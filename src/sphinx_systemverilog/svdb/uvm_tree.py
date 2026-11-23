"""The UVM component tree, stitched from per-class records (stitching plan §3.3).

A database records each component class on its own: the creates, overrides
and connections it writes, and the helper calls between its functions
(``uvm.type``/``uvm.child``/``uvm.conn``/``uvm.override``).  :func:`stitch`
puts those back together into the tree a simulation would build, from a root
test type, following the factory as UVM's does (IEEE 1800.2, as implemented
by ``uvm_default_factory``):

* the build is top-down and depth-first, each component's children built in
  name order;
* a component's ``build_phase`` (and the helpers it calls, :mod:`.uvm_inline`)
  registers overrides and creates children in the order written, and a
  child's constructor registers its overrides when the child is created;
* type overrides are kept newest first: one for a type already overridden
  rewrites that entry, unless it passed ``replace=0``, when it is ignored;
* inst overrides are kept in registration order and the first that matches
  wins, ahead of any type override; a path with a wildcard matches as a glob;
* the type an override produces is looked up again, so overrides chain, and a
  loop stops at the type asked for.

Several databases can be stitched together (a VIP in one, the testbench in
another): classes are keyed by qualified name across all of them.

Pure Python over records: no pyslang, no Sphinx.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Iterable

from .uvm_inline import CONNECT_PHASE, CONSTRUCTOR, run

FORMAT = "svdb-uvm-tree"
VERSION = 1

#: The name ``run_test`` gives the test component.
DEFAULT_NAME = "uvm_test_top"
DEFAULT_MAX_NODES = 5000
DEFAULT_MAX_DEPTH = 32

BUILD_PHASE = "build_phase"

#: Override statuses (:attr:`UvmTreeOverride.status`).
APPLIED = "applied"
UNUSED = "unused"
UNPLACED = "unplaced"
UNKNOWN_TYPE = "unknown_type"
UNAPPLIED = "unapplied"

STATE_OK = "ok"
STATE_OPAQUE = "opaque"
STATE_UNRESOLVED = "unresolved"


# -- output ------------------------------------------------------------------------


@dataclass(frozen=True)
class UvmTreePort:
    name: str
    role: str = "port"
    link: str = "tlm"


@dataclass(frozen=True)
class UvmVia:
    """One override that changed a node's type."""

    kind: str
    #: Path of the component that registered it, or the owner as written for a
    #: global one (a module).
    owner: str
    replacement: str
    loc: dict | None = None


@dataclass
class UvmNode:
    """One component instance."""

    path: str
    name: str
    #: Path of the parent, or ``None`` for the root.
    parent: str | None = None
    handle: str = ""
    #: Key of the type the create names.
    declared: str = ""
    #: Key of the type built, after factory overrides.
    type: str = ""
    #: The overrides that turned :attr:`declared` into :attr:`type`, in order.
    via: tuple[UvmVia, ...] = ()
    tier: str = ""
    created_by: str = "factory"
    conditional: bool = False
    multiplicity: str = "1"
    state: str = STATE_OK
    ports: tuple[UvmTreePort, ...] = ()
    #: Where the create is written.
    loc: dict | None = None
    #: Paths of the children, in build (name) order.
    children: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UvmLinkEnd:
    path: str
    port: str = ""


@dataclass(frozen=True)
class UvmLink:
    """One connection between two instances."""

    source: UvmLinkEnd
    target: UvmLinkEnd
    kind: str = "tlm"
    #: Path of the component whose ``connect_phase`` makes it.
    owner: str = ""
    conditional: bool = False
    #: ``"N"`` when it stands for a loop's worth of links.
    multiplicity: str = "1"
    #: ``"ok"``, or ``"unresolved"`` when an endpoint names no instance.
    state: str = STATE_OK
    #: The endpoints as written, relative to :attr:`owner`.
    text: str = ""
    loc: dict | None = None


@dataclass
class UvmTreeOverride:
    """One override record, and what became of it in this tree."""

    original: str
    replacement: str
    kind: str = "type"
    inst_path: str | None = ""
    path_base: str = ""
    replace: bool = True
    #: Key of the class (or module) that writes it, and the function it is in.
    owner: str = ""
    method: str = ""
    conditional: bool = False
    status: str = UNPLACED
    #: Paths of the components that registered it (empty for a global one).
    registered_by: list[str] = field(default_factory=list)
    #: Paths of the nodes it changed the type of.
    applied_to: list[str] = field(default_factory=list)
    loc: dict | None = None


@dataclass(frozen=True)
class UvmTreeIssue:
    code: str
    message: str
    path: str = ""
    loc: dict | None = None


@dataclass
class UvmTree:
    sources: list[str]
    root: UvmNode | None
    #: Every node, in preorder (each parent before its children, children in
    #: name order).
    nodes: list[UvmNode]
    links: list[UvmLink]
    overrides: list[UvmTreeOverride]
    issues: list[UvmTreeIssue]
    truncated: bool = False

    def node(self, path: str) -> UvmNode | None:
        return self._by_path().get(path)

    def _by_path(self) -> dict[str, UvmNode]:
        return {n.path: n for n in self.nodes}

    def to_json(self, nested: bool = False) -> dict:
        """The tree as ``svdb-uvm-tree`` JSON; *nested* nests ``children``."""
        out: dict[str, Any] = {"format": FORMAT, "version": VERSION, "sources": list(self.sources)}
        if self.root is not None:
            out["root"] = {"name": self.root.name, "type": self.root.type}
        nodes = [_node_json(n) for n in self.nodes]
        if nested:
            by_path = {n["path"]: n for n in nodes}
            for n in nodes:
                n.pop("parent", None)
            for node in self.nodes:
                kids = [by_path[p] for p in node.children if p in by_path]
                if kids:
                    by_path[node.path]["children"] = kids
            out["nodes"] = [by_path[self.root.path]] if self.root is not None else []
        else:
            out["nodes"] = nodes
        out["links"] = [_link_json(k) for k in self.links]
        out["overrides"] = [_override_json(o) for o in self.overrides]
        out["issues"] = [_drop_empty({"code": i.code, "message": i.message, "path": i.path, "loc": i.loc})
                         for i in self.issues]
        if self.truncated:
            out["truncated"] = True
        return out

    def dumps(self, nested: bool = False) -> str:
        return json.dumps(self.to_json(nested), indent=2)


def _drop_empty(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], (), {}, False)}


def _node_json(n: UvmNode) -> dict:
    out = {"path": n.path, "parent": n.parent, "name": n.name, "handle": n.handle,
           "declared": n.declared if n.declared != n.type else "", "type": n.type,
           "via": [_drop_empty({"kind": v.kind, "owner": v.owner, "replacement": v.replacement,
                                "loc": v.loc}) for v in n.via],
           "tier": n.tier, "created_by": n.created_by if n.created_by != "factory" else "",
           "conditional": n.conditional, "multiplicity": n.multiplicity if n.multiplicity != "1" else "",
           "state": n.state if n.state != STATE_OK else "",
           "ports": [_drop_empty({"name": p.name, "role": p.role, "link": p.link}) for p in n.ports],
           "loc": n.loc}
    return _drop_empty(out)


def _link_json(k: UvmLink) -> dict:
    return _drop_empty({
        "source": _drop_empty({"path": k.source.path, "port": k.source.port}),
        "target": _drop_empty({"path": k.target.path, "port": k.target.port}),
        "kind": k.kind, "owner": k.owner, "conditional": k.conditional,
        "multiplicity": k.multiplicity if k.multiplicity != "1" else "",
        "state": k.state if k.state != STATE_OK else "",
        "text": k.text if k.state != STATE_OK else "", "loc": k.loc})


def _override_json(o: UvmTreeOverride) -> dict:
    out = _drop_empty({
        "original": o.original, "replacement": o.replacement, "kind": o.kind,
        "inst_path": o.inst_path, "path_base": o.path_base, "owner": o.owner, "method": o.method,
        "conditional": o.conditional, "status": o.status, "registered_by": o.registered_by,
        "applied_to": o.applied_to, "loc": o.loc})
    if o.kind == "inst" and o.inst_path is None:
        out["inst_path"] = None
    if not o.replace:
        out["replace"] = False
    return out


# -- loading -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Call:
    step: int
    method: str
    super: bool = False
    conditional: bool = False
    multiplicity: str = "1"


@dataclass(frozen=True)
class _Method:
    name: str
    virtual: bool = False
    calls: tuple[_Call, ...] = ()


@dataclass
class _Type:
    key: str
    name: str
    base: str = ""
    tier: str = ""
    kind: str = "component"
    abstract: bool = False
    ports: tuple[UvmTreePort, ...] = ()
    methods: dict[str, _Method] = field(default_factory=dict)

    def method(self, name: str) -> _Method | None:
        return self.methods.get(name)


@dataclass
class _Item:
    """A create, connection or override as one class writes it."""

    kind: str  # "child", "conn" or "override"
    rec: dict
    method: str
    step: int | None
    conditional: bool = False
    multiplicity: str = "1"
    loc: dict | None = None
    #: For an override, its :class:`UvmTreeOverride` (shared by every
    #: registration of it).
    override: UvmTreeOverride | None = None


def _canon(rec: dict) -> str:
    """A record without its source location, to compare across databases."""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if k != "loc"}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v
    return json.dumps(strip(rec), sort_keys=True)


class _Index:
    """Every class's records across the sources of a database, by key.

    Also the :class:`~.uvm_inline.ClassModel` the ``run`` rule reads.
    """

    def __init__(self, sources: list[tuple[str, dict, list[dict]]]) -> None:
        """*sources*: ``(name, {file id: path}, uvm records)`` per source, in
        lookup order."""
        self.sources = [name for name, _, _ in sources]
        self.types: dict[str, _Type] = {}
        self.items: dict[tuple[str, str], list[_Item]] = {}
        self.overrides: list[tuple[_Item, str]] = []  # (item, owner key), record order
        self.roots: list[dict] = []
        self.issues: list[UvmTreeIssue] = []
        self._by_name: dict[str, list[str]] = {}
        seen: dict[str, tuple[int, str]] = {}
        for src, (_, paths, rows) in enumerate(sources):
            self._load(paths, rows, src, seen)
        for key, t in self.types.items():
            self._by_name.setdefault(t.name, []).append(key)

    def _load(self, paths: dict, rows: list[dict], src: int, seen: dict[str, tuple[int, str]]) -> None:
        def loc(rec: dict) -> dict | None:
            at = rec.get("loc")
            if not at:
                return None
            out = {"file": paths.get(at["file"], at["file"]), "line": at["line"]}
            if at.get("col"):
                out["col"] = at["col"]
            return out

        # One class's records together, to compare with another source's.
        bundles: dict[str, list[dict]] = {}
        for rec in rows:
            r = rec["r"]
            if r == "uvm.type":
                bundles.setdefault(_key(rec["type"]), []).insert(0, rec)
            elif r in ("uvm.child", "uvm.conn"):
                bundles.setdefault(_key(rec["owner"]), []).append(rec)
            elif r == "uvm.root":
                self.roots.append(rec)

        taken: set[str] = set()
        for key, recs in bundles.items():
            text = "\n".join(_canon(r) for r in recs)
            if key in seen:
                first_src, first_text = seen[key]
                if first_text != text:
                    self.issues.append(UvmTreeIssue(
                        "ambiguous_type",
                        f"{key} is recorded differently in {self.sources[first_src]} and "
                        f"{self.sources[src]}; using {self.sources[first_src]}"))
                continue
            seen[key] = (src, text)
            taken.add(key)
            for rec in recs:
                if rec["r"] == "uvm.type":
                    self.types[key] = _type(rec)
                else:
                    method = rec.get("method", BUILD_PHASE if rec["r"] == "uvm.child" else CONNECT_PHASE)
                    self.items.setdefault((key, method), []).append(_Item(
                        "child" if rec["r"] == "uvm.child" else "conn", rec, method, rec.get("step"),
                        bool(rec.get("conditional")), rec.get("multiplicity", "1"), loc(rec)))

        for rec in rows:
            if rec["r"] != "uvm.override":
                continue
            owner = rec.get("owner") or {}
            owner_key = _key(owner) if owner else ""
            # An override written by a class another source already supplied
            # is that source's.
            if owner_key in seen and owner_key not in taken:
                continue
            o = UvmTreeOverride(
                original=_key(rec["original"]), replacement=_key(rec["replacement"]),
                kind=rec.get("kind", "type"), inst_path=rec.get("inst_path", ""),
                path_base=rec.get("path_base", ""), replace=rec.get("replace", True),
                owner=owner_key, method=rec.get("method", ""),
                conditional=bool(rec.get("conditional")), loc=loc(rec))
            if rec.get("unknown"):
                o.status = UNKNOWN_TYPE
            item = _Item("override", rec, o.method, rec.get("step"), o.conditional, "1", o.loc, o)
            self.overrides.append((item, owner_key))

    def finish(self) -> None:
        """File each override under its class, once types are all loaded."""
        resolved = []
        for item, owner_key in self.overrides:
            o = item.override
            o.original = self.resolve(o.original)
            o.replacement = self.resolve(o.replacement)
            # Ref.target is optional: a producer may name the owner bare.
            owner_key = o.owner = self.resolve(owner_key) if owner_key else ""
            resolved.append((item, owner_key))
            if owner_key in self.types:
                self.items.setdefault((owner_key, item.method), []).append(item)
        self.overrides = resolved

    def resolve(self, name: str) -> str:
        """The key for a type written as *name* (a key already, or a bare name)."""
        if name in self.types or "::" in name:
            return name
        keys = self._by_name.get(name, [])
        return keys[0] if keys else name

    # -- ClassModel --

    def type(self, key: str) -> _Type | None:
        return self.types.get(key)

    def base(self, key: str) -> str | None:
        t = self.types.get(key)
        return t.base if t is not None and t.base else None

    def items_of(self, key: str, method: str) -> list[_Item]:
        found = list(self.items.get((key, method), ()))
        found.sort(key=lambda i: float("inf") if i.step is None else i.step)
        return found


class _Model:
    """:class:`~.uvm_inline.ClassModel` over an :class:`_Index`."""

    def __init__(self, index: _Index) -> None:
        self._i = index

    def type(self, key: str) -> _Type | None:
        return self._i.type(key)

    def base(self, key: str) -> str | None:
        return self._i.base(key)

    def items(self, key: str, method: str) -> list[_Item]:
        return self._i.items_of(key, method)


def _key(ref: dict) -> str:
    name = ref.get("name", "")
    return ref.get("target") or ("" if name == "$unknown" else name)


def _type(rec: dict) -> _Type:
    methods = {}
    for name, m in (rec.get("methods") or {}).items():
        methods[name] = _Method(name, bool(m.get("virtual")), tuple(
            _Call(c["step"], c["method"], bool(c.get("super")), bool(c.get("conditional")),
                  c.get("multiplicity", "1")) for c in m.get("calls", ())))
    ports = tuple(UvmTreePort(p["name"], p.get("role", "port"), p.get("link", "tlm"))
                  for p in rec.get("ports", ()))
    base = rec.get("base") or {}
    return _Type(key=_key(rec["type"]), name=rec["type"].get("name", ""), base=_key(base) if base else "",
                 tier=rec.get("tier", ""), kind=rec.get("kind", "component"),
                 abstract=bool(rec.get("abstract")), ports=ports, methods=methods)


# -- the factory -------------------------------------------------------------------


@dataclass
class _Entry:
    original: str
    replacement: str
    replace: bool
    override: UvmTreeOverride
    registered_by: str
    #: Inst overrides: the full path pattern.
    path: str = ""


class _Factory:
    """``uvm_default_factory``'s override tables and lookup."""

    def __init__(self, issues: list[UvmTreeIssue]) -> None:
        self.types: list[_Entry] = []  # newest first
        self.insts: list[_Entry] = []  # registration order
        self.issues = issues

    def register(self, o: UvmTreeOverride, owner_path: str) -> None:
        if owner_path and owner_path not in o.registered_by:
            o.registered_by.append(owner_path)
        if o.status == UNKNOWN_TYPE:
            return
        if o.kind == "inst":
            if o.inst_path is None or o.path_base not in ("owner", "absolute"):
                o.status = UNAPPLIED
                return
            if o.path_base == "owner":
                path = f"{owner_path}.{o.inst_path}" if o.inst_path else owner_path
            else:
                path = o.inst_path
            self.insts.append(_Entry(o.original, o.replacement, True, o, owner_path, path))
            _registered(o)
            return
        for entry in self.types:
            if entry.original == o.original:
                if not o.replace:
                    # TPREGD: an override for this type exists already
                    _registered(o)
                    self.issues.append(UvmTreeIssue(
                        "override_ignored",
                        f"{o.original} -> {o.replacement} passed replace=0 and {o.original} is "
                        f"already overridden (to {entry.replacement})", owner_path, o.loc))
                    return
                # TPREGR: rewritten in place
                entry.replacement, entry.replace, entry.override = o.replacement, o.replace, o
                entry.registered_by = owner_path
                _registered(o)
                return
        self.types.insert(0, _Entry(o.original, o.replacement, o.replace, o, owner_path))
        _registered(o)

    def resolve(self, requested: str, path: str) -> tuple[str, list[_Entry]]:
        """``(type, entries applied)`` for ``create`` of *requested* at *path*."""
        used: list[_Entry] = []
        current = requested
        for _ in range(64):
            entry = self._find(current, path)
            if entry is None or entry.replacement == current:
                return current, used
            if any(u.original == entry.replacement for u in used) or entry.replacement == requested:
                self.issues.append(UvmTreeIssue(
                    "override_loop", f"overrides of {requested} loop back to it; {requested} is built",
                    path, entry.override.loc))
                return requested, []
            used.append(entry)
            current = entry.replacement
        return current, used

    def _find(self, requested: str, path: str) -> _Entry | None:
        for entry in self.insts:
            if entry.original == requested and _path_matches(entry.path, path):
                return entry
        found = None
        for entry in self.types:
            if entry.original == requested and (found is None or not found.replace):
                found = entry
                if found.replace:
                    break
        return found


def _registered(o: UvmTreeOverride) -> None:
    if o.status == UNPLACED:
        o.status = UNUSED


def _path_matches(pattern: str, path: str) -> bool:
    """``uvm_is_match`` for a pattern with a wildcard, equality otherwise."""
    if "*" in pattern or "?" in pattern:
        return pattern == "*" or fnmatchcase(path, pattern)
    return pattern == path


# -- stitching ---------------------------------------------------------------------


def stitch(db: Any, root: str | None = None, *, name: str = DEFAULT_NAME,
           include_conditional: bool = True, max_nodes: int = DEFAULT_MAX_NODES,
           max_depth: int = DEFAULT_MAX_DEPTH) -> UvmTree:
    """The component tree from *root* (a type key or bare name) in *db*.

    *root* ``None`` takes the first ``uvm.root`` record; with none, a
    :class:`LookupError` names the component types that could be roots.
    """
    return _stitch(_Index(_db_sources(db)), root, name, include_conditional, max_nodes, max_depth)


def stitch_records(records: Iterable[dict], root: str | None = None, *, source: str = "",
                   name: str = DEFAULT_NAME, include_conditional: bool = True,
                   max_nodes: int = DEFAULT_MAX_NODES, max_depth: int = DEFAULT_MAX_DEPTH) -> UvmTree:
    """As :func:`stitch`, from ``uvm.*`` records not yet in a database (the
    Sphinx extension's, for ``sv:uvm-tree :resolved:``). A record's
    ``loc.file`` is the path itself; *source* names the records in
    :attr:`UvmTree.sources`."""
    rows = [rec for rec in records if rec.get("r", "").startswith("uvm.")]
    return _stitch(_Index([(source, {}, rows)]), root, name, include_conditional, max_nodes, max_depth)


def _db_sources(db: Any) -> list[tuple[str, dict, list[dict]]]:
    out = []
    for src, path in enumerate(db.paths):
        conn = db.connection(src)
        try:
            paths = dict(conn.execute("SELECT fid, path FROM file"))
            rows = [json.loads(rec) for (rec,) in conn.execute("SELECT rec FROM uvm ORDER BY seq")]
        except Exception:
            paths, rows = {}, []
        out.append((path, paths, rows))
    return out


def _stitch(index: _Index, root: str | None, name: str, include_conditional: bool,
            max_nodes: int, max_depth: int) -> UvmTree:
    index.finish()
    return _Stitcher(index, include_conditional, max_nodes, max_depth).stitch(root, name)


class _Stitcher:
    def __init__(self, index: _Index, include_conditional: bool, max_nodes: int, max_depth: int) -> None:
        self.index = index
        self.model = _Model(index)
        self.include_conditional = include_conditional
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.issues: list[UvmTreeIssue] = list(index.issues)
        self.factory = _Factory(self.issues)
        self.nodes: dict[str, UvmNode] = {}
        self.truncated = False
        #: ``(class key, method)`` of every function a build-time run reached.
        self.reached: set[tuple[str, str]] = set()

    # -- the tree --

    def stitch(self, root: str | None, name: str) -> UvmTree:
        root_key = self._root(root)
        for item, owner_key in self.index.overrides:
            if not item.method and owner_key not in self.index.types:
                self._register(item, "")
        actual, used = self.factory.resolve(root_key, name)
        top = self._node(path=name, name=name, parent=None, declared=root_key, actual=actual,
                         used=used, handle="", rec={}, reached=None)
        if top is not None:
            self._construct(top)
            self._build(top, 0)
            links = self._links(top)
        else:
            links = []
        self._unplaced()
        nodes = self._preorder(top)
        overrides = [item.override for item, _ in self.index.overrides]
        return UvmTree(self.index.sources, top, nodes, links, overrides, self.issues, self.truncated)

    def _root(self, root: str | None) -> str:
        if root:
            key = self.index.resolve(root)
            if key not in self.index.types:
                raise LookupError(f"no component class {root!r} in {', '.join(self.index.sources)}")
            return key
        for rec in self.index.roots:
            key = self.index.resolve(_key(rec["root"]))
            if key in self.index.types:
                return key
        tests = sorted(k for k, t in self.index.types.items() if t.tier == "test")
        raise LookupError("no uvm.root record names a root; candidates: " + (", ".join(tests) or "none"))

    def _register(self, item: _Item, owner_path: str) -> None:
        if item.conditional and not self.include_conditional:
            return
        self.factory.register(item.override, owner_path)

    def _node(self, *, path: str, name: str, parent: str | None, declared: str, actual: str,
              used: list[_Entry], handle: str, rec: dict, reached: Any) -> UvmNode | None:
        if len(self.nodes) >= self.max_nodes:
            if not self.truncated:
                self.issues.append(UvmTreeIssue("max_nodes", f"stopped at {self.max_nodes} nodes", path))
            self.truncated = True
            return None
        t = self.index.type(actual)
        state = rec.get("state", STATE_OK)
        if state == STATE_OK and t is None:
            state = STATE_UNRESOLVED
            self.issues.append(UvmTreeIssue(
                "unknown_type", f"{actual} is not in {', '.join(self.index.sources)}", path))
        elif t is not None and t.abstract:
            self.issues.append(UvmTreeIssue("abstract_instance", f"{actual} is a virtual class", path))
        for entry in used:
            if path not in entry.override.applied_to:
                entry.override.applied_to.append(path)
            entry.override.status = APPLIED
        node = UvmNode(
            path=path, name=name, parent=parent, handle=handle, declared=declared, type=actual,
            via=tuple(UvmVia(e.override.kind, e.registered_by or e.override.owner, e.replacement,
                             e.override.loc) for e in used),
            tier=t.tier if t is not None else "", created_by=rec.get("created_by", "factory"),
            conditional=bool(reached.conditional) if reached is not None else False,
            multiplicity=reached.multiplicity if reached is not None else "1",
            state=state, ports=t.ports if t is not None else (),
            loc=getattr(reached.item, "loc", None) if reached is not None else None)
        self.nodes[path] = node
        return node

    def _construct(self, node: UvmNode) -> None:
        """What the node's constructor does when it is created: overrides now,
        children (rare) along with its build_phase's."""
        if node.state != STATE_OK:
            return
        node._pending = self._run(node, CONSTRUCTOR)  # type: ignore[attr-defined]

    def _build(self, node: UvmNode, depth: int) -> None:
        if node.state != STATE_OK:
            return
        if depth >= self.max_depth:
            self.truncated = True
            self.issues.append(UvmTreeIssue("max_depth", f"stopped at depth {self.max_depth}", node.path))
            return
        made = getattr(node, "_pending", [])
        made += self._run(node, BUILD_PHASE)
        node._pending = []  # type: ignore[attr-defined]
        for child in sorted(made, key=lambda c: c.name):
            node.children.append(child.path)
        for child in sorted(made, key=lambda c: c.name):
            self._build(child, depth + 1)

    def _run(self, node: UvmNode, method: str) -> list[UvmNode]:
        """Replay *method* on *node*: register its overrides, create its children."""
        result = run(self.model, node.type, method)
        for issue in result.issues:
            self.issues.append(UvmTreeIssue(
                issue.kind, f"{issue.owner}.{issue.method} is not followed further "
                f"({'a call cycle' if issue.kind == 'inline_cycle' else 'too deep'})", node.path))
        made = []
        for reached in result.items:
            item = reached.item
            self.reached.add((reached.owner, item.method))
            if item.kind == "override":
                if reached.conditional and not self.include_conditional:
                    continue
                self.factory.register(item.override, node.path)
            elif item.kind == "child":
                if reached.conditional and not self.include_conditional:
                    continue
                child = self._create(node, item, reached)
                if child is not None:
                    made.append(child)
        return made

    def _create(self, parent: UvmNode, item: _Item, reached: Any) -> UvmNode | None:
        rec = item.rec
        if reached.multiplicity != "1":
            name = rec.get("inst_name") or f"{rec.get('handle') or '?'}[*]"
        else:
            name = rec.get("inst_name") or rec.get("handle") or "?"
        path = f"{parent.path}.{name}"
        if path in self.nodes:
            self.issues.append(UvmTreeIssue("duplicate_name", f"{name} is created twice under {parent.path}",
                                            path, item.loc))
            return None
        declared = self.index.resolve(_key(rec["type"]))
        used: list[_Entry] = []
        actual = declared
        if rec.get("created_by", "factory") == "factory" and rec.get("state", STATE_OK) == STATE_OK:
            actual, used = self.factory.resolve(declared, path)
        node = self._node(path=path, name=name, parent=parent.path, declared=declared, actual=actual,
                          used=used, handle=rec.get("handle", ""), rec=rec, reached=reached)
        if node is not None:
            self._construct(node)
        return node

    def _preorder(self, top: UvmNode | None) -> list[UvmNode]:
        out: list[UvmNode] = []

        def visit(node: UvmNode) -> None:
            out.append(node)
            for path in node.children:
                visit(self.nodes[path])

        if top is not None:
            visit(top)
        for node in out:
            node.__dict__.pop("_pending", None)
        return out

    def _unplaced(self) -> None:
        """Report what the tree's classes write but no run reaches.

        Only for the classes the tree is built from (each node's type and its
        bases) and for overrides written outside any component (a helper
        object's): another test's overrides are not this tree's business.
        """
        chains: set[str] = set()
        for key in {n.type for n in self.nodes.values()}:
            seen = 0
            while key and key in self.index.types and key not in chains and seen < 64:
                chains.add(key)
                key = self.index.base(key)
                seen += 1
        for item, owner_key in self.index.overrides:
            o = item.override
            if o.status != UNPLACED or not item.method or (owner_key, item.method) in self.reached:
                continue
            if owner_key in chains or owner_key not in self.index.types:
                self.issues.append(UvmTreeIssue(
                    "unplaced_override",
                    f"{o.original} -> {o.replacement} in {owner_key}.{item.method} is not reached "
                    f"from any build_phase or constructor in this tree", loc=o.loc))
        for (key, method), items in self.index.items.items():
            if key not in chains or (key, method) in self.reached or method == CONNECT_PHASE:
                continue
            for item in items:
                if item.kind == "child":
                    self.issues.append(UvmTreeIssue(
                        "unplaced_create",
                        f"{key}.{method} creates {item.rec.get('handle') or '?'} but is not reached "
                        f"from build_phase or the constructor", loc=item.loc))

    # -- connections --

    def _links(self, top: UvmNode) -> list[UvmLink]:
        links: list[UvmLink] = []
        for node in self._preorder(top):
            if node.state != STATE_OK:
                continue
            result = run(self.model, node.type, CONNECT_PHASE)
            for reached in result.items:
                item = reached.item
                if item.kind != "conn":
                    continue
                if reached.conditional and not self.include_conditional:
                    continue
                links.append(self._link(node, item, reached))
        return links

    def _link(self, node: UvmNode, item: _Item, reached: Any) -> UvmLink:
        rec = item.rec
        source, s_many = self._end(node, rec.get("source", {}))
        target, t_many = self._end(node, rec.get("target", {}))
        ok = source is not None and target is not None
        text = f"{_end_text(rec.get('source', {}))} -> {_end_text(rec.get('target', {}))}"
        many = s_many or t_many or reached.multiplicity != "1"
        return UvmLink(
            source=source or UvmLinkEnd(f"{node.path}.{_end_text(rec.get('source', {}))}"),
            target=target or UvmLinkEnd(f"{node.path}.{_end_text(rec.get('target', {}))}"),
            kind=rec.get("kind", "tlm"), owner=node.path, conditional=reached.conditional,
            multiplicity="N" if many else "1", state=STATE_OK if ok else STATE_UNRESOLVED,
            text=text, loc=item.loc)

    def _end(self, node: UvmNode, end: dict) -> tuple[UvmLinkEnd | None, bool]:
        """Resolve an endpoint's handle path from *node* to an instance."""
        current = node
        handles = list(end.get("path", ()))
        port = end.get("port", "")
        many = False
        for i, handle in enumerate(handles):
            bare = handle.split("[", 1)[0]
            child = next((self.nodes[p] for p in current.children if self.nodes[p].handle == bare), None)
            if child is None:
                # A component endpoint may end at a handle the component only
                # holds (a virtual sequencer's), which is not a child of it.
                if end.get("component") and i == len(handles) - 1 and not port:
                    return UvmLinkEnd(current.path, handle), many
                return None, many
            many = many or child.multiplicity != "1"
            current = child
        if port and current.state == STATE_OK and current.ports and not any(p.name == port for p in current.ports):
            self.issues.append(UvmTreeIssue(
                "unknown_port", f"{current.type} has no port {port}", current.path))
        return UvmLinkEnd(current.path, port), many


def _end_text(end: dict) -> str:
    parts = [*end.get("path", ()), *([end["port"]] if end.get("port") else [])]
    return ".".join(parts) or "this"


# -- renderers ---------------------------------------------------------------------


def _short(key: str) -> str:
    return key.rsplit("::", 1)[-1]


def render_text(tree: UvmTree) -> str:
    """An indented tree for a terminal, then the links, overrides and issues."""
    lines: list[str] = []
    by_path = tree._by_path()

    def label(n: UvmNode) -> str:
        text = f"{n.name} : {_short(n.type)}"
        if n.declared and n.declared != n.type:
            text += f" <- {_short(n.declared)}"
        if n.multiplicity != "1":
            text += f"  (x{n.multiplicity})"
        if n.conditional:
            text += "  [conditional]"
        if n.state != STATE_OK:
            text += f"  [{n.state}]"
        return text

    def visit(n: UvmNode, prefix: str, last: bool, top: bool) -> None:
        lines.append(label(n) if top else f"{prefix}{'└── ' if last else '├── '}{label(n)}")
        inner = "" if top else prefix + ("    " if last else "│   ")
        for i, path in enumerate(n.children):
            visit(by_path[path], inner, i == len(n.children) - 1, False)

    if tree.root is not None:
        visit(tree.root, "", True, True)
    root = tree.root.path + "." if tree.root is not None else ""

    def end(e: UvmLinkEnd) -> str:
        path = e.path[len(root):] if e.path.startswith(root) else e.path
        return f"{path}.{e.port}" if e.port else path

    if tree.links:
        lines += ["", "links:"]
        for k in tree.links:
            text = f"  {end(k.source)} -> {end(k.target)}  ({k.kind})"
            if k.multiplicity != "1":
                text += f"  (x{k.multiplicity})"
            if k.conditional:
                text += "  [conditional]"
            if k.state != STATE_OK:
                text += f"  [{k.state}: {k.text}]"
            lines.append(text)
    # an unplaced override that matters is under issues already
    applied = [o for o in tree.overrides if o.status != UNPLACED]
    if applied:
        lines += ["", "overrides:"]
        for o in applied:
            where = f" at {o.inst_path}" if o.kind == "inst" else ""
            lines.append(f"  {_short(o.original)} -> {_short(o.replacement)} ({o.kind}{where}): {o.status}")
    if tree.issues:
        lines += ["", "issues:"]
        lines += [f"  {i.code}: {i.message}" + (f" ({i.path})" if i.path else "") for i in tree.issues]
    if tree.truncated:
        lines += ["", "(truncated)"]
    return "\n".join(lines) + "\n"


def render_dot(tree: UvmTree) -> str:
    """Graphviz: a component with children is a cluster, links are edges."""
    by_path = tree._by_path()
    out = ["digraph uvm {", "  rankdir=LR;", "  compound=true;", "  node [shape=box, fontsize=10];"]

    def q(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def visit(n: UvmNode, indent: str) -> None:
        label = f"{n.name}\\n{_short(n.type)}"
        if n.children:
            out.append(f"{indent}subgraph {q('cluster_' + n.path)} {{")
            out.append(f"{indent}  label={q(n.name + ' : ' + _short(n.type))};")
            # an anchor for links that end at the component itself
            out.append(f"{indent}  {q(n.path)} [label={q(n.name)}, shape=plaintext];")
            for path in n.children:
                visit(by_path[path], indent + "  ")
            out.append(f"{indent}}}")
        else:
            style = ", style=dashed" if n.conditional or n.state != STATE_OK else ""
            out.append(f"{indent}{q(n.path)} [label={q(label)}{style}];")

    if tree.root is not None:
        visit(tree.root, "  ")
    for k in tree.links:
        attrs = [f"label={q(k.kind)}"]
        if k.source.port:
            attrs.append(f"taillabel={q(k.source.port)}")
        if k.target.port:
            attrs.append(f"headlabel={q(k.target.port)}")
        if k.conditional or k.state != STATE_OK:
            attrs.append("style=dashed")
        if k.source.path in by_path and k.target.path in by_path:
            out.append(f"  {q(k.source.path)} -> {q(k.target.path)} [{', '.join(attrs)}];")
    out.append("}")
    return "\n".join(out) + "\n"
