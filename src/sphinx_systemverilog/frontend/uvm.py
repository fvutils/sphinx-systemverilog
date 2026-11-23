"""The UVM views of one build as ``uvm.*`` records (plan §5.3, D4-IMPL-1).

The records carry the :mod:`~..model.uvm` dataclasses one-for-one: field names
match, a ``location`` is a ``loc``, a type name is a ``Ref`` and a field that
holds its dataclass default is left out, so a reader rebuilds the dataclass
from the fields that are there.  Renamed on the way:

* ``name`` of a ``UvmType``/``UvmSequence`` and every ``type_name`` is
  ``type``;
* a ``UvmBinding``'s ``set_access`` is ``set`` and its ``consumers`` are the
  ``id`` of the ``uvm.config`` records they are (``c1``, ``c2``, ... in
  ``UvmConfig.accesses`` order);
* a ``UvmType``'s ``methods`` tuple is an object keyed by method name;
* a ``UvmType``'s ``key`` and a ``UvmChild``'s ``type_key`` are the
  ``target`` of its ``type`` Ref;
* a ``UvmType``'s ``base`` is the ``target`` of a ``base`` Ref named
  ``chain[1]``, and a ``UvmOverride``'s ``*_key`` the ``target`` of the
  matching Ref.

``UvmConfigRow``, ``built_by`` and ``used_by`` are derived and not written.

The ``uvm.type``, ``uvm.child`` and ``uvm.conn`` records are each class's own
partial elaboration (:meth:`~..model.uvm.UvmProvider.classes`), not the root
walk: the walk is derived, and :func:`rebuild` redoes it from them with the
same rule (:func:`~..svdb.uvm_inline.walk`).  ``uvm.root`` says where it starts.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ..model.objects import SourceRef
from ..model.uvm import (_LIBRARY_PREFIX, DEFAULT_MAX_COMPONENTS, MAX_DEPTH, STATE_OK, UvmActivity, UvmBinding, UvmBridge, UvmCall, UvmChild, UvmConfig,
                         UvmConfigAccess, UvmConnection, UvmEndpoint, UvmInterfaceDriver, UvmMethod,
                         UvmOverride, UvmOverrides, UvmPort, UvmSequence, UvmStructure, UvmType)

log = logging.getLogger(__name__)

#: ``SourceRef -> Loc`` of the records being written (``emit``'s ``loc``).
LocFn = Callable[[Any], "dict | None"]


@dataclass
class UvmViews:
    """What the UVM provider answers without an argument, plus every sequence."""

    structure: Any = None
    #: Every component class's own records, keyed by qualified name.
    classes: Any = None
    config: Any = None
    overrides: Any = None
    bridge: Any = None
    sequences: list[UvmSequence] = field(default_factory=list)

    def sections(self) -> dict[str, str]:
        """Header ``sections`` for the views that were computed."""
        out = {}
        for key, value in (("uvm.tree", self.structure or self.classes), ("uvm.config", self.config),
                           ("uvm.overrides", self.overrides), ("uvm.bindings", self.bridge)):
            if value is not None:
                out[key] = "complete"
        if self.structure is not None or self.sequences:
            out["uvm.sequences"] = "complete"
        return out


def views(provider: Any) -> UvmViews:
    """Ask *provider* (a :class:`~..model.uvm.UvmProvider`) for every view.

    A view that fails is ``None``: the directive that asks reports it.
    """
    out = UvmViews(structure=_quietly(provider.get, "UVM testbench"),
                   classes=_quietly(provider.classes, "component classes"),
                   config=_quietly(provider.config, "config_db accesses"),
                   overrides=_quietly(provider.overrides, "factory overrides"),
                   bridge=_quietly(provider.bridge, "virtual-interface bindings"))
    classes = _quietly(provider._class_index, "class index") or {}
    for name in classes:
        if name.startswith(_LIBRARY_PREFIX):
            continue
        seq = _quietly(lambda: provider.sequence(name), f"sequence {name}")
        if seq is not None:
            out.sequences.append(seq)
    return out


def _quietly(fn, what: str):
    try:
        return fn()
    except Exception as e:
        log.debug("sphinx-systemverilog: precomputing the %s failed: %s", what, e)
        return None


def _ref(name: str | None, target: str = "") -> dict:
    out = {"name": name or "$unknown"}
    if target:
        out["target"] = target
    return out


def _fields(obj: Any, loc: LocFn, skip: tuple[str, ...] = ()) -> dict:
    """The non-default fields of *obj*, with ``type_name``/``location`` renamed."""
    out: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        if f.name in skip:
            continue
        value = getattr(obj, f.name)
        default = f.default if f.default is not dataclasses.MISSING else (
            f.default_factory() if f.default_factory is not dataclasses.MISSING else dataclasses.MISSING)
        if value == default:
            continue
        if f.name == "location":
            at = loc(value)
            if at:
                out["loc"] = at
        elif f.name == "type_name":
            out["type"] = _ref(value)
        elif isinstance(value, tuple):
            out[f.name] = list(value)
        else:
            out[f.name] = value
    return out


def _endpoint(e: UvmEndpoint, loc: LocFn) -> dict:
    return _fields(e, loc)


def _method(m: UvmMethod, loc: LocFn) -> dict:
    out = _fields(m, loc, skip=("name", "calls"))
    if m.calls:
        # `step` 0 is its dataclass default, and still always written
        out["calls"] = [{"step": c.step, **_fields(c, loc, skip=("step",))} for c in m.calls]
    return out


def _activity(a: UvmActivity, loc: LocFn) -> dict:
    out = {"kind": a.kind, **_fields(a, loc, skip=("kind", "children"))}
    if a.children:
        out["children"] = [_activity(c, loc) for c in a.children]
    return out


def records(v: UvmViews, loc: LocFn) -> list[dict]:
    """``uvm.*`` records of *v*, in the export order of §5.3."""
    out: list[dict] = []
    s = v.structure
    if s is not None and s.root:
        rec: dict[str, Any] = {"r": "uvm.root", "root": _ref(s.root, s.root_key)}
        for name in ("root_origin", "component_count", "truncated"):
            if getattr(s, name):
                rec[name] = getattr(s, name)
        if s.root_candidates:
            rec["root_candidates"] = list(s.root_candidates)
        out.append(rec)
    c = v.classes
    if c is not None:
        for key in sorted(c.types):
            t = c.types[key]
            rec = {"r": "uvm.type", "type": _ref(t.name, t.key),
                   **_fields(t, loc, skip=("name", "ports", "methods", "key", "base"))}
            if t.base:
                rec["base"] = _ref(t.chain[1] if len(t.chain) > 1 else t.base.rsplit("::", 1)[-1], t.base)
            if t.ports:
                rec["ports"] = [{"name": p.name, **_fields(p, loc, skip=("name",))} for p in t.ports]
            if t.methods:
                rec["methods"] = {m.name: _method(m, loc) for m in t.methods}
            out.append(rec)
        for key in sorted(c.types):
            for k in c.children.get(key, ()):
                out.append({"r": "uvm.child", "owner": _ref(c.types[key].name, key), "handle": k.handle,
                            "type": _ref(k.type_name, k.type_key),
                            **_fields(k, loc, skip=("handle", "type_name", "type_key"))})
        for key in sorted(c.types):
            for w in c.connections.get(key, ()):
                out.append({"r": "uvm.conn", "owner": _ref(c.types[key].name, key),
                            "source": _endpoint(w.source, loc), "target": _endpoint(w.target, loc),
                            **_fields(w, loc, skip=("owner", "source", "target"))})
    ids: list[tuple[UvmConfigAccess, str]] = []
    if v.config is not None:
        for i, a in enumerate(v.config.accesses, 1):
            ids.append((a, f"c{i}"))
            rec = {"r": "uvm.config", "id": f"c{i}", "action": a.action, "owner": _ref(a.owner),
                   **_fields(a, loc, skip=("action", "owner", "type_name"))}
            if a.type_name:
                rec["type"] = a.type_name  # as written, not a Ref (§5.3)
            out.append(rec)
    if v.overrides is not None:
        for o in v.overrides.overrides:
            rec = {"r": "uvm.override", "original": _ref(o.original, o.original_key),
                   "replacement": _ref(o.replacement, o.replacement_key),
                   **_fields(o, loc, skip=("original", "replacement", "owner", "original_key",
                                           "replacement_key", "owner_key"))}
            if o.owner:
                rec["owner"] = _ref(o.owner, o.owner_key)
            out.append(rec)
    if v.bridge is not None:
        def cid(access: UvmConfigAccess) -> str | None:
            found = next((i for a, i in ids if a is access), None)
            return found or next((i for a, i in ids if a == access), None)

        for b in v.bridge.bindings:
            set_id = cid(b.set_access)
            if set_id is None:
                continue
            rec = {"r": "uvm.binding", "interface_type": _ref(b.interface_type), "set": set_id}
            if b.field is not None:
                rec["field"] = b.field
            if b.instance_path:
                rec["instance_path"] = b.instance_path
            if b.drivers:
                rec["drivers"] = [_fields(d, loc) for d in b.drivers]
            consumers = [i for i in (cid(a) for a in b.consumers) if i]
            if consumers:
                rec["consumers"] = consumers
            out.append(rec)
    for q in v.sequences:
        rec = {"r": "uvm.sequence", "type": _ref(q.name), **_fields(q, loc, skip=("name", "body"))}
        if q.body:
            rec["body"] = [_activity(a, loc) for a in q.body]
        out.append(rec)
    return out


# -- reading back (D4-IMPL-2) ----------------------------------------------------


def read(db: Any, source: int = 0) -> UvmViews:
    """The views stored in file *source* of *db* (a :class:`~..svdb.Database`).

    A view whose header section is missing is ``None``, as when it was not
    computed; the sequences are every ``uvm.sequence`` record.
    """
    sections = (db.headers[source] or {}).get("sections") or {}
    conn = db.connection(source)
    paths = dict(conn.execute("SELECT fid, path FROM file"))
    rows = [json.loads(rec) for (rec,) in conn.execute("SELECT rec FROM uvm ORDER BY seq")]
    return rebuild(rows, paths, sections)


def rebuild(recs: list[dict], paths: dict[str, str], sections: dict[str, str]) -> UvmViews:
    """The inverse of :func:`records`: *paths* maps file ids to paths."""

    def build(cls, rec: dict, **known):
        args: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name in known:
                args[f.name] = known[f.name]
            elif f.name == "location":
                at = rec.get("loc")
                if at:
                    args["location"] = SourceRef(paths.get(at["file"], at["file"]), at["line"], at.get("col", 0))
            elif f.name == "type_name":
                if "type" in rec:
                    args["type_name"] = _name(rec["type"])
            elif f.name in rec:
                value = rec[f.name]
                args[f.name] = tuple(value) if isinstance(value, list) else value
        return cls(**args)

    def activity(rec: dict) -> UvmActivity:
        return build(UvmActivity, rec, children=tuple(activity(c) for c in rec.get("children", ())))

    by_r: dict[str, list[dict]] = {}
    for rec in recs:
        by_r.setdefault(rec["r"], []).append(rec)
    out = UvmViews()
    if "uvm.tree" in sections:
        c = UvmStructure()
        for rec in by_r.get("uvm.type", ()):
            ports = tuple(build(UvmPort, p) for p in rec.get("ports", ()))
            methods = tuple(
                build(UvmMethod, m, name=name, calls=tuple(build(UvmCall, k) for k in m.get("calls", ())))
                for name, m in rec.get("methods", {}).items())
            t = build(UvmType, rec, name=_name(rec["type"]), ports=ports, methods=methods,
                      key=_key(rec["type"]), base=(rec.get("base") or {}).get("target") or "")
            c.types[t.key] = t
            c.children[t.key] = []
            c.connections[t.key] = []
        for rec in by_r.get("uvm.child", ()):
            c.children.setdefault(_key(rec["owner"]), []).append(
                build(UvmChild, rec, type_key=rec["type"].get("target") or ""))
        for rec in by_r.get("uvm.conn", ()):
            c.connections.setdefault(_key(rec["owner"]), []).append(build(
                UvmConnection, rec, owner=_name(rec["owner"]),
                source=build(UvmEndpoint, rec["source"]), target=build(UvmEndpoint, rec["target"])))
        out.classes = c
        out.structure = _walk(c, by_r.get("uvm.root", ())[:1])
    accesses: dict[str, UvmConfigAccess] = {}
    if "uvm.config" in sections:
        out.config = UvmConfig()
        for rec in by_r.get("uvm.config", ()):
            a = build(UvmConfigAccess, rec, owner=_name(rec["owner"]), type_name=rec.get("type", ""))
            accesses[rec["id"]] = a
            out.config.accesses.append(a)
    if "uvm.overrides" in sections:
        out.overrides = UvmOverrides()
        for rec in by_r.get("uvm.override", ()):
            out.overrides.overrides.append(build(
                UvmOverride, rec, original=_name(rec["original"]), replacement=_name(rec["replacement"]),
                original_key=rec["original"].get("target") or "",
                replacement_key=rec["replacement"].get("target") or "",
                owner=_name(rec["owner"]) if "owner" in rec else "",
                owner_key=(rec.get("owner") or {}).get("target") or ""))
    if "uvm.bindings" in sections:
        out.bridge = UvmBridge()
        for rec in by_r.get("uvm.binding", ()):
            out.bridge.bindings.append(build(
                UvmBinding, rec, interface_type=_name(rec["interface_type"]), set_access=accesses[rec["set"]],
                drivers=tuple(build(UvmInterfaceDriver, d) for d in rec.get("drivers", ())),
                consumers=tuple(accesses[i] for i in rec.get("consumers", ()))))
    for rec in by_r.get("uvm.sequence", ()):
        out.sequences.append(build(UvmSequence, rec, name=_name(rec["type"]),
                                   body=tuple(activity(a) for a in rec.get("body", ()))))
    return out


def _name(ref: dict) -> str:
    name = ref.get("name", "")
    return "" if name == "$unknown" else name


def _key(ref: dict) -> str:
    """A Ref's target, or its name when the producer left it unresolved."""
    return ref.get("target") or _name(ref)


def _walk(classes: UvmStructure, roots: list[dict]) -> UvmStructure:
    """The root walk, redone from per-class records (:func:`records`' inverse)."""
    from ..svdb.uvm_inline import walk

    s = UvmStructure()
    for rec in roots:
        s.root = _name(rec["root"])
        s.root_key = rec["root"].get("target") or ""
        s.root_origin = rec.get("root_origin", "")
        s.component_count = rec.get("component_count", 0)
        s.truncated = rec.get("truncated", False)
        s.root_candidates = tuple(rec.get("root_candidates", ()))
    key = s.root_key or next((k for k, t in classes.types.items() if t.name == s.root), "")
    if key in classes.types:
        # The same budget the producer stopped at, so a truncated tree is cut
        # in the same place.
        budget = s.component_count if s.truncated else max(s.component_count, DEFAULT_MAX_COMPONENTS)
        found = walk(_RecordModel(classes), key, s.root, budget=budget, max_depth=MAX_DEPTH)
        s.types, s.children, s.connections = found.types, found.children, found.connections
    return s


class _RecordModel:
    """:class:`~..svdb.uvm_inline.WalkModel` over per-class records."""

    def __init__(self, classes: UvmStructure) -> None:
        self._c = classes

    def type(self, key: str) -> UvmType | None:
        return self._c.types.get(key)

    def base(self, key: str) -> str | None:
        t = self._c.types.get(key)
        return t.base if t is not None and t.base else None

    def items(self, key: str, method: str) -> list[Any]:
        return ([k for k in self._c.children.get(key, ()) if k.method == method]
                + [w for w in self._c.connections.get(key, ()) if w.method == method])

    def describe(self, key: str, display: str) -> UvmType:
        return dataclasses.replace(self._c.types[key], name=display)

    def is_child(self, item: Any) -> bool:
        return isinstance(item, UvmChild)

    def child(self, reached: Any) -> tuple[UvmChild, str | None]:
        k = reached.item
        child = dataclasses.replace(k, conditional=reached.conditional, multiplicity=reached.multiplicity)
        descend = k.state == STATE_OK and k.type_key in self._c.types
        return child, k.type_key if descend else None

    def connection(self, reached: Any, display: str) -> UvmConnection | None:
        w = reached.item
        if not isinstance(w, UvmConnection):
            return None
        return dataclasses.replace(w, owner=display, conditional=reached.conditional)
