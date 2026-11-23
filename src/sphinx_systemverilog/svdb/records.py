"""What the schema says about each record type, compiled for fast use.

Everything here is derived from ``svdb-1.schema.json`` so that the importer
and exporter cannot drift from the contract:

* the known fields of each record type, in schema order (exports use that
  order, imports drop and warn about anything else);
* the required fields (the built-in structural check of decision #10);
* *reference walkers*: for each record type, and for each object kind's
  ``detail``, a function that yields every ``Ref`` and every ``Span`` in a
  record, with the property path it was found under (its *role*).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterator

from . import schema as _schema

#: A found reference: (role, pos, seq-in-container, ref dict, head).
#: ``role`` is the dotted property path below the record (or below ``detail``
#: for objects), without array indices.  ``pos`` is the index in the first
#: array on that path, ``None`` when there is none.  ``head`` is true for a
#: Ref, and for a Span that starts its text (``extends base #(T)``: ``base``).
Found = tuple[str, "int | None", int, dict, bool]

_Walker = Callable[[Any, str, "int | None", list], None]


@dataclass(frozen=True)
class RecordInfo:
    """Fields and reference walker of one record type."""

    fields: tuple[str, ...]
    required: frozenset[str]
    walk: _Walker | None


def _ref_leaf(value, role, pos, out):
    if isinstance(value, dict) and "name" in value and "text" not in value:
        out.append((role, pos, 0, value, True))


def _spans_leaf(value, role, pos, out):
    if isinstance(value, dict) and "text" in value:
        for j, span in enumerate(value.get("refs") or ()):
            if isinstance(span, dict) and "name" in span:
                at = span.get("at") or (None,)
                out.append((role, pos, j, span, at[0] == 0))


def _span_leaf(value, role, pos, out):
    if isinstance(value, dict) and "name" in value and "at" in value:
        out.append((role, pos, 0, value, value["at"][0] == 0))


_LEAVES = {"Ref": _ref_leaf, "Span": _span_leaf, "TypeRef": _spans_leaf, "Expr": _spans_leaf}


class _Compiler:
    def __init__(self, defs: dict):
        self.defs = defs
        self.memo: dict[str, _Walker | None] = {}

    def ref(self, name: str) -> _Walker | None:
        if name in _LEAVES:
            return _LEAVES[name]
        if name in self.memo:
            return self.memo[name]
        # Recursive definitions (the UVM activity tree) see a forwarding stub.
        box: list[_Walker | None] = [None]
        self.memo[name] = lambda v, r, p, o: box[0] and box[0](v, r, p, o)
        box[0] = self.node(self.defs[name])
        self.memo[name] = box[0]
        return box[0]

    def node(self, node: Any) -> _Walker | None:
        if not isinstance(node, dict):
            return None
        parts: list[_Walker] = []
        if "$ref" in node:
            w = self.ref(node["$ref"].rsplit("/", 1)[-1])
            if w:
                parts.append(w)
        for key in ("oneOf", "anyOf", "allOf"):
            for alt in node.get(key, ()):
                w = self.node(alt)
                if w:
                    parts.append(w)
        if "then" in node:
            w = self.node(node["then"])
            if w:
                parts.append(w)
        props = {k: self.node(v) for k, v in node.get("properties", {}).items()}
        props = {k: w for k, w in props.items() if w}
        if props:
            parts.append(_props(props))
        items = self.node(node.get("items"))
        if items:
            parts.append(_items(items))
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return _seq(parts)


def _props(props: dict[str, _Walker]) -> _Walker:
    def walk(value, role, pos, out):
        if isinstance(value, dict):
            for k, w in props.items():
                if k in value:
                    w(value[k], f"{role}.{k}" if role else k, pos, out)
    return walk


def _items(item: _Walker) -> _Walker:
    def walk(value, role, pos, out):
        if isinstance(value, list):
            for i, v in enumerate(value):
                item(v, role, i if pos is None else pos, out)
    return walk


def _seq(parts: list[_Walker]) -> _Walker:
    def walk(value, role, pos, out):
        for w in parts:
            w(value, role, pos, out)
    return walk


@lru_cache(maxsize=1)
def record_types() -> dict[str, RecordInfo]:
    """Info for every record type the schema defines, keyed by ``r``."""
    s = _schema()
    defs = s["$defs"]
    comp = _Compiler(defs)
    out: dict[str, RecordInfo] = {}
    for clause in s["allOf"]:
        r = clause["if"]["properties"]["r"]["const"]
        name = clause["then"]["$ref"].rsplit("/", 1)[-1]
        d = defs[name]
        if r == "object":
            walk = None  # objects walk their detail per kind; see detail_walkers()
        else:
            walk = comp.node({"properties": {k: v for k, v in d.get("properties", {}).items() if k != "r"}})
        out[r] = RecordInfo(tuple(d.get("properties", {})), frozenset(d.get("required", ())), walk)
    return out


@lru_cache(maxsize=1)
def detail_walkers() -> dict[str, _Walker | None]:
    """Reference walker of ``detail``, by object kind."""
    defs = _schema()["$defs"]
    comp = _Compiler(defs)
    out: dict[str, _Walker | None] = {k: None for k in kinds()}
    for clause in defs["rec_object"].get("allOf", ()):
        cond = clause.get("if", {}).get("properties", {}).get("kind", {})
        detail = clause.get("then", {}).get("properties", {}).get("detail")
        if not detail:
            continue
        names = [cond["const"]] if "const" in cond else cond.get("enum", [])
        w = comp.node(detail)
        for k in names:
            out[k] = w
    return out


@lru_cache(maxsize=1)
def kinds() -> tuple[str, ...]:
    """Every object kind, in schema order."""
    return tuple(_schema()["$defs"]["kind"]["enum"])


@lru_cache(maxsize=1)
def sections() -> tuple[str, ...]:
    """Every header section name."""
    return tuple(_schema()["$defs"]["rec_header"]["properties"]["sections"]["propertyNames"]["enum"])


def find_refs(record: dict) -> Iterator[Found]:
    """Every Ref and Span in *record* (an object's are those in ``detail``)."""
    out: list = []
    if record.get("r") == "object":
        w = detail_walkers().get(record.get("kind"))
        if w and isinstance(record.get("detail"), dict):
            w(record["detail"], "", None, out)
    else:
        info = record_types().get(record.get("r"))
        if info and info.walk:
            info.walk(record, "", None, out)
    return iter(out)


# -- structural legality (plan §5.2 "Parent kinds") ------------------------------

_DEFINITION = frozenset({"module", "interface", "program"})
_SCOPE = _DEFINITION | {"package", "checker", "class", "generate", "function", "task", "block", "process"}
_DATA_HOLDERS = frozenset({"typedef", "variable", "net", "port", "parameter", "field"})

#: Kinds that may appear at the root (no ``parent``).
ROOT_KINDS = frozenset({
    "package", "module", "interface", "program", "checker", "primitive", "config", "macro",
    "class", "parameter", "net", "variable", "typedef", "nettype", "function", "task",
    "sequence", "sva_property", "let", "covergroup",
})

#: Allowed parent kinds, by child kind.  Deliberately a little wider than the
#: LRM where a tool is likely to report such a parent (a typedef in a task).
PARENT_KINDS: dict[str, frozenset[str]] = {
    "package": frozenset(), "module": _DEFINITION, "interface": _DEFINITION, "program": _DEFINITION,  # LRM 23.4 nesting
    "primitive": frozenset(), "config": frozenset(), "macro": frozenset(),
    "checker": _DEFINITION | {"package", "generate", "checker"},
    "class": _DEFINITION | {"package", "class", "generate"},
    "constraint": frozenset({"class"}),
    "parameter": _SCOPE | {"covergroup", "primitive"},
    "port": _DEFINITION | {"primitive"},
    "net": _DEFINITION | {"package", "generate", "checker"},
    "variable": _SCOPE | {"covergroup", "clocking"},
    "typedef": _SCOPE,
    "enum_member": _DATA_HOLDERS,
    "field": _DATA_HOLDERS,
    "nettype": _DEFINITION | {"package", "generate"},
    "function": _SCOPE | {"covergroup"},
    "task": _SCOPE,
    "modport": frozenset({"interface", "generate"}),
    "clocking": _DEFINITION | {"checker", "generate"},
    "clockvar": frozenset({"clocking"}),
    "instance": _DEFINITION | {"generate", "checker"},
    "generate": _DEFINITION | {"generate", "checker"},
    "genvar": _DEFINITION | {"generate", "checker"},
    "defparam": _DEFINITION | {"generate"},
    "process": _DEFINITION | {"generate", "checker"},
    "block": frozenset({"process", "function", "task", "block"}),
    "sequence": _DEFINITION | {"package", "checker", "generate"},
    "sva_property": _DEFINITION | {"package", "checker", "generate"},
    "let": _SCOPE,
    "assertion": _DEFINITION | {"generate", "process", "checker", "block", "function", "task"},
    "covergroup": _DEFINITION | {"class", "package", "generate"},
    "coverpoint": frozenset({"covergroup"}),
    "cross": frozenset({"covergroup"}),
    "bins": frozenset({"coverpoint", "cross"}),
}
