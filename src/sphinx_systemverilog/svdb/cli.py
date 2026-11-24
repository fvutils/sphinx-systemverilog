"""``svdb``: import, export, validate and query svdb databases.

::

    svdb build --source-dir rtl -I rtl/include --top soc -o design.svdb
    svdb build --sphinx-conf docs/conf.py -o design.svdb
    svdb import design.ndjson -o design.svdb
    svdb export design.svdb -o design.ndjson
    svdb validate design.ndjson            # or a .svdb
    svdb stats design.svdb --unresolved
    svdb query -d design.svdb get axi_pkg::axi_item
    svdb query -d tb.svdb -d vip.svdb derived uvm_pkg::uvm_component --transitive
    svdb sql design.svdb "SELECT kind, count(*) FROM object GROUP BY kind"
    svdb uvm-tree -d tb.svdb -d vip.svdb --root my_test --format text
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import contextmanager
from typing import Iterator, Sequence

from . import exporter, importer
from .database import AmbiguousKey, Database, Object, Unresolved
from .issues import SvdbError
from .validate import validate


def _is_db(path: str) -> bool:
    if path == "-":
        return False
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


@contextmanager
def _text_in(path: str) -> Iterator:
    if path == "-":
        yield sys.stdin
    else:
        with open(path, encoding="utf-8") as f:
            yield f


def _print_issues(issues, out=sys.stderr) -> None:
    for i in issues:
        print(i, file=out)


def cmd_build(args) -> int:
    # The front end needs pyslang; the rest of svdb does not (plan D1-TEST-5).
    from ..frontend import build

    kw: dict = {}
    if args.sphinx_conf:
        kw = build.conf_kwargs(args.sphinx_conf)
    for flag, key in (("source_dir", "source_dirs"), ("build_unit", "build_units"),
                      ("include_dir", "include_dirs"), ("top", "structure_tops")):
        if getattr(args, flag):
            kw[key] = getattr(args, flag)
    if args.define:
        kw["defines"] = dict(d.split("=", 1) if "=" in d else (d, "") for d in args.define)
    for flag, key in (("doc_style", "doc_style"), ("uvm_root", "uvm_root")):
        if getattr(args, flag) is not None:
            kw[key] = getattr(args, flag)
    if args.no_macros:
        kw["document_macros"] = False
    if args.link:
        kw["links"] = [*kw.get("links", ()), *args.link]
    kw.setdefault("base_path", None)
    if not kw.get("source_dirs") and not kw.get("build_units"):
        print("svdb: nothing to parse; give --source-dir, --build-unit or --sphinx-conf", file=sys.stderr)
        return 1
    options = build.Options.make(**kw)
    index = build.parse(options)
    w = build.write(index, options, args.output)
    w.conn.close()
    _print_issues(w.issues)
    for d in index.diagnostics:
        print(f"parser: {d.strip()}", file=sys.stderr)
    print(f"{args.output}: {len(index)} object(s)")
    return 0


def cmd_import(args) -> int:
    with _text_in(args.input) as f:
        w = importer.import_stream(f, args.output, name=args.input)
    _print_issues(w.issues)
    return 0


def cmd_export(args) -> int:
    with Database.open(args.database) as db:
        conn = db.connection()
        if args.output in (None, "-"):
            exporter.export(conn, sys.stdout)
        else:
            with open(args.output, "w", encoding="utf-8") as out:
                exporter.export(conn, out)
    return 0


def cmd_validate(args) -> int:
    if _is_db(args.input):
        with Database.open(args.input) as db:
            report = validate(list(exporter.iter_records(db.connection())), check_schema=not args.no_schema)
    else:
        with _text_in(args.input) as f:
            report = validate(importer.read_ndjson(f, args.input), check_schema=not args.no_schema)
    _print_issues(report.issues, sys.stdout)
    print(f"{args.input}: {report.records} records, {report.objects} objects, {report.references} references"
          f" ({report.unresolved} unresolved, {report.external} to other databases); "
          f"{len(report.errors)} error(s)" + ("" if report.schema_checked else "; schema not checked"))
    return 0 if report.ok else 1


def cmd_stats(args) -> int:
    with Database.open(args.database) as db:
        q = db.sql
        stats = {
            "kinds": dict(q("SELECT kind, count(*) FROM object GROUP BY kind ORDER BY kind")),
            "namespaces": dict(q("SELECT ns, count(*) FROM object GROUP BY ns ORDER BY ns")),
            "files": q("SELECT count(*) FROM file")[0][0],
            "references": q("SELECT count(*) FROM ref")[0][0],
            "unresolved": q("SELECT count(*) FROM ref WHERE target_id IS NULL AND given = 0")[0][0],
            "external": q("SELECT count(*) FROM ref WHERE target_id IS NULL AND given = 1")[0][0],
            "sections": dict(q("SELECT name, status FROM section ORDER BY name")),
            "links": [{"origin": lk.origin, "path": lk.path, "units": list(lk.units), "state": lk.state}
                      for lk in db.links()],
        }
        if args.unresolved:
            stats["unresolved_refs"] = [
                {"from": f, "role": role, "name": name}
                for f, role, name in q(
                    "SELECT coalesce(o.qname, r.src || ':' || r.src_id), r.role, r.name FROM ref r"
                    " LEFT JOIN object o ON r.src = 0 AND o.id = r.src_id"
                    " WHERE r.target_id IS NULL AND r.given = 0 ORDER BY r.id")]
    if args.json:
        json.dump(stats, sys.stdout, indent=2)
        print()
        return 0
    print(f"objects: {sum(stats['kinds'].values())}")
    for k, n in stats["kinds"].items():
        print(f"  {k:<14} {n}")
    print("name spaces: " + ", ".join(f"{k} {n}" for k, n in stats["namespaces"].items()))
    print(f"files: {stats['files']}")
    print(f"references: {stats['references']} ({stats['unresolved']} unresolved,"
          f" {stats['external']} to other databases)")
    for r in stats.get("unresolved_refs", ()):
        print(f"  {r['from']}  {r['role']}  {r['name']}")
    for lk in stats["links"]:
        # Alone, the file cannot check a hash: "missing" means "not open here".
        note = {"missing": "not open; give it with the database to check it"}.get(lk["state"], lk["state"])
        print(f"linked against {lk['origin']} ({lk['path'] or 'path unknown'}): {', '.join(lk['units'])}"
              f" [{note}]")
    return 0


def _show(db: Database, o: Object | Unresolved, as_json: bool) -> None:
    if isinstance(o, Unresolved):
        print(json.dumps({"unresolved": o.name, "target": o.target}) if as_json
              else f"(unresolved) {o.name}" + (f" -> {o.target}" if o.target else ""))
        return
    if as_json:
        print(exporter.dumps(db.record(o)))
        return
    where = f"{o.loc.path}:{o.loc.line}" if o.loc and o.loc.path else ""
    print(f"{o.kind:<12} {o.ns}:{o.qname}  {where}")


def cmd_query(args) -> int:
    with Database.open(args.db) as db:
        if args.op == "find":
            found = db.find(args.arg, kind=args.kind, limit=args.limit)
        else:
            try:
                obj = db.get(args.arg)
            except AmbiguousKey as e:
                print(f"svdb: {e}", file=sys.stderr)
                return 2
            if obj is None:
                print(f"svdb: no object {args.arg!r}", file=sys.stderr)
                return 1
            if args.op == "get":
                found = [obj]
            elif args.op == "members":
                found = db.members(obj, [args.kind] if args.kind else None)
            elif args.op == "bases":
                found = db.bases(obj)
            elif args.op == "derived":
                found = db.derived(obj, transitive=args.transitive)
            else:  # refs
                found = []
                for ref in db.references(obj):
                    if args.json:
                        _show(db, ref.source, True)
                    else:
                        print(f"{ref.role:<14} {ref.source.ns}:{ref.source.qname}")
        for o in found:
            _show(db, o, args.json)
    return 0


def cmd_sql(args) -> int:
    with Database.open(args.database) as db:
        for row in db.sql(args.query, args.params):
            print("\t".join("" if v is None else v.hex() if isinstance(v, bytes) else str(v) for v in row))
    return 0


def cmd_uvm_tree(args) -> int:
    from .uvm_tree import render_dot, render_text

    with Database.open(args.db, follow_links=args.follow_links) as db:
        try:
            tree = db.uvm_tree(args.root, name=args.name, include_conditional=not args.no_conditional,
                               max_nodes=args.max_nodes)
        except LookupError as e:
            print(f"svdb: {e.args[0] if e.args else e}", file=sys.stderr)
            return 1
    if args.format == "text":
        text = render_text(tree)
    elif args.format == "dot":
        text = render_dot(tree)
    else:
        text = tree.dumps(nested=args.format == "nested") + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_uvm_sequences(args) -> int:
    import json

    from .uvm_sequences import open_provider, render_text, to_json, view

    if args.view != "tasks" and not args.name:
        print(f"svdb: the {args.view} view needs a class name", file=sys.stderr)
        return 1
    provider = open_provider(args.db, follow_links=args.follow_links)
    value = view(provider, args.view, args.name or "", args.method or "")
    if value is None:
        what = "sequence" if args.view == "users" else "behavioural task"
        print(f"svdb: no {what} named {args.name!r}", file=sys.stderr)
        return 1
    if args.format == "text":
        text = render_text(args.view, value)
    else:
        text = json.dumps(to_json(value), indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="svdb", description="SystemVerilog design database tool.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("build", help="parse SystemVerilog sources into a database file (needs pyslang)")
    s.add_argument("-o", "--output", required=True, help="database file to write")
    s.add_argument("--sphinx-conf", metavar="CONF_PY",
                   help="take the sv_* settings from a Sphinx conf.py; the flags below override them")
    s.add_argument("--source-dir", action="append", help="directory (or file) to scan for .sv/.svh (repeat)")
    s.add_argument("--build-unit", action="append", help="file to parse as a root, instead of scanning (repeat)")
    s.add_argument("-I", "--include-dir", action="append", help="include directory (repeat)")
    s.add_argument("-D", "--define", action="append", metavar="NAME[=VALUE]", help="preprocessor define (repeat)")
    s.add_argument("--top", action="append", help="elaborate only this top module (repeat)")
    s.add_argument("--doc-style", choices=["native", "naturaldocs", "doxygen", "auto"])
    s.add_argument("--uvm-root", help="root UVM component (default: detected from run_test)")
    s.add_argument("--no-macros", action="store_true", help="do not record `define macros")
    s.add_argument("--link", action="append", metavar="DATABASE",
                   help="link against this database: what the sources use but do not define is taken"
                        " from it and not written (repeat; the first that defines a name wins)")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("import", help="import NDJSON into a database file")
    s.add_argument("input", help="NDJSON file ('-' for stdin)")
    s.add_argument("-o", "--output", required=True, help="database file to write")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("export", help="export a database as NDJSON, in canonical order")
    s.add_argument("database")
    s.add_argument("-o", "--output", help="NDJSON file (default: stdout)")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("validate", help="check an NDJSON or database file against the schema and the rules")
    s.add_argument("input", help="NDJSON file, database file, or '-'")
    s.add_argument("--no-schema", action="store_true", help="skip the JSON Schema check")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("stats", help="counts by kind, name space and reference resolution")
    s.add_argument("database")
    s.add_argument("--unresolved", action="store_true", help="list the unresolved references")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("query", help="look objects up")
    s.add_argument("-d", "--db", action="append", required=True, help="database file (repeat to federate)")
    s.add_argument("op", choices=["get", "find", "members", "bases", "derived", "refs"])
    s.add_argument("arg", help="a key (qname, ns:qname, $unit[id]::name) or, for find, a GLOB pattern")
    s.add_argument("--kind", help="find/members: only this kind")
    s.add_argument("--limit", type=int, default=1000, help="find: at most this many (default 1000)")
    s.add_argument("--transitive", action="store_true", help="derived: at any depth")
    s.add_argument("--json", action="store_true", help="print object records as NDJSON")
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("sql", help="run a read-only SQL query (the layout is not a stable interface)")
    s.add_argument("database")
    s.add_argument("query")
    s.add_argument("params", nargs="*")
    s.set_defaults(func=cmd_sql)

    s = sub.add_parser("uvm-tree", help="the UVM component tree, with factory overrides applied and connections")
    s.add_argument("-d", "--db", action="append", required=True, help="database file (repeat to stitch several)")
    s.add_argument("--root", help="root test class (default: the database's uvm.root)")
    s.add_argument("--name", default="uvm_test_top", help="the root's instance name (default: uvm_test_top)")
    s.add_argument("--follow-links", action="store_true",
                   help="also open the databases the given ones were linked against")
    s.add_argument("--format", choices=["json", "nested", "text", "dot"], default="json",
                   help="json (flat, default), nested JSON, an indented text tree, or Graphviz dot")
    s.add_argument("--no-conditional", action="store_true",
                   help="leave out components and connections that sit under an if")
    s.add_argument("--max-nodes", type=int, default=5000, help="stop after this many components (default 5000)")
    s.add_argument("-o", "--output", help="file to write (default: stdout)")
    s.set_defaults(func=cmd_uvm_tree)

    s = sub.add_parser("uvm-sequences",
                       help="the sequences a test task or sequence depends on, or that depend on a sequence")
    s.add_argument("name", nargs="?", help="the class: a test or other component, or a sequence")
    s.add_argument("-d", "--db", action="append", required=True, help="database file (repeat for linked ones)")
    s.add_argument("--view", choices=["catalog", "tree", "users", "tasks"], default="catalog",
                   help="catalog (each sequence once, default), tree (every start, nested), users (what"
                        " depends on a sequence), or tasks (every behavioural task; no name)")
    s.add_argument("--method", help="the task: body for a sequence (default), a task phase for a component"
                                    " (default run_phase)")
    s.add_argument("--follow-links", action="store_true",
                   help="also open the databases the given ones were linked against")
    s.add_argument("--format", choices=["json", "text"], default="json")
    s.add_argument("-o", "--output", help="file to write (default: stdout)")
    s.set_defaults(func=cmd_uvm_sequences)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SvdbError as e:
        print(f"svdb: {e}", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"svdb: SQL error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
