"""D1-TEST-3: the read API, on the bundled examples and across two files."""

from __future__ import annotations

import pytest

from sphinx_systemverilog import svdb
from sphinx_systemverilog.svdb.database import AmbiguousKey, Database, Unresolved
from sphinx_systemverilog.svdb.issues import SvdbError
from sphinx_systemverilog.svdb.writer import write

from .conftest import HEADER, example, obj, typeref

pytestmark = pytest.mark.unit


def test_get_and_members_minimal(example_db):
    db = example_db("minimal.ndjson")
    counter = db.get("counter")
    assert counter.kind == "module" and counter.ns == "design" and counter.parent is None
    members = db.members(counter)
    assert [m.pos for m in members] == sorted(m.pos for m in members)
    assert all(m.parent == "counter" for m in members)
    assert db.parent(members[0]) == counter
    assert counter.loc.path and counter.loc.line >= 1


def test_get_accepts_dots_and_bare_names(example_db):
    db = example_db("classes.ndjson")
    assert db.get("env_pkg.base_item").qname == "env_pkg::base_item"
    assert db.get("word_item").qname == "env_pkg::word_item"
    assert db.get("no_such_thing") is None
    with pytest.raises(AmbiguousKey):
        db.get("render")  # base_item::render and printable::render


def test_doc_body_detail(example_db):
    db = example_db("classes.ndjson")
    c = db.get("env_pkg::base_item")
    assert c.doc.text.startswith("Base for every item") and c.doc.style == "doxygen"
    assert c.detail["virtual"] is True
    assert db.get("env_pkg::base_item::c_sane").body == "{ payload != 0; }"
    assert db.get("env_pkg::word_item").body is None


def test_find(example_db):
    db = example_db("classes.ndjson")
    classes = db.find("env_pkg::*", kind="class")
    assert [o.qname for o in classes] == sorted(o.qname for o in classes)
    assert {o.kind for o in classes} == {"class"}
    assert len(db.find("env_pkg::*", limit=3)) == 3


def test_bases_derived_references(example_db):
    db = example_db("classes.ndjson")
    base = db.get("env_pkg::base_item")
    ext, impl = db.bases(base)
    assert isinstance(ext, Unresolved) and ext.target == "uvm_pkg::uvm_sequence_item"
    assert impl.qname == "env_pkg::printable"
    assert [o.qname for o in db.derived(base)] == ["env_pkg::word_item"]
    assert [o.qname for o in db.derived(db.get("env_pkg::printable"), transitive=True)] == [
        "env_pkg::base_item", "env_pkg::word_item"]
    refs = db.references(base)
    assert [(r.source.qname, r.role) for r in refs] == [("env_pkg::word_item", "extends")]


def test_structure_queries(example_db):
    db = example_db("structure.ndjson")
    top, leaf = db.get("tb_top"), db.get("leaf")
    assert "tb_top::u_named" in [i.qname for i in db.instances(top)]
    assert "tb_top::g_lane::u_l" in [i.qname for i in db.used_by(leaf)]
    conns = db.connections(db.get("tb_top::u_named"))
    assert [(c.port, c.dir) for c in conns] == [("clk", "input"), ("d", "input"), ("q", "output")]
    assert conns[0].port_object.qname == "leaf::clk"
    assert [s.qname for s in conns[1].signals] == ["tb_top::d8"]
    peers = {(i.qname, c.port) for i, c in db.peers(db.get("tb_top::d8"))}
    assert ("tb_top::u_named", "d") in peers
    keys = {e["key"] for e in db.elaborations(leaf)}
    assert len(keys) == 2

    tree = db.tree(top)
    assert tree.instance is None and tree.definition.qname == "tb_top" and not tree.truncated
    by_inst = {c.instance.qname: c for c in tree.children}
    assert by_inst["tb_top::u_named"].definition.qname == "leaf"
    assert by_inst["tb_top::u_named"].count == 1
    assert by_inst["tb_top::g_lane::u_l"].count == 4
    # ``tb_top::u_vip`` names no elaboration (an unresolved instance, D3c):
    # the site is still a child, with nothing to descend into.
    assert by_inst["tb_top::u_vip"].definition is None
    assert db.tree(top, depth=0).children == ()
    shallow = db.tree(top, cap=1)
    assert shallow.truncated and all(c.children == () for c in shallow.children)
    assert any(c.truncated for c in shallow.children if c.definition is not None)


@pytest.mark.parametrize("name", svdb.example_names())
def test_every_object_reads_back(example_db, name):
    db = example_db(name)
    want = {(r["ns"], r.get("unit"), r["qname"]) for r in example(name) if r["r"] == "object"}
    got = set()
    for o in db.find("*", limit=None):
        got.add((o.ns, o.unit, o.qname))
        assert db.record(o)["qname"] == o.qname
    assert got == want


# -- federation ------------------------------------------------------------------


@pytest.fixture
def two_files(tmp_path):
    vip = tmp_path / "vip.svdb"
    tb = tmp_path / "tb.svdb"
    write(vip, [dict(HEADER, role="external"), obj("vip_pkg", "package"), obj("vip_pkg::vip_base", "class"),
                obj("shared", "package", pos=1), obj("shared::T", "typedef")])
    write(tb, [HEADER, obj("tb_pkg", "package"),
               obj("tb_pkg::my_comp", "class", detail={"extends": typeref("vip_base", "vip_pkg::vip_base")}),
               obj("tb_pkg::other", "class", pos=1, detail={"extends": typeref("my_comp")}),
               obj("shared", "package", pos=1), obj("shared::T", "typedef", sig="local")])
    return tb, vip


def test_federation_follows_references_across_files(two_files):
    tb, vip = two_files
    with Database.open([tb, vip]) as db:
        base = db.get("vip_pkg::vip_base")
        assert base.path == str(vip)
        (b,) = db.bases(db.get("tb_pkg::my_comp"))
        assert b == base
        assert [o.qname for o in db.derived(base, transitive=True)] == ["tb_pkg::my_comp", "tb_pkg::other"]
        assert [r.source.qname for r in db.references(base)] == ["tb_pkg::my_comp"]
        assert db.headers[1]["role"] == "external"


def test_federation_precedence_and_duplicates(two_files, caplog):
    tb, vip = two_files
    with Database.open([tb, vip]) as db:
        assert db.get("shared::T").sig == "local", "the first file wins"
        db.get("shared::T")
        assert db.duplicates == {"package:shared::T": [str(tb), str(vip)]}
        assert sum("shared::T" in r.message for r in caplog.records) == 1, "reported once"
    with Database.open([vip, tb]) as db:
        assert db.get("shared::T").sig is None


def test_open_refuses_other_layouts(tmp_path):
    import sqlite3

    p = tmp_path / "x.svdb"
    write(p, [HEADER])
    conn = sqlite3.connect(p)
    conn.execute("UPDATE meta SET value = '999' WHERE key = 'layout_version'")
    conn.commit()
    conn.close()
    with pytest.raises(SvdbError, match="re-import"):
        Database.open(p)
    with pytest.raises(SvdbError, match="no such database"):
        Database.open(tmp_path / "missing.svdb")


def test_database_is_read_only(two_files):
    import sqlite3

    tb, _ = two_files
    with Database.open(tb) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.sql("DELETE FROM object")
