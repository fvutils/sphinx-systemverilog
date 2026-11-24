"""Declaration-only SystemVerilog from a database, for linking a compile
against it (docs/design/svdb-linking-plan.md §1.4).

The text is what another compilation can *observe* of a package, interface,
module or program: names, types, signatures, parameter values and port lists.
Bodies, constraints, covergroups and assertions are left out; a non-void
function gets an empty body.  Members a macro generated (``type_id`` of a
``uvm_*_utils`` class) are written out expanded, as recorded: a link buffer is
its own preprocessing unit, so the macro would not be defined there.

Pure Python: no pyslang import, so it lives with the reader.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from .database import Database, Object

#: Prefix of the buffer names generated text is parsed under.
LINK_SCHEME = "svdb-link:"

#: Kinds a link unit can be (a root object).
UNIT_KINDS = ("package", "interface", "module", "program")

_END = {"package": "endpackage", "interface": "endinterface", "module": "endmodule",
        "program": "endprogram", "class": "endclass"}
#: Written before a method's ``function``/``task`` keyword.
_METHOD_WORDS = {"pure", "virtual", "static", "local", "protected", "extern"}
#: Written before a property's type.
_PROPERTY_WORDS = {"local", "protected", "static", "rand", "randc", "const", "var", "automatic"}
_ELIDED = "{ ... }"


def buffer_name(origin: str, unit: str) -> str:
    """The name the text of *unit* from the database labelled *origin* is parsed under."""
    return f"{LINK_SCHEME}{origin}/{unit}.sv"


def is_link_buffer(name: str | None) -> bool:
    return bool(name) and name.startswith(LINK_SCHEME)


def origin_of(db: Database, source: int) -> str:
    """A database file's label: its header ``origin``, else its file name without suffix."""
    origin = (db.headers[source] or {}).get("origin")
    if origin:
        return origin
    return os.path.splitext(os.path.basename(db.paths[source]))[0] or f"db{source}"


# -- units and their closure -------------------------------------------------------


def unit(db: Database, name: str) -> Object | None:
    """The package or definition called *name* (first file wins), or None."""
    for o in db.by_qname(name):
        if o.parent is None and o.kind in UNIT_KINDS and o.ns in ("package", "design"):
            return o
    return None


@dataclass
class Closure:
    """What :func:`closure` found."""

    #: Units to link, dependencies before the units that need them.
    units: list[Object] = field(default_factory=list)
    #: Names the units need that the database does not define (a source may).
    missing: set[str] = field(default_factory=set)
    #: ``$unit`` declarations the units need; these cannot be linked (§1.2).
    unit_scope: set[str] = field(default_factory=set)


def closure(db: Database, names: Iterable[str]) -> Closure:
    """*names* (packages, interfaces, modules, programs) and everything they need
    from *db*: the packages they import, the packages that qualified names in
    their declarations live in, and the definitions their types name."""
    out = Closure()
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        u = unit(db, name)
        if u is None:
            if any(o.ns == "unit" for o in db.by_qname(name)):
                out.unit_scope.add(name)
            else:
                out.missing.add(name)
            return
        for dep in sorted(_dependencies(db, u)):
            if dep != name:
                visit(dep)
        out.units.append(u)

    for n in names:
        visit(n)
    return out


def _dependencies(db: Database, u: Object) -> set[str]:
    deps = {pkg for pkg, _item, _export in imports(db, u)}
    for o in _walk(db, u):
        deps.update(_imports_of(db, o) if o.kind == "class" else ())
        for name in _ref_names(o.detail):
            if "::" in name:
                head = name.split("::", 1)[0]
                # ``cls::member`` names a class scope, not a package.
                if unit(db, head) is not None or not any(x.kind == "class" for x in db.by_name(head)):
                    deps.add(head)
            elif name not in deps:
                d = unit(db, name)
                if d is not None and d.kind != "package":
                    deps.add(name)
                elif d is None and any(x.ns == "unit" and x.parent is None for x in db.by_qname(name)):
                    deps.add(name)      # a $unit declaration: reported, not linked
    return deps


def _ref_names(value: Any) -> Iterator[str]:
    """The ``name`` of every ``Span`` in a ``detail`` value."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "refs" and isinstance(v, list):
                for span in v:
                    if isinstance(span, dict) and span.get("name"):
                        yield span["name"]
            else:
                yield from _ref_names(v)
    elif isinstance(value, list):
        for v in value:
            yield from _ref_names(v)


def _walk(db: Database, obj: Object) -> Iterator[Object]:
    yield obj
    for m in db.members(obj):
        yield from _walk(db, m)


def imports(db: Database, scope: Object) -> list[tuple[str, str, bool]]:
    """``(package, item, export)`` for each import written in *scope*, in order."""
    rows = db.sql("SELECT package_name, item, is_export FROM import WHERE scope_name = ? ORDER BY seq",
                  (scope.qname,), source=scope.source)
    return [(p, i, bool(e)) for p, i, e in rows if p and i]


def _imports_of(db: Database, scope: Object) -> set[str]:
    return {p for p, _i, _e in imports(db, scope)}


# -- text ----------------------------------------------------------------------------


def generate(db: Database, units: Iterable[Object]) -> dict[str, str]:
    """``{buffer name: text}`` for each of *units* (see :func:`closure`)."""
    return {buffer_name(origin_of(db, u.source), u.qname): unit_text(db, u) for u in units}


def unit_text(db: Database, u: Object) -> str:
    """The declaration-only text of one package or definition."""
    lines: list[str] = []
    _Gen(db, lines).unit(u)
    return "\n".join(lines) + "\n"


def include_text(db: Database, path: str, source: int = 0) -> str:
    """The `` `define ``s the database recorded from the file *path*, in source
    order, under a guard so a second `` `include `` in a compilation unit is harmless."""
    rows = db.sql("SELECT o.qname FROM object o JOIN file f ON o.file_id = f.id "
                  "WHERE o.kind = 'macro' AND f.path = ? ORDER BY o.line, o.col", (path,), source=source)
    guard = "SVDB_LINK_" + re.sub(r"\W", "_", os.path.basename(path)).upper()
    lines = [f"`ifndef {guard}", f"`define {guard}"]
    for (qname,) in rows:
        m = next((o for o in db.by_qname(qname) if o.kind == "macro" and o.source == source), None)
        if m is not None:
            lines.append(macro_text(m))
    lines.append("`endif")
    return "\n".join(lines) + "\n"


def include_files(db: Database, source: int = 0) -> list[str]:
    """Paths of the files the database recorded `` `define ``s from."""
    rows = db.sql("SELECT DISTINCT f.path FROM object o JOIN file f ON o.file_id = f.id "
                  "WHERE o.kind = 'macro' AND f.path IS NOT NULL ORDER BY f.path", (), source=source)
    return [p for (p,) in rows]


def macro_text(m: Object) -> str:
    params = m.detail.get("params")
    head = f"`define {m.name}"
    if params is not None:
        parts = []
        for p in params:
            d = p.get("default")
            parts.append(p["name"] + (f"={d['text'] if isinstance(d, dict) else d}" if d is not None else ""))
        head += "(" + ", ".join(parts) + ")"
    body = m.body
    return f"{head} {body}" if body else head


class _Gen:
    def __init__(self, db: Database, lines: list[str]):
        self.db = db
        self.lines = lines
        self.depth = 0
        #: Per database file: path -> (file it was first included from, line).
        self._included: dict[int, dict[str, tuple[str, int]]] = {}
        self._roots: dict[int, dict[str, int]] = {}
        #: Text of the variables already written in this scope (a declaration
        #: of several names is recorded once per name, with the same ``sig``).
        self._written: set[str] = set()

    def _stream_key(self, o: Object) -> tuple | None:
        """Where *o* falls in its compilation unit's text: by `` `include ``
        site, then line and column.  ``pos`` orders by line alone across the
        files of a package."""
        if o.loc is None or not o.loc.path:
            return None
        src = o.source
        if src not in self._included:
            inc: dict[str, tuple[str, int]] = {}
            for to, frm, line in self.db.sql(
                    "SELECT t.path, f.path, i.line FROM include i JOIN file t ON t.id = i.to_id "
                    "JOIN file f ON f.id = i.from_id ORDER BY i.seq", (), source=src):
                inc.setdefault(to, (frm, line))
            self._included[src] = inc
            self._roots[src] = {p: i for i, (p,) in enumerate(
                self.db.sql("SELECT path FROM file ORDER BY seq", (), source=src))}
        inc, roots = self._included[src], self._roots[src]
        key = [(o.loc.line, o.loc.col or 0)]
        path, seen = o.loc.path, set()
        while path in inc and path not in seen:
            seen.add(path)
            path, line = inc[path]
            key.append((line, 0))
        key.append((roots.get(path, 1 << 30), 0))
        return tuple(reversed(key))

    def ordered(self, members: list[Object]) -> list[Object]:
        """*members* in source order (one without a location stays after the
        member before it)."""
        keyed, last = [], ()
        for i, m in enumerate(members):
            k = self._stream_key(m)
            last = k if k is not None else last
            keyed.append((last, i, m))
        return [m for _k, _i, m in sorted(keyed, key=lambda t: (t[0], t[1]))]

    def emit(self, text: str) -> None:
        for line in text.split("\n"):
            self.lines.append("  " * self.depth + line)

    # -- scopes --------------------------------------------------------------

    def unit(self, u: Object) -> None:
        if u.kind == "package":
            self.emit(f"package {u.name};")
        else:
            self.emit(self.definition_header(u))
        self.depth += 1
        self.imports(u)
        members = self.db.members(u)
        if u.kind == "package":
            for m in members:
                if m.kind == "class":
                    self.emit(f"typedef class {m.name};")
        self.members(members, in_class=False)
        self.depth -= 1
        self.emit(_END[u.kind])

    def imports(self, scope: Object) -> None:
        for pkg, item, export in imports(self.db, scope):
            if export:
                self.emit(f"export {pkg}::{item};")
            else:
                self.emit(f"import {pkg}::{item};")

    def definition_header(self, u: Object) -> str:
        members = self.db.members(u)
        params = [self.parameter(p, header=True) for p in members
                  if p.kind == "parameter" and p.detail.get("port_list")]
        ports = [self.port(p) for p in members if p.kind == "port"]
        head = f"{u.kind} {u.name}"
        if params:
            head += " #(" + ", ".join(params) + ")"
        head += " (" + ", ".join(ports) + ");" if ports else ";"
        return head

    def port(self, p: Object) -> str:
        """An ANSI port declaration: its ``sig`` when that has a direction (or
        the port has none, as an interface port), else built from ``detail``."""
        text = _strip_comments(_strip_semicolon(p.sig or p.name))
        d = p.detail.get("dir")
        if not d or text.split(" ", 1)[0] in _DIRECTIONS:
            return text
        t = (p.detail.get("type") or {}).get("text", "")
        return " ".join(x for x in (d, t, text if text.endswith(p.name) else p.name) if x)

    def klass(self, c: Object) -> None:
        d = c.detail
        word = "interface class" if d.get("interface_class") else \
            "virtual class" if d.get("virtual") or "virtual" in c.quals else "class"
        members = self.db.members(c)
        params = [self.parameter(p, header=True) for p in members
                  if p.kind == "parameter" and p.detail.get("port_list")]
        head = f"{word} {c.name}"
        if params:
            head += " #(" + ", ".join(params) + ")"
        ext = d.get("extends")
        if ext:
            head += " extends " + ext["text"]
            args = d.get("extends_args")
            if args:
                head += " #(" + ", ".join(a["text"] for a in args) + ")"
        impl = d.get("implements")
        if impl:
            head += " implements " + ", ".join(i["text"] for i in impl)
        self.emit(head + ";")
        self.depth += 1
        self.imports(c)
        self.members(members, in_class=True)
        self.depth -= 1
        self.emit("endclass")

    def members(self, members: list[Object], in_class: bool) -> None:
        written, self._written = self._written, set()
        for m in self.ordered(members):
            k = m.kind
            if k == "class":
                self.klass(m)
            elif k == "typedef":
                self.emit(self.typedef(m))
            elif k == "parameter":
                if not m.detail.get("port_list"):
                    self.emit(self.parameter(m, header=False) + ";")
            elif k in ("variable", "net"):
                text = self.variable(m, in_class)
                if text:
                    self.emit(text)
            elif k in ("function", "task"):
                text = self.subroutine(m, in_class)
                if text:
                    self.emit(text)
            elif k == "modport" and m.sig:
                self.emit(_strip_semicolon(m.sig) + ";")
            elif k == "clocking":
                self.clocking(m)
        self._written = written

    # -- declarations ----------------------------------------------------------

    def parameter(self, p: Object, header: bool) -> str:
        d = p.detail
        if d.get("type_param"):
            text = f"type {p.name}"
            dt = d.get("default_type")
            if dt:
                text += f" = {dt['text']}"
        else:
            t = (d.get("type") or {}).get("text", "")
            text = f"{t} {p.name}".strip()
            default = d.get("default")
            if default:
                text += f" = {default['text']}"
        if header:
            return f"parameter {text}"
        return f"{'localparam' if d.get('local') else 'parameter'} {text}"

    def typedef(self, t: Object) -> str:
        sig = t.sig or ""
        if not sig.startswith("typedef"):
            text = (t.detail.get("type") or {}).get("text", "")
            sig = f"typedef {text} {t.name}"
        return self.expand(t, _strip_semicolon(sig)) + ";"

    def expand(self, o: Object, text: str) -> str:
        """*text* with an elided ``{ ... }`` rebuilt from *o*'s members."""
        if _ELIDED not in text:
            return text
        members = self.db.members(o)
        if any(m.kind == "enum_member" for m in members):
            seen: set[str] = set()
            items = []
            for m in members:
                if m.kind != "enum_member":
                    continue
                gen = m.detail.get("generated_from")
                if gen:
                    if gen not in seen:
                        seen.add(gen)
                        items.append(gen)
                    continue
                value = (m.detail.get("value") or {}).get("text")
                items.append(f"{m.name} = {value}" if value else m.name)
            body = "{ " + ", ".join(items) + " }"
        else:
            fields = [self.expand(m, _strip_semicolon(m.sig or m.name)) + ";"
                      for m in members if m.kind == "field"]
            body = "{ " + " ".join(fields) + " }"
        return text.replace(_ELIDED, body, 1)

    def variable(self, v: Object, in_class: bool) -> str | None:
        if not v.sig:
            return None
        text = _strip_comments(_strip_semicolon(v.sig))
        if text in self._written:
            return None
        self._written.add(text)
        stripped = _strip_words(text, _PROPERTY_WORDS)
        written = set(text[:len(text) - len(stripped)].split())
        text = stripped
        have = set(v.quals) | written
        quals = [q for q in ("local", "protected") if q in have and in_class]
        quals += [q for q in ("static", "randc" if "randc" in have else "rand", "const", "var", "automatic")
                  if q in have]
        if quals:
            text = " ".join(quals) + " " + text
        text = self.expand(v, text)
        init = v.detail.get("init")
        if init and "const" in v.quals and "=" not in text:
            text += f" = {init['text']}"
        return text + ";"

    def resolve_class(self, scope: Object, name: str) -> Object | None:
        """The class *name* as seen from the class *scope*: qualified, in
        *scope*'s package, or through that package's imports."""
        name = re.sub(r"\s+", "", name.split("#")[0])
        tries = [name] if "::" in name else []
        if "::" not in name:
            pkg = scope.qname.split("::")[0]
            tries.append(f"{pkg}::{name}")
            u = unit(self.db, pkg)
            if u is not None:
                for p, item, _export in imports(self.db, u):
                    if item in ("*", name):
                        tries.append(f"{p}::{name}")
        for q in tries:
            for o in self.db.by_qname(q):
                if o.kind == "class":
                    return o
        return None

    def super_new(self, s: Object) -> str | None:
        """``super.new(...)`` for the constructor *s* (§1.4): up to the base
        constructor's last argument without a default, the derived argument of
        the same name, else the default (an empty argument), else a constant
        of the argument's type.  Only the call's types are observable."""
        cls = self.db.parent(s)
        ext = (cls.detail.get("extends") or {}).get("text") if cls is not None else None
        if not ext:
            return None
        base = self.resolve_class(cls, ext)
        if base is None:
            return None
        base_new = next((m for m in self.db.members(base) if m.name == "new"), None)
        if base_new is None:
            return None
        names = {a["name"] for a in s.detail.get("args") or []}
        formals = base_new.detail.get("args") or []
        required = [i for i, a in enumerate(formals) if a.get("default") is None]
        actual = []
        for i, a in enumerate(formals[:required[-1] + 1] if required else []):
            if a["name"] in names:
                actual.append(a["name"])
            elif a.get("default") is not None:
                actual.append("")       # an empty argument takes the default
            else:
                t = a.get("type") or {}
                form, text = t.get("form"), t.get("text", "")
                actual.append("null" if form in ("class", "chandle", "virtual_interface") else
                              '""' if form == "string" else
                              f"{text}'(0)" if re.fullmatch(r"[A-Za-z_]\w*(::\w+)*", text) else "'0")
        return f"super.new({', '.join(actual)});"

    def subroutine(self, s: Object, in_class: bool) -> str | None:
        sig = s.sig or ""
        if not sig:
            return None
        word = "task" if s.kind == "task" else "function"
        sig = _strip_comments(_strip_semicolon(sig))
        text = _strip_words(sig, _METHOD_WORDS)
        written = set(sig[:len(sig) - len(text)].split())
        s_quals = set(s.quals) | written
        if s.detail.get("constructor"):
            text = re.sub(r"^function\s+void\s+new\b", "function new", text)
        text = _explicit_directions(text, s.name, s.detail.get("args") or [])
        quals = []
        if in_class:
            if "pure" in s_quals:
                quals += ["pure", "virtual"]        # slang: ``pure`` comes first
            quals += [q for q in ("local", "protected") if q in s_quals]
            if "static" in s_quals:
                quals.append("static")
            if "virtual" in s_quals and "pure" not in s_quals:
                quals.append("virtual")
        if quals:
            text = " ".join(quals) + " " + text
        dpi = s.detail.get("dpi") or {}
        spec = dpi.get("spec", "DPI-C")
        c_name = f"{dpi['c_name']} = " if dpi.get("c_name") and dpi["c_name"] != s.name else ""
        if dpi.get("dir") == "import":
            prop = " ".join(q for q in ("context", "pure") if dpi.get(q) or q in s_quals)
            return f'import "{spec}" {prop + " " if prop else ""}{c_name}{_strip_words(text, {"import"})};'
        if dpi.get("dir") == "export":
            return f'export "{spec}" {c_name}{word} {s.name};\n{text};\nend{word}'
        if "pure" in s_quals:
            return text + ";"
        call = self.super_new(s) if s.detail.get("constructor") else None
        if call:
            return f"{text};\n  {call}\nend{word}"
        return f"{text};\nend{word}"

    def clocking(self, c: Object) -> None:
        sig = _strip_semicolon(c.sig or f"clocking {c.name}")
        if c.detail.get("default") and not sig.startswith("default"):
            sig = "default " + sig
        self.emit(sig + ";")
        self.depth += 1
        for v in self.db.members(c):
            if v.kind == "clockvar":
                d = v.detail.get("dir", "input")
                self.emit(f"{d} {v.name};")
        self.depth -= 1
        self.emit("endclocking")


_DIRECTIONS = ("input", "output", "inout", "ref", "const")


def _explicit_directions(text: str, name: str, args: list[dict]) -> str:
    """*text* (a subroutine signature) with a direction on every argument: one
    left implicit after ``ref`` or ``output`` would inherit it."""
    m = re.search(r"\b" + re.escape(name) + r"\s*\(", text)
    if m is None or not args:
        return text
    start = m.end()
    pieces, depth, quote, cur = [], 0, False, start
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                pieces.append(text[cur:i])
                break
            depth -= 1
        elif ch == "," and depth == 0:
            pieces.append(text[cur:i])
            cur = i + 1
        i += 1
    else:
        return text
    if len(pieces) != len(args):
        return text
    fixed = []
    for piece, arg in zip(pieces, args):
        p = piece.strip()
        if p.split(" ", 1)[0] not in _DIRECTIONS:
            p = _argument(p, arg)
        fixed.append(p)
    return text[:start] + ", ".join(fixed) + text[i:]


def _argument(piece: str, arg: dict) -> str:
    """One formal argument written out in full: direction, type, name, the
    unpacked dimensions as written in *piece*, and the default.  A direction
    alone would turn an argument that inherits the previous one's type into
    ``logic``."""
    name, t = arg["name"], (arg.get("type") or {}).get("text")
    if not t:
        return f"{arg.get('dir') or 'input'} {piece}"
    m = re.search(r"\b" + re.escape(name) + r"\s*((?:\[[^\]]*\]\s*)*)", piece)
    dims = re.sub(r"\s+", "", m.group(1)) if m else ""
    if dims and t.replace(" ", "").endswith(dims):
        t = _drop_suffix(t, dims)
    direction = arg.get("dir") or "input"
    if arg.get("static"):
        direction += " static"
    text = f"{direction} {t} {name}{dims}"
    default = arg.get("default")
    if default:
        text += f" = {default['text']}"
    return text


def _drop_suffix(text: str, dims: str) -> str:
    """*text* without the unpacked dimensions *dims* (spaces ignored) the
    schema appends to a ``TypeRef`` after a space."""
    i, j = len(text), len(dims)
    while j > 0 and i > 0:
        i -= 1
        if text[i] == " ":
            continue
        j -= 1
    return text[:i].rstrip()


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_semicolon(text: str) -> str:
    return text.rstrip().rstrip(";").rstrip()


def _strip_words(text: str, words: set[str]) -> str:
    parts = text.split(" ")
    while parts and parts[0] in words:
        parts.pop(0)
    return " ".join(parts)
