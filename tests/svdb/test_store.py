"""D1-TEST-1 and D1-TEST-2: the store round-trips, and the writer reports
what it must."""

from __future__ import annotations

import io
import json
import sqlite3

import pytest

from sphinx_systemverilog import svdb
from sphinx_systemverilog.svdb import canon, exporter, importer, layout
from sphinx_systemverilog.svdb.database import AmbiguousKey
from sphinx_systemverilog.svdb.issues import SvdbError

from .conftest import HEADER, example, memory_db, obj, typeref

pytestmark = pytest.mark.unit

EXAMPLES = svdb.example_names()


def canonical(recs: list[dict]) -> list[dict]:
    """The export the plan promises for *recs*, computed independently of the
    exporter: hashes filled in, flags in schema order, objects by key, bodies
    after them in the same order, everything else in input order by type."""
    order = {r: i for i, r in enumerate(layout.EXPORT_ORDER)}
    recs = [dict(r) for r in recs]
    bodies = {b["of"]: b["text"] for b in recs if b["r"] == "body"}
    objects = {}
    for r in recs:
        if r["r"] == "object":
            if "flags" in r:
                r["flags"] = [f for f in layout.FLAGS if f in r["flags"]]
            if "hash" not in r:
                r["hash"] = canon.object_hash(r, body=bodies.get(r["qname"]))
            objects[r["qname"]] = r

    def key(item):
        i, r = item
        if r["r"] in ("object", "body"):
            o = r if r["r"] == "object" else objects[r["of"]]
            return (order[r["r"]], o["ns"], o.get("unit", ""), o["qname"])
        return (order[r["r"]], i)

    return [r for _, r in sorted(enumerate(recs), key=key)]


@pytest.mark.parametrize("name", EXAMPLES)
def test_round_trip_equals_canonical_input(name):
    db, w = memory_db(example(name))
    assert [i for i in w.issues if i.severity == "error"] == []
    assert list(exporter.iter_records(db.connection())) == canonical(example(name))


@pytest.mark.parametrize("name", EXAMPLES)
def test_export_is_a_fixed_point(tmp_path, name):
    src = tmp_path / "in.ndjson"
    src.write_text(svdb.example_text(name))
    importer.import_file(src, tmp_path / "a.svdb")
    exporter.export_file(tmp_path / "a.svdb", tmp_path / "a.ndjson")
    importer.import_file(tmp_path / "a.ndjson", tmp_path / "b.svdb")
    exporter.export_file(tmp_path / "b.svdb", tmp_path / "b.ndjson")
    assert (tmp_path / "a.ndjson").read_bytes() == (tmp_path / "b.ndjson").read_bytes()


def test_file_build_is_atomic_and_compact(tmp_path):
    out = tmp_path / "x.svdb"
    out.write_text("previous")
    bad = [HEADER, obj("p", "package"), obj("p", "package", pos=1)]
    with pytest.raises(SvdbError):
        svdb.writer.write(out, bad)
    assert out.read_text() == "previous", "a failed build leaves the old file alone"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.svdb"]

    svdb.writer.write(out, [HEADER, obj("p", "package")])
    conn = sqlite3.connect(out)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not {t for t in tables if t.startswith("stg_")}, "staging tables are dropped"
    assert "sqlite_stat1" in tables, "ANALYZE ran"
    assert conn.execute("SELECT value FROM meta WHERE key = 'layout_version'").fetchone()[0] == str(
        layout.LAYOUT_VERSION)
    conn.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.svdb"]


def test_batches_smaller_than_the_input():
    # A batch size of 2 exercises every flush path.
    w = svdb.Writer(":memory:", batch=2)
    for rec in example("classes.ndjson"):
        w.add(rec)
    w.finish()
    assert list(exporter.iter_records(w.conn)) == canonical(example("classes.ndjson"))


# -- D1-TEST-2: errors and warnings ---------------------------------------------


def _codes(issues, severity=None):
    return [i.code for i in issues if severity is None or i.severity == severity]


def test_duplicate_key_reports_both_locations():
    recs = [HEADER, {"r": "file", "id": "f1", "path": "a.sv"},
            obj("p", "package", loc={"file": "f1", "line": 3}),
            obj("p", "package", pos=1, loc={"file": "f1", "line": 9})]
    with pytest.raises(SvdbError) as e:
        memory_db(recs)
    dup = [i for i in e.value.issues if i.code == "DuplicateKey"]
    assert len(dup) == 1 and "a.sv:3" in dup[0].message and "a.sv:9" in dup[0].message


def test_same_qname_in_two_name_spaces_is_not_a_duplicate():
    db, _ = memory_db([HEADER, obj("foo", "package"), obj("foo", "module", ns="design")])
    with pytest.raises(AmbiguousKey):
        db.get("foo")
    assert db.get("package:foo").kind == "package"
    assert db.get("design:foo").kind == "module"


def test_bad_parent_kind():
    recs = [HEADER, obj("p", "package"), obj("p::C", "class"),
            obj("p::C::a", "port", detail={"dir": "input"})]
    with pytest.raises(SvdbError) as e:
        memory_db(recs)
    assert _codes(e.value.issues, "error") == ["BadParentKind"]
    assert "port cannot be a child of a class" in str(e.value)


def test_bad_root_kind():
    with pytest.raises(SvdbError) as e:
        memory_db([HEADER, obj("x", "constraint", ns="unit", unit="cu0")])
    assert "BadRootKind" in _codes(e.value.issues)


def test_dangling_parent_body_and_elab():
    recs = [HEADER, obj("p::C", "class"), {"r": "body", "of": "q::x", "text": "..."},
            {"r": "elab", "def": "nope", "key": "e3b0c44298fc1c14"}]
    _, w = memory_db(recs, strict=False)
    assert set(_codes(w.issues, "error")) == {"DanglingParent", "DanglingBody", "DanglingElab"}


def test_unsupported_major_version_is_refused():
    with pytest.raises(SvdbError, match="2.0"):
        memory_db([dict(HEADER, schema="2.0")])


def test_header_must_come_first():
    with pytest.raises(SvdbError, match="header"):
        memory_db([obj("p", "package"), HEADER])


def test_newer_minor_content_is_ignored_with_one_warning_each():
    recs = [dict(HEADER, schema="1.9", sections={"objects": "complete", "widgets": "complete"}),
            obj("p", "package", colour="red"),
            obj("p::C", "class", colour="blue"),
            {"r": "widget", "x": 1}, {"r": "widget", "x": 2},
            obj("p::g", "gizmo", pos=1), obj("p::h", "gizmo", pos=2),
            obj("p::g::inner", "class"), obj("p::g::inner::deeper", "class")]
    db, w = memory_db(recs)
    assert sorted(_codes(w.issues)) == ["NewerMinor", "UnknownField", "UnknownKind", "UnknownRecord",
                                        "UnknownSection"]
    assert all(i.severity == "warning" for i in w.issues)
    assert [o.qname for o in db.find("*")] == ["p", "p::C"], "children of unknown kinds go with them"
    assert "colour" not in db.record(db.get("p"))


def test_unit_collisions_are_accepted_and_bare_lookup_is_ambiguous():
    recs = [HEADER, {"r": "unit", "id": "cu0"}, {"r": "unit", "id": "cu1"},
            obj("byte_t", "typedef", ns="unit", unit="cu0"),
            obj("byte_t", "typedef", ns="unit", unit="cu1")]
    db, w = memory_db(recs)
    assert _codes(w.issues) == []
    with pytest.raises(AmbiguousKey) as e:
        db.get("byte_t")
    assert sorted(canon.format_key(o.key, qualify=True) for o in e.value.candidates) == [
        "$unit[cu0]::byte_t", "$unit[cu1]::byte_t"]
    assert db.get("$unit[cu1]::byte_t").unit == "cu1"


def test_section_declared_absent_but_present():
    recs = [dict(HEADER, sections={"docs": "absent", "bodies": "absent"}),
            obj("p", "package", doc={"text": "hi"})]
    with pytest.raises(SvdbError) as e:
        memory_db(recs)
    assert _codes(e.value.issues, "error") == ["SectionAbsent"]


def test_missing_required_field():
    _, w = memory_db([HEADER, {"r": "object", "kind": "package", "ns": "package", "name": "p", "pos": 0}],
                     strict=False)
    assert _codes(w.issues) == ["MissingField"]


def test_root_in_wrong_name_space():
    _, w = memory_db([HEADER, obj("m", "module", ns="package")], strict=False)
    assert _codes(w.issues) == ["RootNamespace"]


def test_unknown_file_and_unit_are_warnings():
    db, w = memory_db([HEADER, obj("t", "typedef", ns="unit", unit="cu9", loc={"file": "f7", "line": 2})])
    assert sorted(_codes(w.issues, "warning")) == ["UnknownFile", "UnknownUnit"]
    assert db.get("t").loc.path is None


def test_bad_ndjson_line():
    with pytest.raises(SvdbError, match=r"x\.ndjson:2: not JSON"):
        importer.import_stream(io.StringIO(json.dumps(HEADER) + "\n{oops\n"), ":memory:", name="x.ndjson")


# -- hashes ----------------------------------------------------------------------


def test_hash_is_computed_when_absent_and_kept_when_given():
    given = "ab" * 32
    recs = [HEADER, obj("p", "package"), obj("p::s", "sequence", detail={}),
            obj("q", "package", pos=1, hash=given), {"r": "body", "of": "p::s", "text": "a ##1 b"}]
    db, _ = memory_db(recs)
    assert db.get("p").hash == canon.object_hash(obj("p", "package"))
    assert db.get("p::s").hash == canon.object_hash(obj("p::s", "sequence", detail={}), body="a ##1 b")
    assert db.get("q").hash == given


# -- reference resolution (§3.4) ---------------------------------------------------


def _resolution_db(*extra):
    recs = [HEADER, obj("q", "package"), obj("q::B", "class"), obj("r", "package", pos=1),
            obj("r::Only", "class"), obj("p", "package", pos=2),
            {"r": "import", "scope": "p", "package": {"name": "q", "target": "q"}, "item": "*"},
            *extra]
    return memory_db(recs)[0]


def _base(db, qname):
    (b,) = db.bases(db.get(qname))
    return getattr(b, "qname", b)


def test_resolution_prefers_the_enclosing_scope():
    db = _resolution_db(obj("p::B", "class"), obj("p::C", "class", pos=1, detail={"extends": typeref("B")}))
    assert _base(db, "p::C") == "p::B"


def test_resolution_then_wildcard_imports():
    db = _resolution_db(obj("p::C", "class", detail={"extends": typeref("B")}))
    assert _base(db, "p::C") == "q::B"


def test_resolution_then_a_unique_bare_name():
    db = _resolution_db(obj("p::C", "class", detail={"extends": typeref("Only")}))
    assert _base(db, "p::C") == "r::Only"


def test_resolution_of_a_qualified_name_and_failure():
    db = _resolution_db(obj("p::C", "class", detail={"extends": typeref("r::Only")}),
                        obj("p::D", "class", pos=1, detail={"extends": typeref("Missing")}))
    assert _base(db, "p::C") == "r::Only"
    missing = _base(db, "p::D")
    assert missing.name == "Missing" and missing.target is None


def test_producer_targets_are_kept_on_export():
    db = _resolution_db(obj("p::C", "class", detail={"extends": typeref("B")}))
    exported = db.record(db.get("p::C"))
    assert "target" not in exported["detail"]["extends"]["refs"][0], "best-effort resolution is not exported"
