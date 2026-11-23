"""The UVM views of one build as ``uvm.*`` records (plan §5.3, D4-IMPL-1).

The records carry the :mod:`~..model.uvm` dataclasses one-for-one: field names
match, a ``location`` is a ``loc``, a type name is a ``Ref`` and a field that
holds its dataclass default is left out, so a reader rebuilds the dataclass
from the fields that are there.  Renamed on the way:

* ``name`` of a ``UvmType``/``UvmSequence`` and every ``type_name`` is
  ``type``;
* a ``UvmBinding``'s ``set_access`` is ``set`` and its ``consumers`` are the
  ``id`` of the ``uvm.config`` records they are (``c1``, ``c2``, ... in
  ``UvmConfig.accesses`` order).

``UvmConfigRow``, ``built_by`` and ``used_by`` are derived and not written.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ..model.objects import SourceRef
from ..model.uvm import (_LIBRARY_PREFIX, UvmActivity, UvmBinding, UvmBridge, UvmChild, UvmConfig,
                         UvmConfigAccess, UvmConnection, UvmEndpoint, UvmInterfaceDriver, UvmOverride,
                         UvmOverrides, UvmPort, UvmSequence, UvmStructure, UvmType)

log = logging.getLogger(__name__)

#: ``SourceRef -> Loc`` of the records being written (``emit``'s ``loc``).
LocFn = Callable[[Any], "dict | None"]


@dataclass
class UvmViews:
    """What the UVM provider answers without an argument, plus every sequence."""

    structure: Any = None
    config: Any = None
    overrides: Any = None
    bridge: Any = None
    sequences: list[UvmSequence] = field(default_factory=list)

    def sections(self) -> dict[str, str]:
        """Header ``sections`` for the views that were computed."""
        out = {}
        for key, value in (("uvm.tree", self.structure), ("uvm.config", self.config),
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


def _ref(name: str | None) -> dict:
    return {"name": name or "$unknown"}


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
        rec: dict[str, Any] = {"r": "uvm.root", "root": _ref(s.root)}
        for name in ("root_origin", "component_count", "truncated"):
            if getattr(s, name):
                rec[name] = getattr(s, name)
        if s.root_candidates:
            rec["root_candidates"] = list(s.root_candidates)
        out.append(rec)
        for t in s.types.values():
            rec = {"r": "uvm.type", "type": _ref(t.name), **_fields(t, loc, skip=("name", "ports"))}
            if t.ports:
                rec["ports"] = [{"name": p.name, **_fields(p, loc, skip=("name",))} for p in t.ports]
            out.append(rec)
        for owner, kids in s.children.items():
            for c in kids:
                out.append({"r": "uvm.child", "owner": _ref(owner), "handle": c.handle,
                            "type": _ref(c.type_name), **_fields(c, loc, skip=("handle", "type_name"))})
        for owner, conns in s.connections.items():
            for c in conns:
                rec = {"r": "uvm.conn", "owner": _ref(owner or c.owner),
                       "source": _endpoint(c.source, loc), "target": _endpoint(c.target, loc),
                       **_fields(c, loc, skip=("owner", "source", "target"))}
                out.append(rec)
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
            rec = {"r": "uvm.override", "original": _ref(o.original), "replacement": _ref(o.replacement),
                   **_fields(o, loc, skip=("original", "replacement", "owner"))}
            if o.owner:
                rec["owner"] = _ref(o.owner)
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
        s = UvmStructure()
        for rec in by_r.get("uvm.root", ())[:1]:
            s.root = _name(rec["root"])
            s.root_origin = rec.get("root_origin", "")
            s.component_count = rec.get("component_count", 0)
            s.truncated = rec.get("truncated", False)
            s.root_candidates = tuple(rec.get("root_candidates", ()))
        for rec in by_r.get("uvm.type", ()):
            ports = tuple(build(UvmPort, p) for p in rec.get("ports", ()))
            t = build(UvmType, rec, name=_name(rec["type"]), ports=ports)
            s.types[t.name] = t
            # the walk enters a type in all three dicts at once, empty lists too
            s.children[t.name] = []
            s.connections[t.name] = []
        for rec in by_r.get("uvm.child", ()):
            s.children.setdefault(_name(rec["owner"]), []).append(build(UvmChild, rec))
        for rec in by_r.get("uvm.conn", ()):
            owner = _name(rec["owner"])
            s.connections.setdefault(owner, []).append(build(
                UvmConnection, rec, owner=owner,
                source=build(UvmEndpoint, rec["source"]), target=build(UvmEndpoint, rec["target"])))
        out.structure = s
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
                owner=_name(rec["owner"]) if "owner" in rec else ""))
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
