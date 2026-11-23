"""Write an ``.svdb`` file from svdb records.

:class:`Writer` is the one way records get into a database: the NDJSON
importer feeds it parsed lines, and a front end (D2) feeds it records it
builds in memory.  It works in two passes so that memory stays bounded and
records may arrive in any order (plan §2):

1. :meth:`Writer.add` streams each record into tables, batched, with every
   cross-record pointer kept as *text* (a parent qname, a Ref target, a
   ``def@key``).  Only the small maps of file and unit ids live in memory.
2. :meth:`Writer.finish` builds the indexes, then resolves those pointers to
   row ids with set-based SQL -- parents, scopes, references (§3.4 order),
   instance definitions, port connections, elaborations -- checks what can
   only be checked once everything is in (duplicate keys, parent kinds,
   dangling pointers, sections), and writes the file.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from typing import Any

from . import SCHEMA_VERSION, canon, layout, records
from .issues import Issue, SvdbError

_ROLE_OWNER = {"uvm.root": "root", "uvm.type": "type", "uvm.child": "owner", "uvm.conn": "owner",
               "uvm.config": "owner", "uvm.override": "owner", "uvm.binding": "interface_type",
               "uvm.sequence": "type"}
_ROLE_TYPE = {"uvm.child": "type", "uvm.override": "original", "uvm.type": "type", "uvm.sequence": "type"}

_INSERT = {
    "object": "INSERT INTO object (id, ns, unit_id, qname, name, kind, pos, file_id, line, col, end_line, end_col,"
              " flags, quals, sig, origin_id, url, hash, detail, extra) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "doc": "INSERT INTO doc (object_id, text, style, grp, loc) VALUES (?,?,?,?,?)",
    "stg_link": "INSERT INTO stg_link (id, parent, scope) VALUES (?,?,?)",
    "stg_hash": "INSERT INTO stg_hash (id) VALUES (?)",
    "ref": "INSERT INTO ref (id, src, src_id, role, pos, seq, head, name, lookup, given,"
           " target_qname, target_ns, target_unit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "stg_cand": "INSERT INTO stg_cand (ref_id, rank, scope) VALUES (?,?,?)",
    "inst": "INSERT INTO inst (object_id, of_name, of_kind, state, array_count) VALUES (?,?,?,?,?)",
    "stg_inst": "INSERT INTO stg_inst (object_id, def_name, bind_from) VALUES (?,?,?)",
    "port_conn": "INSERT INTO port_conn (inst_id, pos, port, mode, dir, expr) VALUES (?,?,?,?,?,?)",
    "stg_body": "INSERT INTO stg_body (seq, of_qname, of_ns, of_unit, text) VALUES (?,?,?,?,?)",
    "import": "INSERT INTO import (seq, scope_name, package_name, item, is_export, rec) VALUES (?,?,?,?,?,?)",
    "use": "INSERT INTO use (seq, from_name, kind, rec) VALUES (?,?,?,?)",
    "diag": "INSERT INTO diag (seq, severity, code, rec) VALUES (?,?,?,?)",
    "uvm": "INSERT INTO uvm (seq, r, field, rec) VALUES (?,?,?,?)",
    "include": "INSERT INTO include (from_id, to_id, line) VALUES (?,?,?)",
    "elab_site": "INSERT INTO elab_site (elab_id, pos, inst_name, present, count, child_def, child_key)"
                 " VALUES (?,?,?,?,?,?,?)",
    "elab_gen": "INSERT INTO elab_gen (elab_id, pos, block_name, taken, iterations) VALUES (?,?,?,?,?)",
}

_STAGING = """
CREATE TABLE stg_link (id INTEGER PRIMARY KEY, parent TEXT, scope TEXT);
CREATE TABLE stg_hash (id INTEGER PRIMARY KEY);
CREATE TABLE stg_cand (ref_id INT, rank INT, scope TEXT);
CREATE TABLE stg_inst (object_id INTEGER PRIMARY KEY, def_name TEXT, bind_from TEXT);
CREATE TABLE stg_body (seq INTEGER PRIMARY KEY, of_qname TEXT, of_ns TEXT, of_unit TEXT, text TEXT, object_id INT);
CREATE TABLE stg_dropped (ns TEXT, unit_id INT, qname TEXT);
"""


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Writer:
    """Build one ``.svdb`` file (or an in-memory database) from records.

    *path* is the file to create (replaced atomically when the build
    succeeds) or ``":memory:"``.  With *strict* (the default), :meth:`finish`
    raises :class:`SvdbError` if any error was found; otherwise errors are only
    reported in :attr:`issues` -- the validator uses that.

    The first record must be the ``header``.  Use as a context manager, or
    call :meth:`finish` (and :meth:`abort` on failure) yourself::

        with Writer("out.svdb") as w:
            for rec in records:
                w.add(rec)
    """

    def __init__(self, path: str | os.PathLike, *, strict: bool = True, batch: int = 10_000):
        self.path = str(path)
        self.strict = strict
        self.batch = batch
        self.issues: list[Issue] = []
        self._memory = self.path == ":memory:"
        if self._memory:
            self._build_path = ":memory:"
        else:
            self._build_path = self.path + ".build"
            for p in (self._build_path, self.path + ".part"):
                if os.path.exists(p):
                    os.remove(p)
        self.conn = sqlite3.connect(self._build_path)
        self.conn.execute("PRAGMA journal_mode=OFF")
        self.conn.execute("PRAGMA synchronous=OFF")
        self.conn.execute("PRAGMA cache_size=-65536")
        self.conn.executescript(layout.TABLES + _STAGING)
        self._buf: dict[str, list] = defaultdict(list)
        self._header: dict | None = None
        self._warned: set[tuple] = set()
        self._file_ids: dict[str, int] = {}
        self._files_declared: set[str] = set()
        self._unit_ids: dict[str, int] = {}
        self._units_declared: set[str] = set()
        self._origin_ids: dict[str, int] = {}
        self._elabs: set[tuple[str, str]] = set()
        self._dropped: list[tuple] = []
        self._section_use: dict[str, int] = defaultdict(int)
        self._next = defaultdict(int)
        self._count = 0
        self._finished = False

    # -- context manager ---------------------------------------------------------

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.finish()
        else:
            self.abort()

    # -- issues ------------------------------------------------------------------

    def _issue(self, severity: str, code: str, message: str, where: str = "") -> None:
        self.issues.append(Issue(severity, code, message, where))

    def _warn_once(self, code: str, name: str, message: str, where: str = "") -> None:
        if (code, name) not in self._warned:
            self._warned.add((code, name))
            self._issue("warning", code, message, where)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    # -- buffered inserts --------------------------------------------------------

    def _push(self, table: str, row: tuple) -> None:
        buf = self._buf[table]
        buf.append(row)
        if len(buf) >= self.batch:
            self._flush(table)

    def _flush(self, table: str | None = None) -> None:
        tables = [table] if table else list(self._buf)
        for t in tables:
            rows = self._buf.get(t)
            if rows:
                self.conn.executemany(_INSERT[t], rows)
                rows.clear()
        self.conn.commit()

    def _id(self, what: str) -> int:
        self._next[what] += 1
        return self._next[what]

    def _file(self, fid: str | None) -> int | None:
        if fid is None:
            return None
        if fid not in self._file_ids:
            self._file_ids[fid] = len(self._file_ids) + 1
        return self._file_ids[fid]

    def _unit(self, name: str | None) -> int:
        if not name:
            return 0
        if name not in self._unit_ids:
            self._unit_ids[name] = len(self._unit_ids) + 1
        return self._unit_ids[name]

    def _origin(self, name: str | None) -> int | None:
        if not name:
            return None
        if name not in self._origin_ids:
            oid = self._origin_ids[name] = len(self._origin_ids) + 1
            self.conn.execute("INSERT INTO origin (id, name) VALUES (?, ?)", (oid, name))
        return self._origin_ids[name]

    # -- pass 1 ------------------------------------------------------------------

    def add(self, rec: dict, where: str = "") -> None:
        """Add one record.  *where* locates it in error messages."""
        if self._finished:
            raise RuntimeError("Writer already finished")
        self._count += 1
        where = where or f"record {self._count}"
        r = rec.get("r") if isinstance(rec, dict) else None
        if self._header is None:
            if r != "header":
                raise SvdbError(f"{where}: the first record must be the header, not {r!r}")
            self._add_header(rec, where)
            return
        if r == "header":
            self._issue("error", "DuplicateHeader", "more than one header record", where)
            return
        info = records.record_types().get(r) if isinstance(r, str) else None
        if info is None:
            self._warn_once("UnknownRecord", str(r), f"record type {r!r} is not known to this reader; ignored", where)
            return
        unknown = [k for k in rec if k not in info.fields]
        if unknown:
            for k in unknown:
                self._warn_once("UnknownField", f"{r}.{k}", f"field {k!r} of {r!r} records is not known; ignored", where)
            rec = {k: v for k, v in rec.items() if k in info.fields}
        missing = sorted(info.required - rec.keys())
        if missing:
            self._issue("error", "MissingField", f"{r} record lacks {', '.join(missing)}", where)
            return
        section = layout.RECORD_SECTION.get(r)
        if section:
            self._section_use[section] += 1
        try:
            getattr(self, "_add_" + r.replace(".", "_"), self._add_uvm)(rec, where)
        except canon.QNameError as e:
            self._issue("error", "BadName", str(e), where)

    def _add_header(self, rec: dict, where: str) -> None:
        if rec.get("format") != "svdb":
            raise SvdbError(f"{where}: not an svdb file (format {rec.get('format')!r})")
        version = str(rec.get("schema", ""))
        major, _, minor = version.partition(".")
        ours = SCHEMA_VERSION.split(".")
        if major != ours[0] or not minor.isdigit():
            raise SvdbError(f"{where}: schema version {version!r} is not supported; this reader reads {ours[0]}.x")
        if int(minor) > int(ours[1]):
            self._issue("warning", "NewerMinor",
                        f"schema {version} is newer than {SCHEMA_VERSION}; unknown content will be ignored", where)
        known = records.record_types()["header"].fields
        for k in [k for k in rec if k not in known]:
            self._warn_once("UnknownField", f"header.{k}", f"header field {k!r} is not known; ignored", where)
        rec = {k: v for k, v in rec.items() if k in known}
        sections = rec.get("sections") or {}
        for name in [s for s in sections if s not in records.sections()]:
            self._warn_once("UnknownSection", name, f"section {name!r} is not known; ignored", where)
        self._header = rec
        self.conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", [
            ("header", _dumps(rec)),
            ("layout_version", str(layout.LAYOUT_VERSION)),
            ("schema", version),
        ])
        self.conn.executemany("INSERT INTO section (name, status) VALUES (?, ?)",
                              [(k, v) for k, v in sections.items() if k in records.sections()])

    def _add_file(self, rec: dict, where: str) -> None:
        fid = rec["id"]
        if fid in self._files_declared:
            self._issue("error", "DuplicateFile", f"file id {fid!r} declared twice", where)
            return
        self._files_declared.add(fid)
        fid_row = self._file(fid)
        self.conn.execute(
            "INSERT INTO file (id, fid, seq, path, sha256, size, lang, protected) VALUES (?,?,?,?,?,?,?,?)",
            (fid_row, fid, self._id("file"), rec["path"], rec.get("sha256"), rec.get("size"), rec.get("lang"),
             _dumps(rec.get("protected"))))
        if "text" in rec:
            self._section_use["sources"] += 1
            self.conn.execute("INSERT INTO file_text (file_id, text) VALUES (?, ?)", (fid_row, rec["text"]))

    def _add_include(self, rec: dict, where: str) -> None:
        self._push("include", (self._file(rec["from"]), self._file(rec["to"]), rec.get("line")))

    def _add_unit(self, rec: dict, where: str) -> None:
        name = rec["id"]
        if name in self._units_declared:
            self._issue("error", "DuplicateUnit", f"unit id {name!r} declared twice", where)
            return
        self._units_declared.add(name)
        uid = self._unit(name)
        self.conn.execute(
            "INSERT INTO unit (id, name, seq, defines, default_nettype, timescale) VALUES (?,?,?,?,?,?)",
            (uid, name, self._id("unit"), _dumps(rec.get("defines")), rec.get("default_nettype"), rec.get("timescale")))
        self.conn.executemany("INSERT INTO unit_file (unit_id, pos, file_id) VALUES (?,?,?)",
                              [(uid, i, self._file(f)) for i, f in enumerate(rec.get("files", ()))])

    def _add_object(self, rec: dict, where: str) -> None:
        kind, ns, qname = rec["kind"], rec["ns"], rec["qname"]
        if kind not in records.kinds():
            self._warn_once("UnknownKind", str(kind), f"object kind {kind!r} is not known to this reader; ignored", where)
            self._dropped.append((ns, self._unit(rec.get("unit")), qname))
            return
        if ns not in canon.NAMESPACES:
            self._issue("error", "BadNamespace", f"{qname}: unknown name space {ns!r}", where)
            return
        if (ns == "unit") != bool(rec.get("unit")):
            self._issue("error", "BadUnit", f"{qname}: 'unit' is required in, and only in, the unit name space", where)
            return
        segs = canon.parse_qname(qname)
        parent = rec.get("parent")
        if parent is None and ns != canon.root_ns(kind):
            self._issue("error", "RootNamespace",
                        f"{qname}: a root {kind} belongs in name space {canon.root_ns(kind)!r}, not {ns!r}", where)
            return
        oid = self._id("object")
        loc = rec.get("loc") or {}
        flags = rec.get("flags") or ()
        extra = {k: rec[k] for k in ("extent", "body_loc", "via", "attrs") if k in rec}
        if "hash" in rec:
            digest = bytes.fromhex(rec["hash"])
        else:
            digest = bytes.fromhex(canon.object_hash(rec))
            self._push("stg_hash", (oid,))
        self._push("object", (
            oid, ns, self._unit(rec.get("unit")), qname, rec["name"], kind, rec["pos"],
            self._file(loc.get("file")), loc.get("line"), loc.get("col"), loc.get("end_line"), loc.get("end_col"),
            layout.flags_to_bits(flags), _dumps(rec.get("quals")), rec.get("sig"), self._origin(rec.get("origin")),
            rec.get("url"), digest, _dumps(rec.get("detail")), _dumps(extra) if extra else None))
        if parent is not None or "scope" in rec:
            self._push("stg_link", (oid, parent, rec.get("scope")))
        doc = rec.get("doc")
        if doc is not None:
            self._section_use["docs"] += 1
            self._push("doc", (oid, doc.get("text"), doc.get("style"), doc.get("group"), _dumps(doc.get("loc"))))
        if "anonymous" in flags:
            self._section_use["anonymous"] += 1
        self._add_refs(layout.SRC_OBJECT, oid, qname, records.find_refs(rec))
        if kind == "instance":
            self._add_instance(oid, segs, rec)

    def _add_instance(self, oid: int, segs: list[str], rec: dict) -> None:
        d = rec.get("detail") or {}
        self._section_use["structure"] += 1
        of = d.get("of") or {}
        array = d.get("array") or {}
        self._push("inst", (oid, of.get("name"), d.get("of_kind"), d.get("state", "ok"), array.get("count")))
        bind = d.get("bind") or {}
        self._push("stg_inst", (oid, segs[0], bind.get("from")))
        conns = d.get("conns") or ()
        if conns:
            self._section_use["connections"] += 1
        for i, c in enumerate(conns):
            expr = c.get("expr")
            self._push("port_conn", (oid, c.get("pos", i), c.get("port"), c.get("mode"), c.get("dir"),
                                     expr.get("text") if isinstance(expr, dict) else None))

    def _add_refs(self, src: int, src_id: int, ctx: str | None, found) -> None:
        scopes: list[str] | None = None
        for role, pos, idx, ref, head in found:
            rid = self._id("ref")
            name = ref["name"]
            target = ref.get("target")
            tq = tns = tunit = None
            lookup = name[:-3] if name.endswith("::*") else name
            if target:
                key = canon.parse_key(target)
                tq, tns, tunit = key.qname, ref.get("ns") or key.ns, key.unit
            self._push("ref", (rid, src, src_id, role, pos, idx, int(bool(head)), name, lookup,
                               int(bool(target)), tq, tns, tunit))
            if target:
                continue
            # Candidate scopes for best-effort resolution (§3.4), innermost
            # first; the root ('') comes first for a qualified name.
            if scopes is None:
                segs = canon.parse_qname(ctx) if ctx else []
                scopes = [canon.format_qname(segs[:k]) for k in range(len(segs), 0, -1)]
            qualified = canon.SEP in lookup
            if qualified:
                self._push("stg_cand", (rid, -1, ""))
            for rank, scope in enumerate(scopes):
                self._push("stg_cand", (rid, rank, scope))
            if not qualified:
                self._push("stg_cand", (rid, len(scopes), ""))

    def _add_body(self, rec: dict, where: str) -> None:
        key = canon.parse_key(rec["of"])
        self._push("stg_body", (self._id("body"), key.qname, key.ns, key.unit, rec["text"]))

    def _add_import(self, rec: dict, where: str) -> None:
        scope = canon.parse_key(rec["scope"]).qname
        pkg = rec["package"]
        target = pkg.get("target")
        pname = canon.parse_key(target).qname if target else pkg["name"]
        if pname.endswith("::*"):
            pname = pname[:-3]
        seq = self._id("import")
        self._push("import", (seq, scope, pname, rec["item"], int(bool(rec.get("export"))), _dumps(rec)))
        self._add_refs(layout.SRC_IMPORT, seq, scope, records.find_refs(rec))

    def _add_use(self, rec: dict, where: str) -> None:
        seq = self._id("use")
        frm = canon.parse_key(rec["from"]).qname
        self._push("use", (seq, frm, rec["kind"], _dumps(rec)))
        self._add_refs(layout.SRC_USE, seq, frm, records.find_refs(rec))

    def _add_diag(self, rec: dict, where: str) -> None:
        self._push("diag", (self._id("diag"), rec["severity"], rec.get("code"), _dumps(rec)))

    def _add_elab(self, rec: dict, where: str) -> None:
        key = (rec["def"], rec["key"])
        if key in self._elabs:
            self._issue("error", "DuplicateElab", f"elaboration {canon.elab_ref(*key)} appears twice", where)
            return
        self._elabs.add(key)
        eid = self._id("elab")
        self.conn.execute("INSERT INTO elab (id, def_name, key, count, truncated, rec) VALUES (?,?,?,?,?,?)",
                          (eid, rec["def"], rec["key"], rec.get("count"), int(bool(rec.get("truncated"))), _dumps(rec)))
        for i, s in enumerate(rec.get("sites") or ()):
            cdef, _, ckey = (s.get("elab") or "").rpartition("@")
            self._push("elab_site", (eid, i, s.get("inst"), int(s.get("present", True)), s.get("count"),
                                     cdef or None, ckey or None))
        for i, g in enumerate(rec.get("generate") or ()):
            taken = g.get("taken")
            self._push("elab_gen", (eid, i, g.get("block"), None if taken is None else int(taken), g.get("iterations")))

    def _add_top(self, rec: dict, where: str) -> None:
        d, _, k = rec["elab"].rpartition("@")
        self.conn.execute("INSERT INTO top (seq, elab_def, elab_key, origin, rec) VALUES (?,?,?,?,?)",
                          (self._id("top"), d, k, rec.get("origin"), _dumps(rec)))

    def _add_uvm(self, rec: dict, where: str) -> None:
        seq = self._id("uvm")
        self._push("uvm", (seq, rec["r"], rec.get("field"), _dumps(rec)))
        self._add_refs(layout.SRC_UVM, seq, None, records.find_refs(rec))

    # -- pass 2 ------------------------------------------------------------------

    def finish(self) -> list[Issue]:
        """Resolve, check and write the database.  Returns :attr:`issues`.

        Raises :class:`SvdbError` (and removes the partial file) when *strict*
        and an error was found.
        """
        if self._finished:
            return self.issues
        if self._header is None:
            self.abort()
            raise SvdbError("no header record")
        try:
            self._flush()
            self._placeholders()
            self._check_sections()
            dup = self._check_duplicates()
            for sql in layout.INDEXES:
                if dup and sql.startswith("CREATE UNIQUE INDEX object_key"):
                    sql = sql.replace("UNIQUE ", "")
                self.conn.execute(sql)
            self.conn.execute("CREATE INDEX stg_cand_ref ON stg_cand(ref_id, rank)")
            self._drop_orphans_of_unknown_kinds()
            self._resolve_links()
            self._check_parent_kinds()
            self._resolve_refs()
            self._resolve_structure()
            self._resolve_bodies()
            self._resolve_records()
            self._hash_bodies()
            self.conn.executescript(
                "DROP TABLE stg_link; DROP TABLE stg_hash; DROP TABLE stg_cand; DROP TABLE stg_inst;"
                " DROP TABLE stg_body; DROP TABLE stg_dropped;")
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) SELECT 'objects', count(*) FROM object")
            self.conn.commit()
        except BaseException:
            self.abort()
            raise
        if self.strict and self.errors:
            self.abort()
            raise SvdbError(f"cannot write {self.path}", self.issues)
        self.conn.execute("ANALYZE")
        self.conn.commit()
        self._finished = True
        if not self._memory:
            part = self.path + ".part"
            self.conn.execute("VACUUM INTO ?", (part,))
            self.conn.close()
            os.replace(part, self.path)
            os.remove(self._build_path)
        return self.issues

    def abort(self) -> None:
        """Discard the build."""
        self._finished = True
        try:
            self.conn.close()
        finally:
            if not self._memory:
                for p in (self._build_path, self.path + ".part"):
                    if os.path.exists(p):
                        os.remove(p)

    def _placeholders(self) -> None:
        missing = [f for f in self._file_ids if f not in self._files_declared]
        for fid in missing:
            self._issue("warning", "UnknownFile", f"file id {fid!r} is used but has no file record")
        self.conn.executemany("INSERT INTO file (id, fid) VALUES (?, ?)", [(self._file_ids[f], f) for f in missing])
        missing = [u for u in self._unit_ids if u not in self._units_declared]
        for name in missing:
            self._issue("warning", "UnknownUnit", f"unit id {name!r} is used but has no unit record")
        self.conn.executemany("INSERT INTO unit (id, name) VALUES (?, ?)", [(self._unit_ids[u], u) for u in missing])

    def _check_sections(self) -> None:
        declared = (self._header or {}).get("sections") or {}
        for section, n in sorted(self._section_use.items()):
            if declared.get(section) == "absent":
                self._issue("error", "SectionAbsent",
                            f"header declares section {section!r} absent, but {n} record(s) or field(s) belong to it")

    def _where(self, oid: int) -> str:
        row = self.conn.execute(
            "SELECT f.path, o.line FROM object o LEFT JOIN file f ON f.id = o.file_id WHERE o.id = ?", (oid,)).fetchone()
        if row and row[0]:
            return f"{row[0]}:{row[1]}" if row[1] else row[0]
        return ""

    def _check_duplicates(self) -> bool:
        rows = self.conn.execute(
            "SELECT ns, unit_id, qname, group_concat(id) FROM object GROUP BY ns, unit_id, qname"
            " HAVING count(*) > 1").fetchall()
        for ns, unit_id, qname, ids in rows:
            places = [self._where(int(i)) or f"object #{i}" for i in ids.split(",")]
            self._issue("error", "DuplicateKey",
                        f"{ns}:{qname} is declared {len(places)} times: {', '.join(places)}", places[0])
        return bool(rows)

    def _drop_orphans_of_unknown_kinds(self) -> None:
        """Children of objects dropped for an unknown kind go with them, quietly."""
        if not self._dropped:
            return
        self.conn.executemany("INSERT INTO stg_dropped VALUES (?,?,?)", self._dropped)
        self.conn.execute("CREATE INDEX stg_dropped_key ON stg_dropped(ns, unit_id, qname)")
        while True:
            ids = [r[0] for r in self.conn.execute(
                "SELECT o.id FROM stg_link s JOIN object o ON o.id = s.id JOIN stg_dropped d"
                " ON d.ns = o.ns AND d.unit_id = o.unit_id AND d.qname = s.parent")]
            if not ids:
                return
            for oid in ids:
                self.conn.execute("INSERT INTO stg_dropped SELECT ns, unit_id, qname FROM object WHERE id = ?", (oid,))
                for table, col in (("object", "id"), ("stg_link", "id"), ("doc", "object_id"), ("inst", "object_id"),
                                   ("stg_inst", "object_id"), ("port_conn", "inst_id"), ("stg_hash", "id")):
                    self.conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (oid,))
                self.conn.execute("DELETE FROM ref WHERE src = 0 AND src_id = ?", (oid,))

    def _resolve_links(self) -> None:
        c = self.conn
        for col in ("parent", "scope"):
            c.execute(f"""
                UPDATE object SET {col}_id = p.id FROM stg_link s, object p
                WHERE s.id = object.id AND s.{col} IS NOT NULL
                  AND p.ns = object.ns AND p.unit_id = object.unit_id AND p.qname = s.{col}""")
            for oid, qname, target in c.execute(f"""
                    SELECT o.id, o.qname, s.{col} FROM stg_link s JOIN object o ON o.id = s.id
                    WHERE s.{col} IS NOT NULL AND o.{col}_id IS NULL""").fetchall():
                self._issue("error", "Dangling" + col.title(),
                            f"{qname}: {col} {target!r} is not an object in this database", self._where(oid))

    def _check_parent_kinds(self) -> None:
        c = self.conn
        for kind, pkind, qname in c.execute(
                "SELECT o.kind, p.kind, min(o.qname) FROM object o JOIN object p ON p.id = o.parent_id"
                " GROUP BY o.kind, p.kind").fetchall():
            if pkind not in records.PARENT_KINDS.get(kind, ()):
                self._issue("error", "BadParentKind", f"a {kind} cannot be a child of a {pkind} (e.g. {qname})")
        for kind, qname in c.execute(
                "SELECT o.kind, min(o.qname) FROM object o LEFT JOIN stg_link s ON s.id = o.id"
                " WHERE s.parent IS NULL GROUP BY o.kind").fetchall():
            if kind not in records.ROOT_KINDS:
                self._issue("error", "BadRootKind", f"a {kind} cannot be a root object (e.g. {qname})")

    def _resolve_refs(self) -> None:
        c = self.conn
        # Producer-given targets: an exact key.
        c.execute("""
            UPDATE ref SET target_id = (
              SELECT o.id FROM object o
              WHERE o.qname = ref.target_qname AND (ref.target_ns IS NULL OR o.ns = ref.target_ns)
                AND (ref.target_unit IS NULL OR o.unit_id = (SELECT u.id FROM unit u WHERE u.name = ref.target_unit))
              ORDER BY o.id LIMIT 1)
            WHERE given = 1""")
        # Unresolved names, best effort (§3.4): enclosing scopes innermost
        # first, each followed by the packages imported into it ...
        c.execute("""
            UPDATE ref SET target_id = (
              SELECT id FROM (
                SELECT k.rank AS rk, 0 AS sub, o.id AS id FROM stg_cand k JOIN object o
                  ON o.qname = (CASE WHEN k.scope = '' THEN ref.lookup ELSE k.scope || '::' || ref.lookup END)
                WHERE k.ref_id = ref.id
                UNION ALL
                SELECT k.rank, 1, o.id FROM stg_cand k JOIN import i ON i.scope_name = k.scope
                  JOIN object o ON o.qname = i.package_name || '::' || ref.lookup
                WHERE k.ref_id = ref.id AND (i.item = '*' OR i.item = ref.lookup))
              ORDER BY rk, sub, id LIMIT 1)
            WHERE given = 0""")
        # ... then a bare name that is unique in the database.
        c.execute("""
            UPDATE ref SET target_id = (
              SELECT min(o.id) FROM object o WHERE o.name = ref.lookup HAVING count(*) = 1)
            WHERE given = 0 AND target_id IS NULL AND instr(ref.lookup, '::') = 0""")
        c.execute("""
            UPDATE ref SET target_qname = o.qname, target_ns = o.ns,
                           target_unit = (SELECT u.name FROM unit u WHERE u.id = o.unit_id)
            FROM object o WHERE o.id = ref.target_id AND ref.given = 0""")

    def _resolve_structure(self) -> None:
        c = self.conn
        c.execute("""UPDATE inst SET of_id = r.target_id FROM ref r
                     WHERE r.src = 0 AND r.src_id = inst.object_id AND r.role = 'of'""")
        c.execute("""UPDATE inst SET def_id = o.id FROM stg_inst s, object me, object o
                     WHERE s.object_id = inst.object_id AND me.id = inst.object_id
                       AND o.ns = me.ns AND o.unit_id = me.unit_id AND o.qname = s.def_name""")
        c.execute("""UPDATE inst SET bind_from_id = (SELECT o.id FROM object o WHERE o.qname = s.bind_from
                                                     ORDER BY o.id LIMIT 1)
                     FROM stg_inst s WHERE s.object_id = inst.object_id AND s.bind_from IS NOT NULL""")
        c.execute("""UPDATE port_conn SET port_id = (
                       SELECT o.id FROM inst i JOIN object o ON o.parent_id = i.of_id
                       WHERE i.object_id = port_conn.inst_id AND o.name = port_conn.port AND o.kind = 'port')
                     WHERE port IS NOT NULL""")
        design = "(SELECT o.id FROM object o WHERE o.ns = 'design' AND o.unit_id = 0 AND o.qname = {})"
        c.execute(f"UPDATE elab SET def_id = {design.format('elab.def_name')}")
        c.execute(f"UPDATE elab_site SET inst_id = {design.format('elab_site.inst_name')}")
        c.execute("""UPDATE elab_site SET child_elab_id = (SELECT e.id FROM elab e WHERE e.def_name = elab_site.child_def
                                                           AND e.key = elab_site.child_key)
                     WHERE child_def IS NOT NULL""")
        c.execute(f"UPDATE elab_gen SET block_id = {design.format('elab_gen.block_name')}")
        c.execute("""UPDATE top SET elab_id = (SELECT e.id FROM elab e WHERE e.def_name = top.elab_def
                                               AND e.key = top.elab_key)""")
        for table, col, what in (("elab", "def_name", "definition"), ("elab_site", "inst_name", "instance"),
                                 ("elab_gen", "block_name", "generate block")):
            idcol = {"elab": "def_id", "elab_site": "inst_id", "elab_gen": "block_id"}[table]
            for (name,) in c.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {idcol} IS NULL").fetchall():
                self._issue("error", "DanglingElab", f"elaboration names {what} {name!r}, which is not in this database")
        for d, k in c.execute("SELECT elab_def, elab_key FROM top WHERE elab_id IS NULL").fetchall():
            self._issue("error", "DanglingElab", f"top {d}@{k} names no elab record")

    def _resolve_bodies(self) -> None:
        c = self.conn
        c.execute("""
            UPDATE stg_body SET object_id = (
              SELECT o.id FROM object o
              WHERE o.qname = stg_body.of_qname AND (stg_body.of_ns IS NULL OR o.ns = stg_body.of_ns)
                AND (stg_body.of_unit IS NULL OR o.unit_id = (SELECT u.id FROM unit u WHERE u.name = stg_body.of_unit))
              ORDER BY o.id LIMIT 1)""")
        for (q,) in c.execute("SELECT of_qname FROM stg_body WHERE object_id IS NULL").fetchall():
            self._issue("error", "DanglingBody", f"body of {q!r}, which is not an object in this database")
        for (q,) in c.execute("SELECT min(of_qname) FROM stg_body WHERE object_id IS NOT NULL"
                              " GROUP BY object_id HAVING count(*) > 1").fetchall():
            self._issue("error", "DuplicateBody", f"{q!r} has more than one body record")
        c.execute("""INSERT OR IGNORE INTO body (object_id, text)
                     SELECT object_id, text FROM stg_body WHERE object_id IS NOT NULL ORDER BY seq""")

    def _resolve_records(self) -> None:
        c = self.conn
        c.execute("UPDATE import SET scope_id = (SELECT o.id FROM object o WHERE o.qname = import.scope_name"
                  " ORDER BY o.id LIMIT 1)")
        c.execute("UPDATE import SET package_id = r.target_id FROM ref r"
                  " WHERE r.src = 1 AND r.src_id = import.seq AND r.role = 'package'")
        for (q,) in c.execute("SELECT DISTINCT scope_name FROM import WHERE scope_id IS NULL").fetchall():
            self._issue("error", "DanglingScope", f"import into {q!r}, which is not an object in this database")
        c.execute("UPDATE use SET from_id = (SELECT o.id FROM object o WHERE o.qname = use.from_name"
                  " ORDER BY o.id LIMIT 1)")
        c.execute("UPDATE use SET to_id = r.target_id FROM ref r WHERE r.src = 2 AND r.src_id = use.seq AND r.role = 'to'")
        for (q,) in c.execute("SELECT DISTINCT from_name FROM use WHERE from_id IS NULL").fetchall():
            self._issue("error", "DanglingUse", f"use from {q!r}, which is not an object in this database")
        for col, roles in (("owner_id", _ROLE_OWNER), ("type_id", _ROLE_TYPE)):
            for r, role in roles.items():
                c.execute(f"UPDATE uvm SET {col} = ref.target_id FROM ref"
                          " WHERE ref.src = 3 AND ref.src_id = uvm.seq AND uvm.r = ? AND ref.role = ?", (r, role))

    def _hash_bodies(self) -> None:
        """Objects whose hash the writer computed, and that have a body, hash it too."""
        from .exporter import object_record

        rows = self.conn.execute(
            "SELECT h.id, b.text FROM stg_hash h JOIN body b ON b.object_id = h.id").fetchall()
        for oid, text in rows:
            rec = object_record(self.conn, oid)
            self.conn.execute("UPDATE object SET hash = ? WHERE id = ?",
                              (bytes.fromhex(canon.object_hash(rec, body=text)), oid))


def write(path: str | os.PathLike, recs, *, strict: bool = True) -> list[Issue]:
    """Write the records *recs* (header first) to *path*.  Returns the issues."""
    with Writer(path, strict=strict) as w:
        for rec in recs:
            w.add(rec)
    return w.issues
