"""D0-TEST-1: the svdb interchange schema and its bundled examples.

The examples double as the format documentation's examples (D8), so they are
held to more than schema validity: every structural pointer resolves, every
span really covers the name it claims, and elaboration keys follow the
canonicalization rule.
"""

from __future__ import annotations

import copy
import json

import pytest

jsonschema = pytest.importorskip("jsonschema")

from sphinx_systemverilog import svdb  # noqa: E402
from sphinx_systemverilog.svdb import canon  # noqa: E402

pytestmark = pytest.mark.unit

#: Roots of Ref targets that the examples deliberately leave in another
#: database (the UVM library, the RTL a testbench binds to).
EXTERNAL_ROOTS = {"uvm_pkg", "tb_top", "axi_if", "axi_dut"}


@pytest.fixture(scope="module")
def validator():
    schema = svdb.schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _records(name: str) -> list[dict]:
    return [json.loads(line) for line in svdb.example_text(name).splitlines() if line.strip()]


EXAMPLES = svdb.example_names()


def test_examples_exist():
    expected = {
        "minimal.ndjson", "kdb-like.ndjson", "design-elements.ndjson", "classes.ndjson",
        "data.ndjson", "subroutines.ndjson", "interfaces.ndjson", "structure.ndjson",
        "verification.ndjson", "preprocessor.ndjson", "uvm.ndjson",
    }
    assert expected <= set(EXAMPLES)


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_validates(validator, name):
    records = _records(name)
    assert records[0]["r"] == "header", "the first record must be the header"
    assert all(r["r"] != "header" for r in records[1:]), "exactly one header"
    for i, rec in enumerate(records, start=1):
        errors = sorted(validator.iter_errors(rec), key=lambda e: e.json_path)
        assert not errors, f"{name}:{i}: " + "; ".join(f"{e.json_path}: {e.message}" for e in errors)


def test_examples_cover_every_kind_and_record_type():
    schema = svdb.schema()
    kinds = set(schema["$defs"]["kind"]["enum"])
    rtypes = set(schema["properties"]["r"]["enum"])
    seen_kinds: set[str] = set()
    seen_rtypes: set[str] = set()
    for name in EXAMPLES:
        for rec in _records(name):
            seen_rtypes.add(rec["r"])
            if rec["r"] == "object":
                seen_kinds.add(rec["kind"])
    assert kinds - seen_kinds == set(), "kinds without an example"
    assert rtypes - seen_rtypes == set(), "record types without an example"


# -- semantic consistency of the examples --------------------------------------


def _iter_spans(value):
    """Yield every (text, span) pair inside a TypeRef/Expr anywhere in *value*."""
    if isinstance(value, dict):
        if "text" in value and isinstance(value.get("refs"), list):
            for span in value["refs"]:
                yield value["text"], span
        for v in value.values():
            yield from _iter_spans(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_spans(v)


def _iter_refs(value):
    """Yield every Ref-shaped dict (``name`` + ``target``) anywhere in *value*."""
    if isinstance(value, dict):
        if "name" in value and "target" in value:
            yield value
        for v in value.values():
            yield from _iter_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_refs(v)


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_is_consistent(name):
    records = _records(name)
    files = {r["id"] for r in records if r["r"] == "file"}
    units = {r["id"] for r in records if r["r"] == "unit"}
    objects = [r for r in records if r["r"] == "object"]

    # Identity: (ns, unit, qname) unique; qname well formed; name is the last
    # segment; parent in the same ns/unit and present.
    keys: dict[tuple, dict] = {}
    for o in objects:
        key = (o["ns"], o.get("unit"), o["qname"])
        assert key not in keys, f"duplicate key {key}"
        keys[key] = o
        segs = canon.parse_qname(o["qname"])
        assert canon.base_name(segs[-1]).rstrip() == o["name"].rstrip() or o["name"].startswith("$"), o["qname"]
        if o.get("unit"):
            assert o["unit"] in units
        if "parent" in o:
            # The qname is built in the lookup scope, which is the parent
            # except for enum literals (plan §3.3).
            prefix = o.get("scope", o["parent"])
            assert canon.format_qname(segs[:-1]) == prefix, f"{o['qname']}: qname is not under {prefix}"
            assert (o["ns"], o.get("unit"), o["parent"]) in keys or any(
                (o["ns"], o.get("unit"), o["parent"]) == (p["ns"], p.get("unit"), p["qname"]) for p in objects
            ), f"{o['qname']}: missing parent"
        else:
            assert o["ns"] == canon.root_ns(o["kind"]), f"{o['qname']}: root in the wrong name space"
        if "scope" in o:
            assert any(p["qname"] == o["scope"] for p in objects), f"{o['qname']}: missing scope"
        assert ("anonymous" in o.get("flags", ())) == o["name"].startswith("$")

    # Source order among siblings is a total order.
    siblings: dict[tuple, set[int]] = {}
    for o in objects:
        group = (o["ns"], o.get("unit"), o.get("parent"))
        assert o["pos"] not in siblings.setdefault(group, set()), f"{o['qname']}: repeated pos"
        siblings[group].add(o["pos"])

    qnames = {o["qname"] for o in objects}

    def resolves(target: str) -> bool:
        k = canon.parse_key(target)
        if k.qname in qnames:
            return True
        return canon.parse_qname(k.qname)[0] in EXTERNAL_ROOTS

    # Locations point at declared files.
    def locs(value):
        if isinstance(value, dict):
            if set(value) >= {"file", "line"}:
                yield value
            for v in value.values():
                yield from locs(v)
        elif isinstance(value, list):
            for v in value:
                yield from locs(v)

    for rec in records:
        for loc in locs(rec):
            assert loc["file"] in files, f"{rec}: unknown file {loc['file']}"
        for text, span in _iter_spans(rec):
            a, b = span["at"]
            assert 0 <= a < b <= len(text) and text[a:b] == span["name"], f"span {span} in {text!r}"
        for ref in _iter_refs(rec):
            if ref["target"] is not None:
                assert resolves(ref["target"]), f"dangling target {ref['target']}"

    for rec in records:
        r = rec["r"]
        if r == "body":
            assert rec["of"] in qnames
        elif r == "import":
            assert rec["scope"] in qnames
        elif r == "include":
            assert {rec["from"], rec["to"]} <= files
        elif r == "unit":
            assert set(rec.get("files", ())) <= files

    # Elaborations: key matches its parameters; sites and blocks exist; child
    # and top references name a known elaboration (or one outside the file
    # when the site is unresolved).
    elabs = {canon.elab_ref(e["def"], e["key"]): e for e in records if e["r"] == "elab"}
    for e in elabs.values():
        assert e["def"] in qnames
        if "params" in e:
            assert e["key"] == canon.elab_key((p["name"], p["value"]) for p in e["params"])
        for site in e.get("sites", ()):
            assert site["inst"] in qnames
            if "elab" in site:
                assert site["elab"] in elabs, f"unknown child elaboration {site['elab']}"
        for g in e.get("generate", ()):
            assert g["block"] in qnames
    for t in (r for r in records if r["r"] == "top"):
        assert t["elab"] in elabs

    # UVM bindings reference config accesses by id.
    configs = {r["id"]: r for r in records if r["r"] == "uvm.config"}
    for b in (r for r in records if r["r"] == "uvm.binding"):
        assert configs[b["set"]]["action"] == "set"
        assert all(configs[c]["action"] == "get" for c in b.get("consumers", ()))

    # Every object hashes (no floats, nothing unserializable).
    for o in objects:
        assert len(canon.object_hash(o)) == 64


# -- negative cases ------------------------------------------------------------

_MODULE = {
    "r": "object", "kind": "module", "ns": "design", "qname": "m", "name": "m", "pos": 0,
    "loc": {"file": "f1", "line": 1, "col": 8},
}
_INSTANCE = {
    "r": "object", "kind": "instance", "ns": "design", "qname": "m::u", "name": "u",
    "parent": "m", "pos": 0, "detail": {"of": {"name": "leaf", "target": "leaf"}},
}
_HEADER = {"r": "header", "format": "svdb", "schema": "1.0", "producer": {"name": "t"}}
_UVM_TYPE = {"r": "uvm.type", "type": {"name": "env"}, "kind": "component",
             "methods": {"build_phase": {"virtual": True, "calls": [{"step": 0, "method": "build_agents"}]}}}
_UVM_CHILD = {"r": "uvm.child", "owner": {"name": "env"}, "handle": "a", "type": {"name": "agent"},
              "method": "build_agents", "step": 0}
_UVM_OVERRIDE = {"r": "uvm.override", "original": {"name": "a"}, "replacement": {"name": "b"},
                 "kind": "inst", "inst_path": "env.*", "step": 2, "path_base": "owner"}


def _with(base: dict, **changes) -> dict:
    rec = copy.deepcopy(base)
    for path, value in changes.items():
        *parents, leaf = path.split("__")
        node = rec
        for p in parents:
            node = node.setdefault(p, {})
        if value is _DELETE:
            node.pop(leaf)
        else:
            node[leaf] = value
    return rec


_DELETE = object()

NEGATIVE = [
    ("missing qname", _with(_MODULE, qname=_DELETE), "qname"),
    ("unknown kind", _with(_MODULE, kind="widget"), "widget"),
    ("unit ns without unit", _with(_MODULE, kind="typedef", ns="unit"), "unit"),
    ("unit given outside unit ns", _with(_MODULE, unit="cu0"), "unit"),
    ("module in unit ns", _with(_MODULE, ns="unit", unit="cu0"), "design"),
    ("package in design ns", _with(_MODULE, kind="package"), "package"),
    ("macro outside macro ns", _with(_MODULE, kind="macro"), "macro"),
    ("non-macro in macro ns", _with(_MODULE, ns="macro"), "macro"),
    ("class as package-ns root", _with(_MODULE, kind="class", ns="package"), "package"),
    ("class as design-ns root", _with(_MODULE, kind="class"), "module"),
    ("instance without detail", _with(_INSTANCE, detail=_DELETE), "detail"),
    ("instance without of", _with(_INSTANCE, detail={}), "of"),
    ("bad instance state", _with(_INSTANCE, detail__state="maybe"), "maybe"),
    ("bad conn mode", _with(_INSTANCE, detail__conns=[{"pos": 0, "mode": "byname"}]), "byname"),
    ("line 0", _with(_MODULE, loc={"file": "f1", "line": 0}), "0"),
    ("unknown object field", _with(_MODULE, colour="red"), "colour"),
    ("detail field of another kind", _with(_MODULE, detail={"dir": "input"}), "dir"),
    ("bad hash", _with(_MODULE, hash="abc"), "abc"),
    ("bad qual", _with(_MODULE, quals=["sometimes"]), "sometimes"),
    ("span without at", _with(_MODULE, detail={"default_disable_iff": {"text": "x", "refs": [{"name": "x"}]}}), "at"),
    ("process without proc", {"r": "object", "kind": "process", "ns": "design", "qname": "m::p",
                              "name": "p", "parent": "m", "pos": 0, "detail": {}}, "proc"),
    ("newer major schema", _with(_HEADER, schema="2.0"), "2.0"),
    ("unknown section", _with(_HEADER, sections={"widgets": "complete"}), "widgets"),
    ("bad section status", _with(_HEADER, sections={"docs": "most"}), "most"),
    ("unknown record type", {"r": "widget"}, "widget"),
    ("elab key not hex16", {"r": "elab", "def": "m", "key": "xyz"}, "xyz"),
    ("uvm child negative step", _with(_UVM_CHILD, step=-1), "-1"),
    ("uvm conn step not integer", {"r": "uvm.conn", "owner": {"name": "env"}, "source": {}, "target": {},
                                   "step": "0"}, "'0'"),
    ("uvm method call without step", _with(_UVM_TYPE, methods={"build_phase": {"calls": [{"method": "m"}]}}), "step"),
    ("uvm method call negative step", _with(_UVM_TYPE, methods={"new": {"calls": [{"step": -2, "method": "m"}]}}),
     "-2"),
    ("uvm method unknown field", _with(_UVM_TYPE, methods={"new": {"args": []}}), "args"),
    ("uvm abstract not boolean", _with(_UVM_TYPE, abstract="yes"), "yes"),
    ("bad path_base", _with(_UVM_OVERRIDE, path_base="relative"), "relative"),
    ("path_base on a type override", _with(_UVM_OVERRIDE, kind="type"), "inst"),
    ("path_base without kind", _with(_UVM_OVERRIDE, kind=_DELETE), "kind"),
    ("replace true is left out", _with(_UVM_OVERRIDE, kind="type", path_base=_DELETE, replace=True), "False"),
    ("uvm override negative step", _with(_UVM_OVERRIDE, step=-1), "-1"),
]


POSITIVE = [
    ("uvm type with methods", _with(_UVM_TYPE, abstract=True)),
    ("uvm type inheriting everything", _with(_UVM_TYPE, methods={})),
    ("uvm child in a helper", _UVM_CHILD),
    ("uvm inst override", _UVM_OVERRIDE),
    ("uvm absolute inst override", _with(_UVM_OVERRIDE, path_base="absolute")),
    ("uvm type override, no replace", _with(_UVM_OVERRIDE, kind="type", path_base=_DELETE, replace=False)),
    ("uvm conn with method", {"r": "uvm.conn", "owner": {"name": "env"}, "source": {}, "target": {},
                              "method": "connect_agents", "step": 4}),
]


@pytest.mark.parametrize("label,record", POSITIVE, ids=[n[0] for n in POSITIVE])
def test_positive(validator, label, record):
    errors = sorted(validator.iter_errors(record), key=lambda e: e.json_path)
    assert not errors, f"{label}: " + "; ".join(f"{e.json_path}: {e.message}" for e in errors)


@pytest.mark.parametrize("label,record,token", NEGATIVE, ids=[n[0] for n in NEGATIVE])
def test_negative(validator, label, record, token):
    errors = list(validator.iter_errors(record))
    assert errors, f"{label}: expected the schema to reject {record}"
    text = " ".join(f"{e.json_path} {e.message}" for e in errors)
    # Errors under if/then come back as the failing subschema; walk context
    # too so the token can be found wherever the validator reports it.
    for e in errors:
        for sub in e.context or ():
            text += f" {sub.json_path} {sub.message}"
    assert token in text, f"{label}: {token!r} not in {text!r}"
