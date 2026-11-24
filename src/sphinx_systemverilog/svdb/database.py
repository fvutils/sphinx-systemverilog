"""Read one or more ``.svdb`` files.

:class:`Database` opens files read-only and answers the queries of plan §8.2
with indexed SQL; nothing is loaded up front.  Several files *federate*: they
are searched in the order given, a key found in more than one is reported
once (:attr:`Database.duplicates`) and the first file wins, and references
that one file makes into another (a testbench into a VIP database) are
followed by name.

Every SQL statement the API runs is in :data:`QUERIES`, so that a test can
check each one's query plan for full-table scans (plan D1-TEST-4).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import SCHEMA_VERSION, canon, layout
from .issues import SvdbError

log = logging.getLogger("sphinx_systemverilog.svdb")

_COLS = ("o.id, o.ns, u.name, o.qname, o.name, o.kind, p.qname, s.qname, o.pos, f.fid, f.path, o.line, o.col,"
         " o.end_line, o.end_col, o.sig, o.quals, o.flags, g.name, o.url, o.hash, o.detail, o.extra")
_FROM = ("FROM object o LEFT JOIN unit u ON u.id = o.unit_id LEFT JOIN object p ON p.id = o.parent_id"
         " LEFT JOIN object s ON s.id = o.scope_id LEFT JOIN file f ON f.id = o.file_id"
         " LEFT JOIN origin g ON g.id = o.origin_id")
_OBJ = f"SELECT {_COLS} {_FROM}"
_BASE_ROLES = "('extends', 'implements')"

#: Every statement the read API runs, by name.
QUERIES: dict[str, str] = {
    "by_id": f"{_OBJ} WHERE o.id = ?",
    "by_qname": f"{_OBJ} WHERE o.qname = ?",
    "by_name": f"{_OBJ} WHERE o.name = ? LIMIT ?",
    "find": f"{_OBJ} WHERE o.qname GLOB ? ORDER BY o.qname LIMIT ?",
    "find_kind": f"{_OBJ} WHERE o.qname GLOB ? AND o.kind = ? ORDER BY o.qname LIMIT ?",
    "members": f"{_OBJ} WHERE o.parent_id = ? ORDER BY o.pos",
    "roots": f"{_OBJ} WHERE o.parent_id IS NULL ORDER BY o.pos",
    "count": "SELECT value FROM meta WHERE key = 'objects'",
    "diags": "SELECT rec FROM diag ORDER BY seq",
    "doc": "SELECT text, style, grp, loc FROM doc WHERE object_id = ?",
    "body": "SELECT text FROM body WHERE object_id = ?",
    "refs_from": ("SELECT role, pos, seq, head, name, target_qname, target_ns, target_unit, target_id"
                  " FROM ref WHERE src = 0 AND src_id = ? ORDER BY id"),
    "refs_to_id": "SELECT src_id, role, pos, name FROM ref WHERE target_id = ? AND src = 0 ORDER BY id",
    "refs_to_qname": ("SELECT src_id, role, pos, name, target_ns FROM ref"
                      " WHERE target_qname = ? AND target_id IS NULL AND src = 0 ORDER BY id"),
    "derived_id": (f"SELECT src_id FROM ref WHERE target_id = ? AND role IN {_BASE_ROLES}"
                   " AND head = 1 AND src = 0 ORDER BY id"),
    "derived_qname": (f"SELECT src_id, target_ns FROM ref WHERE target_qname = ? AND target_id IS NULL"
                      f" AND role IN {_BASE_ROLES} AND head = 1 AND src = 0 ORDER BY id"),
    "inst_children": "SELECT object_id FROM inst WHERE def_id = ?",
    "inst_used_by": "SELECT object_id FROM inst WHERE of_id = ?",
    "inst_used_by_name": "SELECT object_id FROM inst WHERE of_name = ? AND of_id IS NULL",
    "inst": "SELECT of_name, of_id, of_kind, state, array_count FROM inst WHERE object_id = ?",
    "connections": "SELECT pos, port, port_id, mode, dir, expr FROM port_conn WHERE inst_id = ? ORDER BY pos",
    "peers": "SELECT src_id, pos FROM ref WHERE target_id = ? AND role = 'conns.expr' AND src = 0 ORDER BY id",
    "elaborations": "SELECT id, rec FROM elab WHERE def_id = ? ORDER BY id",
    "elab_sites": "SELECT inst_id, child_elab_id FROM elab_site WHERE elab_id = ? ORDER BY pos",
    "elab_users": "SELECT elab_id, inst_id FROM elab_site WHERE child_elab_id = ?",
    "elab_by_id": "SELECT def_id, count, truncated FROM elab WHERE id = ?",
    "top_elab_for_def": "SELECT top.elab_id FROM top JOIN elab e ON e.id = top.elab_id WHERE e.def_id = ?",
    "elab_sites_full": "SELECT inst_id, present, count, child_elab_id FROM elab_site WHERE elab_id = ? ORDER BY pos",
}


@dataclass(frozen=True)
class Loc:
    """A source position: ``path`` (None if the file record is missing), 1-based ``line``/``col``."""

    path: str | None
    line: int
    col: int | None = None
    end_line: int | None = None
    end_col: int | None = None


@dataclass(frozen=True)
class Doc:
    """An object's raw documentation comment (``doc`` field)."""

    text: str
    style: str | None = None
    group: str | None = None
    loc: dict | None = None


@dataclass(eq=False)
class Object:
    """One ``object`` record, read from a database.

    The common fields of plan §5.1 are attributes; the kind-specific ones are
    in :attr:`detail`.  :attr:`doc` and :attr:`body` are read on first use.
    Two ``Object`` values are equal when they are the same row of the same
    file.
    """

    db: "Database" = field(repr=False)
    source: int = field(repr=False)
    id: int = field(repr=False)
    ns: str
    unit: str | None
    qname: str
    name: str
    kind: str
    parent: str | None
    scope: str | None
    pos: int
    loc: Loc | None
    sig: str | None
    quals: tuple[str, ...]
    flags: frozenset[str]
    origin: str | None
    url: str | None
    hash: str | None
    detail: dict[str, Any]
    #: Macro expansions that produced the object, outermost first (``via``).
    via: tuple[str, ...] = ()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Object) and (self.db, self.source, self.id) == (other.db, other.source, other.id)

    def __hash__(self) -> int:
        return hash((id(self.db), self.source, self.id))

    @property
    def key(self) -> canon.Key:
        """The identity ``(qname, ns, unit)``."""
        return canon.Key(self.qname, self.ns, self.unit if self.ns == "unit" else None)

    @property
    def path(self) -> str:
        """The database file this object was read from."""
        return self.db.paths[self.source]

    @property
    def doc(self) -> Doc | None:
        row = self.db._one(self.source, "doc", (self.id,))
        if row is None or row[0] is None:
            return None
        return Doc(row[0], row[1], row[2], json.loads(row[3]) if row[3] else None)

    @property
    def body(self) -> str | None:
        row = self.db._one(self.source, "body", (self.id,))
        return row[0] if row else None

    def members(self, kinds: Iterable[str] | None = None) -> list["Object"]:
        return self.db.members(self, kinds)


@dataclass(frozen=True)
class LinkStatus:
    """One ``links`` entry of an open file's header, checked against the
    files open with it (linking plan §1.6)."""

    #: The file whose header names the link.
    database: str
    origin: str
    #: Where the linked database was when *database* was written.
    path: str | None
    units: tuple[str, ...]
    #: ``ok``: open, same content; ``changed``: open, different content
    #: (relinking is due); ``missing``: no open file has that origin.
    state: str
    #: The open file of that origin, if any.
    open_path: str | None = None


@dataclass(frozen=True)
class Unresolved:
    """A reference whose target is not in any open database."""

    name: str
    target: str | None = None


@dataclass(frozen=True)
class Reference:
    """``source`` refers to an object under ``role`` (e.g. ``extends``, ``conns.expr``)."""

    source: Object
    role: str
    pos: int | None
    name: str


@dataclass(frozen=True)
class Connection:
    """One port connection of an instance (plan §5.2.1)."""

    pos: int
    port: str | None
    port_object: Object | None
    mode: str | None
    dir: str | None
    expr: str | None
    signals: tuple[Object | Unresolved, ...]


@dataclass(frozen=True)
class TreeNode:
    """One node of :meth:`Database.tree`'s elaborated instance tree.

    *instance* is the ``instance`` object at this site (``None`` at the
    root, which is the top-level elaboration itself); *definition* is the
    module/interface/program elaborated here (``None`` when the site's
    definition was never elaborated, so there is nothing to descend into).
    *count* is the site's multiplicity (an instance array or a generate
    loop); 1 at the root and for a plain instance.
    """

    definition: Object | None
    instance: Object | None
    count: int
    children: tuple["TreeNode", ...] = ()
    #: ``depth`` or ``cap`` stopped the walk at or below this node.
    truncated: bool = False


class AmbiguousKey(LookupError):
    """A name matches more than one object; ``candidates`` lists them."""

    def __init__(self, text: str, candidates: Sequence[Object]):
        self.candidates = list(candidates)
        names = ", ".join(canon.format_key(o.key, qualify=True) for o in self.candidates)
        super().__init__(f"{text!r} is ambiguous: {names}")


@dataclass
class _Source:
    path: str
    conn: sqlite3.Connection
    header: dict


def _connect_ro(path: str) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_file():
        raise SvdbError(f"{path}: no such database")
    return sqlite3.connect(p.absolute().as_uri() + "?mode=ro", uri=True, check_same_thread=False)


def file_hash(path: str) -> str | None:
    """SHA-256 of a file's bytes (``links[].hash``), or None if unreadable."""
    import hashlib

    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _origin(s: "_Source") -> str:
    """A file's label: its header ``origin``, else its file name without suffix."""
    return (s.header or {}).get("origin") or os.path.splitext(os.path.basename(s.path))[0]


def _unopened_links(sources: list["_Source"]) -> list[str]:
    """Paths of the databases *sources*' headers link to that none of them is."""
    have = {_origin(s) for s in sources} | {os.path.abspath(s.path) for s in sources}
    out: list[str] = []
    for s in sources:
        for lk in (s.header or {}).get("links") or ():
            if lk.get("origin") in have:
                continue
            recorded = lk.get("path") or ""
            for p in (recorded, os.path.join(os.path.dirname(os.path.abspath(s.path)), os.path.basename(recorded))):
                if p and os.path.isfile(p) and os.path.abspath(p) not in have:
                    out.append(p)
                    have.add(os.path.abspath(p))
                    have.add(lk.get("origin"))
                    break
    return out


def _check(path: str, conn: sqlite3.Connection) -> dict:
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
    except sqlite3.DatabaseError as e:
        raise SvdbError(f"{path}: not an svdb database ({e})") from None
    if meta.get("layout_version") != str(layout.LAYOUT_VERSION):
        raise SvdbError(f"{path}: database layout {meta.get('layout_version')} is not {layout.LAYOUT_VERSION};"
                        " re-import it from NDJSON")
    if str(meta.get("schema", "")).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SvdbError(f"{path}: schema {meta.get('schema')} is not supported")
    return json.loads(meta["header"])


class Database:
    """Read access to one or more svdb files, searched in order."""

    def __init__(self, sources: list[_Source]):
        self._sources = sources
        #: Keys found in more than one file, with the files, in order.
        self.duplicates: dict[str, list[str]] = {}
        self._links: list[LinkStatus] | None = None
        for st in self.links():
            if st.state == "changed":
                log.warning("svdb: %s was linked against a different %s (%s); rebuild it to relink",
                            st.database, st.origin, st.open_path)

    @classmethod
    def open(cls, paths: str | os.PathLike | Iterable[str | os.PathLike], *,
             follow_links: bool = False) -> "Database":
        """Open the database file(s) *paths*, read-only; earlier files take precedence.

        *follow_links* also opens, after them, each database a header ``links``
        to that no open file stands for: at its recorded path, else beside the
        file that names it."""
        if isinstance(paths, (str, os.PathLike)):
            paths = [paths]
        sources = []
        try:
            todo = [os.fspath(p) for p in paths]
            while todo:
                p = todo.pop(0)
                conn = _connect_ro(p)
                sources.append(_Source(p, conn, _check(p, conn)))
                if follow_links and not todo:
                    todo = _unopened_links(sources)
        except BaseException:
            for s in sources:
                s.conn.close()
            raise
        return cls(sources)

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection, name: str = ":memory:") -> "Database":
        """Wrap an open connection (an in-memory database from :class:`Writer`)."""
        conn.execute("PRAGMA query_only = 1")
        return cls([_Source(name, conn, _check(name, conn))])

    def close(self) -> None:
        for s in self._sources:
            s.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def paths(self) -> list[str]:
        return [s.path for s in self._sources]

    @property
    def headers(self) -> list[dict]:
        """The header record of each file, in order."""
        return [s.header for s in self._sources]

    def links(self) -> list[LinkStatus]:
        """Every open file's ``links``, each checked against the open files
        (by origin, then by content hash)."""
        if self._links is None:
            by_origin: dict[str, str] = {}
            for s in self._sources:
                by_origin.setdefault(_origin(s), s.path)
            out = []
            for s in self._sources:
                for lk in (s.header or {}).get("links") or ():
                    there = by_origin.get(lk.get("origin", ""))
                    if there is None:
                        state = "missing"
                    elif lk.get("hash") and lk["hash"] != file_hash(there):
                        state = "changed"
                    else:
                        state = "ok"
                    out.append(LinkStatus(s.path, lk.get("origin", ""), lk.get("path"),
                                          tuple(lk.get("units") or ()), state, there))
            self._links = out
        return self._links

    # -- plumbing ----------------------------------------------------------------

    def _rows(self, src: int, query: str, params: tuple) -> list[tuple]:
        return self._sources[src].conn.execute(QUERIES[query], params).fetchall()

    def _one(self, src: int, query: str, params: tuple):
        return self._sources[src].conn.execute(QUERIES[query], params).fetchone()

    def _object(self, src: int, row) -> Object:
        (oid, ns, unit, qname, name, kind, parent, scope, pos, _fid, path, line, col, end_line, end_col, sig, quals,
         flags, origin, url, digest, detail, extra) = row
        loc = Loc(path, line, col, end_line, end_col) if line is not None else None
        via = tuple(v["macro"] for v in json.loads(extra).get("via", ())) if extra else ()
        return Object(self, src, oid, ns, unit if ns == "unit" else None, qname, name, kind, parent, scope, pos, loc,
                      sig, tuple(json.loads(quals)) if quals else (), frozenset(layout.bits_to_flags(flags)),
                      origin, url, digest.hex() if digest else None, json.loads(detail) if detail else {}, via)

    def _by_id(self, src: int, oid: int) -> Object | None:
        row = self._one(src, "by_id", (oid,))
        return self._object(src, row) if row else None

    def _merge(self, found: Iterable[Object]) -> list[Object]:
        """First occurrence of each key wins; later ones are duplicates."""
        seen: dict[canon.Key, Object] = {}
        for o in found:
            first = seen.get(o.key)
            if first is None:
                seen[o.key] = o
            elif first.source != o.source:
                text = canon.format_key(o.key, qualify=True)
                paths = self.duplicates.setdefault(text, [first.path])
                if o.path not in paths:
                    paths.append(o.path)
                    log.warning("svdb: %s is defined in %s; using %s", text, ", ".join(paths), paths[0])
        return list(seen.values())

    # -- lookup ------------------------------------------------------------------

    def candidates(self, text: str) -> list[Object]:
        """Every object *text* can name: a key, a qname in any name space, a
        unique-or-not bare name, with ``.`` accepted for ``::``."""
        try:
            key = canon.parse_key(text)
        except canon.QNameError:
            if "." in text and not text.startswith("\\"):
                return self.candidates(text.replace(".", canon.SEP))
            return []
        found = []
        for src in range(len(self._sources)):
            for row in self._rows(src, "by_qname", (key.qname,)):
                o = self._object(src, row)
                if key.ns and o.ns != key.ns:
                    continue
                if key.unit and o.unit != key.unit:
                    continue
                found.append(o)
        if not found and key.ns is None and canon.SEP not in key.qname:
            for src in range(len(self._sources)):
                found.extend(self._object(src, row) for row in self._rows(src, "by_name", (key.qname, 100)))
        if not found and "." in text and not text.startswith("\\"):
            return self.candidates(text.replace(".", canon.SEP))
        return self._merge(found)

    def by_qname(self, qname: str) -> list[Object]:
        """Objects whose qname is exactly *qname*, in every name space and file."""
        return self._merge(self._object(src, r) for src in range(len(self._sources))
                           for r in self._rows(src, "by_qname", (qname,)))

    def by_name(self, name: str, limit: int | None = None) -> list[Object]:
        """Objects whose last name segment is *name* (at most *limit* per file)."""
        lim = -1 if limit is None else limit
        return self._merge(self._object(src, r) for src in range(len(self._sources))
                           for r in self._rows(src, "by_name", (name, lim)))

    def get(self, text: str) -> Object | None:
        """The object *text* names, or None.  Raises :class:`AmbiguousKey`
        when it names several (qualify it as ``ns:qname`` or ``$unit[id]::name``)."""
        found = self.candidates(text)
        if len(found) > 1:
            raise AmbiguousKey(text, found)
        return found[0] if found else None

    def find(self, pattern: str, *, kind: str | None = None, ns: str | None = None,
             limit: int | None = 1000) -> list[Object]:
        """Objects whose qname matches the GLOB *pattern*, in qname order.

        A pattern with a literal prefix (``axi_pkg::*``) is an index range
        scan; one starting with a wildcard reads the whole qname index.
        """
        lim = -1 if limit is None else limit
        found = []
        for src in range(len(self._sources)):
            if kind:
                rows = self._rows(src, "find_kind", (pattern, kind, lim))
            else:
                rows = self._rows(src, "find", (pattern, lim))
            found.extend(o for o in (self._object(src, r) for r in rows) if ns is None or o.ns == ns)
        found = sorted(self._merge(found), key=lambda o: (o.qname, o.ns))
        return found if limit is None else found[:limit]

    def parent(self, obj: Object) -> Object | None:
        """The structural parent of *obj*."""
        if obj.parent is None:
            return None
        rows = self._rows(obj.source, "by_qname", (obj.parent,))
        for row in rows:
            o = self._object(obj.source, row)
            if o.ns == obj.ns and o.unit == obj.unit:
                return o
        return None

    def members(self, obj: Object, kinds: Iterable[str] | None = None) -> list[Object]:
        """The children of *obj* in source order, optionally only of *kinds*."""
        want = set(kinds) if kinds is not None else None
        out = [self._object(obj.source, r) for r in self._rows(obj.source, "members", (obj.id,))]
        return [o for o in out if want is None or o.kind in want]

    def roots(self) -> list[Object]:
        """Every object without a parent, file by file, in ``pos`` order."""
        return self._merge(self._object(src, r) for src in range(len(self._sources))
                           for r in self._rows(src, "roots", ()))

    def __len__(self) -> int:
        """The number of objects, counted per file (duplicates included)."""
        return sum(int((self._one(src, "count", ()) or (0,))[0]) for src in range(len(self._sources)))

    def diagnostics(self, source: int = 0) -> list[dict]:
        """The ``diag`` records of file number *source*, in order."""
        return [json.loads(r[0]) for r in self._rows(source, "diags", ())]

    # -- references --------------------------------------------------------------

    def _target(self, src: int, name: str, tq: str | None, tns: str | None, tunit: str | None,
                tid: int | None) -> Object | Unresolved:
        if tid is not None:
            o = self._by_id(src, tid)
            if o is not None:
                return o
        if tq:
            found = [o for o in self.candidates(canon.format_key(canon.Key(tq, tns, tunit), qualify=bool(tns)))
                     if o.qname == tq]
            if found:
                return found[0]
            return Unresolved(name, canon.format_key(canon.Key(tq, tns, tunit), qualify=bool(tns)))
        return Unresolved(name)

    def bases(self, obj: Object) -> list[Object | Unresolved]:
        """What *obj* extends and implements, in declaration order."""
        rows = self._rows(obj.source, "refs_from", (obj.id,))
        rows = [r for r in rows if r[0] in ("extends", "implements") and r[3]]
        rows.sort(key=lambda r: (r[0] != "extends", r[1] or 0))
        return [self._target(obj.source, r[4], r[5], r[6], r[7], r[8]) for r in rows]

    def derived(self, obj: Object, *, transitive: bool = False) -> list[Object]:
        """Objects that extend or implement *obj* (directly, or at any depth)."""
        out: list[Object] = []
        seen = {(obj.source, obj.id)}
        todo = [obj]
        while todo:
            cur = todo.pop(0)
            for src in range(len(self._sources)):
                if src == cur.source:
                    ids = [r[0] for r in self._rows(src, "derived_id", (cur.id,))]
                else:
                    ids = [r[0] for r in self._rows(src, "derived_qname", (cur.qname,)) if r[1] in (None, cur.ns)]
                for oid in ids:
                    if (src, oid) in seen:
                        continue
                    seen.add((src, oid))
                    o = self._by_id(src, oid)
                    if o is not None:
                        out.append(o)
                        if transitive:
                            todo.append(o)
        return out

    def references(self, obj: Object, roles: Iterable[str] | None = None) -> list[Reference]:
        """Every object that refers to *obj*, with the role of the reference."""
        want = set(roles) if roles is not None else None
        out = []
        for src in range(len(self._sources)):
            if src == obj.source:
                rows = [(r[0], r[1], r[2], r[3]) for r in self._rows(src, "refs_to_id", (obj.id,))]
            else:
                rows = [(r[0], r[1], r[2], r[3]) for r in self._rows(src, "refs_to_qname", (obj.qname,))
                        if r[4] in (None, obj.ns)]
            for oid, role, pos, name in rows:
                if want is not None and role not in want:
                    continue
                o = self._by_id(src, oid)
                if o is not None:
                    out.append(Reference(o, role, pos, name))
        return out

    # -- structure (plan §8.2; D3c adds the elaborated tree) -----------------------

    def instances(self, definition: Object) -> list[Object]:
        """The instance objects declared in *definition* (at any generate depth)."""
        ids = [r[0] for r in self._rows(definition.source, "inst_children", (definition.id,))]
        return sorted((o for o in (self._by_id(definition.source, i) for i in ids) if o), key=lambda o: o.qname)

    def used_by(self, definition: Object) -> list[Object]:
        """Instances of *definition*, in every open database."""
        out = []
        for src in range(len(self._sources)):
            if src == definition.source:
                ids = [r[0] for r in self._rows(src, "inst_used_by", (definition.id,))]
            else:
                ids = [r[0] for r in self._rows(src, "inst_used_by_name", (definition.qname,))]
            out.extend(o for o in (self._by_id(src, i) for i in ids) if o)
        return out

    def connections(self, inst: Object) -> list[Connection]:
        """The port connections of the instance *inst*, in order."""
        sigs: dict[int, list] = {}
        for r in self._rows(inst.source, "refs_from", (inst.id,)):
            if r[0] == "conns.expr":
                sigs.setdefault(r[1], []).append(self._target(inst.source, r[4], r[5], r[6], r[7], r[8]))
        out = []
        for i, (pos, port, port_id, mode, d, expr) in enumerate(self._rows(inst.source, "connections", (inst.id,))):
            port_obj = self._by_id(inst.source, port_id) if port_id is not None else None
            out.append(Connection(pos, port, port_obj, mode, d, expr, tuple(sigs.get(i, ()))))
        return out

    def peers(self, signal: Object) -> list[tuple[Object, Connection]]:
        """Every (instance, connection) whose connection expression names *signal*."""
        out = []
        for oid, pos in self._rows(signal.source, "peers", (signal.id,)):
            inst = self._by_id(signal.source, oid)
            if inst is None:
                continue
            conns = self.connections(inst)
            if pos is not None and pos < len(conns):
                out.append((inst, conns[pos]))
        return out

    def elaborations(self, definition: Object) -> list[dict]:
        """The ``elab`` records of *definition* (one per parameter set)."""
        return [json.loads(rec) for _id, rec in self._rows(definition.source, "elaborations", (definition.id,))]

    def uvm_tree(self, root: str | None = None, *, name: str = "uvm_test_top",
                 include_conditional: bool = True, max_nodes: int = 5000):
        """The UVM component tree a simulation would build from *root*.

        *root* is a component class (qualified or bare name); ``None`` takes
        the first ``uvm.root`` record.  Stitched from every source's per-class
        records, following factory overrides as IEEE 1800.2's factory does
        (:mod:`.uvm_tree`).  Raises :class:`LookupError` when there is no root.
        """
        from .uvm_tree import UvmTreeIssue, stitch

        tree = stitch(self, root, name=name, include_conditional=include_conditional, max_nodes=max_nodes)
        missing = [lk for lk in self.links() if lk.state == "missing"]
        if missing:
            # Name the database a missing type was linked from (§1.6).
            where = {u: lk for lk in missing for u in lk.units}
            issues = []
            for i in tree.issues:
                lk = where.get(i.message.split(" ", 1)[0].split("::", 1)[0]) if i.code == "unknown_type" else None
                if lk is not None:
                    i = UvmTreeIssue(i.code, f"{i.message}; it was linked from {lk.origin}"
                                     f" ({lk.path or 'path unknown'}), which is not open", i.path, i.loc)
                issues.append(i)
            tree.issues = issues
        return tree

    def tree(self, top: Object, *, depth: int | None = None, cap: int = 5000) -> "TreeNode":
        """The elaborated instance tree rooted at *top* (plan §5.3, D3c-IMPL-2).

        Reads ``elab``/``elab_site`` only -- the walk already happened, when
        the database was built. *top* is a design element (a module,
        interface or program); its ``top`` record's elaboration is used when
        it has one, else its first ``elab``. ``depth`` stops recursion that
        many levels below the root (``None``: unbounded); *cap* stops the
        whole walk after that many nodes, root included, marking the node
        where the budget ran out ``truncated`` -- a safety net, since the
        front end already applied its own instance-count ceiling.

        Not covered yet (D3c-IMPL-2 follow-up, with the records themselves):
        a site inside a generate arm that was never taken, and which arm of a
        generate construct a given elaboration took.
        """
        row = self._one(top.source, "top_elab_for_def", (top.id,))
        elab_id = row[0] if row else None
        if elab_id is None:
            rows = self._rows(top.source, "elaborations", (top.id,))
            elab_id = rows[0][0] if rows else None
        if elab_id is None:
            return TreeNode(definition=top, instance=None, count=1, children=(), truncated=False)
        budget = [cap]
        return self._tree_node(top.source, elab_id, top, None, 1, depth, budget)

    def _tree_node(self, src: int, elab_id: int, definition: Object | None, instance: Object | None,
                   count: int, depth: int | None, budget: list[int]) -> "TreeNode":
        budget[0] -= 1
        if budget[0] < 0 or depth == 0:
            return TreeNode(definition, instance, count, (), truncated=True)
        children = []
        truncated = False
        for inst_id, present, site_count, child_elab_id in self._rows(src, "elab_sites_full", (elab_id,)):
            if not present:
                continue
            inst_obj = self._by_id(src, inst_id) if inst_id is not None else None
            if child_elab_id is None:
                children.append(TreeNode(None, inst_obj, site_count or 1, (), truncated=False))
                continue
            crow = self._one(src, "elab_by_id", (child_elab_id,))
            child_def = self._by_id(src, crow[0]) if crow and crow[0] is not None else None
            if budget[0] <= 0:
                children.append(TreeNode(child_def, inst_obj, site_count or 1, (), truncated=True))
                truncated = True
                continue
            next_depth = None if depth is None else depth - 1
            children.append(self._tree_node(src, child_elab_id, child_def, inst_obj, site_count or 1,
                                             next_depth, budget))
        return TreeNode(definition, instance, count, tuple(children), truncated=truncated)

    # -- escape hatch ------------------------------------------------------------

    def connection(self, source: int = 0) -> sqlite3.Connection:
        """The read-only connection to file number *source*."""
        return self._sources[source].conn

    def record(self, obj: Object) -> dict:
        """The ``object`` record of *obj*, as an export would write it."""
        from .exporter import object_record

        return object_record(self._sources[obj.source].conn, obj.id)

    def sql(self, query: str, params: Sequence[Any] = (), *, source: int = 0) -> list[tuple]:
        """Run a read-only SQL *query* against one file (plan §7 layout)."""
        return self._sources[source].conn.execute(query, tuple(params)).fetchall()
