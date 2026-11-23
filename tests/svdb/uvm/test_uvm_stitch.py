"""Stitching real testbenches end to end (stitching plan §5.4).

Sources -> database (the frontend) -> tree (``Database.uvm_tree``).  Each row
of the plan's §5.1 table has its own assertion here, so regenerating the
golden (``SVDB_REGEN=1``) cannot quietly accept a regression.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.svdb import Database, exporter, importer
from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit

HERE = Path(__file__).parent
P = "stitch_tb_pkg::"


def _build(path: str, *tbs: str, **kw) -> None:
    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv")] + [str(UVM_TB / f"{tb}.sv") for tb in tbs],
                           **kw)
    write(parse(options), options, path).conn.close()


@pytest.fixture(scope="module")
def stitch_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("stitch") / "stitch.svdb")
    _build(path, "stitch_tb")
    with Database.open(path) as db:
        yield db


def _tree(db, root):
    return db.uvm_tree(P + root)


def _type(tree, path):
    node = tree.node("uvm_test_top." + path)
    assert node is not None, f"no node {path}"
    return node.type.removeprefix(P)


def _codes(tree):
    return {i.code for i in tree.issues}


@pytest.fixture(scope="module")
def st_test(stitch_db):
    return _tree(stitch_db, "st_test")


# -- the §5.1 table, row by row -------------------------------------------------------


def test_golden(stitch_db):
    data = stitch_db.uvm_tree().to_json()
    data["sources"] = [Path(s).name for s in data["sources"]]
    text = json.dumps(data, indent=1, sort_keys=True).replace(str(UVM_TB), "<uvm_tb>").replace(str(UVM_STUB), "<stub>")
    path = HERE / "stitch_tb.tree.expected.json"
    if os.environ.get("SVDB_REGEN"):
        path.write_text(text + "\n")
    assert json.loads(text) == json.loads(path.read_text())


def test_the_default_root_is_the_run_test(stitch_db):
    assert stitch_db.uvm_tree().root.type == P + "st_test"


def test_an_inherited_build_phase(stitch_db):
    tree = _tree(stitch_db, "inherit_test")
    assert {n.name for n in tree.nodes if n.parent == "uvm_test_top.inh"} == {"agt_a", "scb"}


def test_super_build_phase_merges_in_order(stitch_db):
    tree = _tree(stitch_db, "inherit_test")
    assert {n.name for n in tree.nodes if n.parent == "uvm_test_top.sup"} == {"agt_a", "agt_b", "scb"}


def test_a_build_phase_without_super_drops_the_base_children(stitch_db):
    tree = _tree(stitch_db, "inherit_test")
    assert {n.name for n in tree.nodes if n.parent == "uvm_test_top.nosup"} == {"agt_b"}


def test_a_type_override_after_the_create_reaches_descendants(st_test):
    assert _type(st_test, "env.agt_b.drv") == "fast_drv"


def test_a_type_override_of_the_env_after_its_create_does_not_apply(st_test):
    assert _type(st_test, "env") == "sup_env"


def test_chained_overrides(st_test):
    assert _type(st_test, "env.agt_a.mon") == "mon_c"
    assert [v.replacement.removeprefix(P) for v in st_test.node("uvm_test_top.env.agt_a.mon").via] == [
        "mon_b", "mon_c"]


def test_a_relative_inst_override_matches_only_its_subtree(st_test):
    assert _type(st_test, "env.agt_a.drv") == "slow_drv"
    assert _type(st_test, "env.agt_b.drv") == "fast_drv"


def test_an_absolute_inst_override_matches_only_its_path(st_test):
    assert _type(st_test, "env.agt_b.mon") == "mon_x"
    assert _type(st_test, "env.agt_a.mon") == "mon_c"


def test_an_inst_override_beats_a_type_override(st_test):
    """``st_mon`` has a type override (to mon_b, chained to mon_c) everywhere;
    agt_b.mon's inst override wins there."""
    assert _type(st_test, "env.agt_b.mon") == "mon_x"


def test_a_sibling_built_earlier_reaches_a_later_siblings_subtree(st_test):
    assert _type(st_test, "b_agent.drv") == "slow_drv"


def test_a_path_relative_to_the_sibling_itself_matches_nothing(st_test):
    o = next(o for o in st_test.overrides if o.inst_path == "b_agent.mon")
    assert o.status == "unused"


def test_replace_zero_leaves_the_global_override(st_test):
    assert _type(st_test, "env.agt_a.seqr") == "top_seqr"
    assert "override_ignored" in _codes(st_test)


def test_an_override_in_a_childs_constructor(st_test):
    assert _type(st_test, "env.scb") == "big_scb"
    o = next(o for o in st_test.overrides if o.replacement == P + "big_scb")
    assert o.registered_by == ["uvm_test_top.env"]


def test_an_override_in_run_phase_is_unplaced(st_test):
    o = next(o for o in st_test.overrides if o.method == "run_phase")
    assert o.status == "unplaced"


def test_an_override_through_another_object_is_unplaced(st_test):
    o = next(o for o in st_test.overrides if o.method == "apply_overrides")
    assert o.status == "unplaced"
    assert "unplaced_override" in _codes(st_test)


def test_a_conditional_create(stitch_db, st_test):
    assert st_test.node("uvm_test_top.env.agt_a.drv").conditional
    tree = stitch_db.uvm_tree(P + "st_test", include_conditional=False)
    assert tree.node("uvm_test_top.env.agt_a.drv") is None
    assert tree.node("uvm_test_top.env.agt_a.mon") is not None


def test_a_loop_create_is_one_node(stitch_db):
    tree = _tree(stitch_db, "helper_test")
    assert tree.node("uvm_test_top.env.agts[*]").multiplicity == "N"


def test_a_helper_called_before_the_create(st_test):
    o = next(o for o in st_test.overrides if o.replacement == P + "fast_drv")
    assert o.method == "set_overrides" and o.status == "applied"


def test_a_helper_called_after_the_create(stitch_db):
    tree = _tree(stitch_db, "late_test")
    assert _type(tree, "env") == "sup_env"
    assert _type(tree, "env.agt_a.drv") == "fast_drv"
    # the registry form, relative to the test
    assert _type(tree, "env.agt_b.mon") == "mon_c"


def test_a_redefined_virtual_helper_runs_with_its_super_call(stitch_db):
    tree = _tree(stitch_db, "derived_test")
    assert _type(tree, "env.agt_a") == "big_agent"
    assert _type(tree, "env.agt_b.drv") == "fast_drv"
    # big_agent inherits st_agent's build_phase
    assert _type(tree, "env.agt_a.mon") == "mon_c"


def test_creates_and_connections_in_helpers(stitch_db):
    tree = _tree(stitch_db, "helper_test")
    assert tree.node("uvm_test_top.env.scb").conditional
    link = next(k for k in tree.links if k.source.path == "uvm_test_top.env.agts[*].mon")
    assert (link.target.path, link.multiplicity) == ("uvm_test_top.env.scb", "N")


def test_helper_recursion_is_an_issue(stitch_db):
    assert "inline_cycle" in _codes(_tree(stitch_db, "helper_test"))


def test_a_link_through_super_connect_phase(st_test):
    ends = {(k.source.path, k.target.path) for k in st_test.links}
    assert ("uvm_test_top.env.agt_a.mon", "uvm_test_top.env.scb") in ends
    assert ("uvm_test_top.env.agt_b.mon", "uvm_test_top.env.scb") in ends


def test_a_link_through_two_handles(st_test):
    assert any(k.source == type(k.source)("uvm_test_top.env.agt_b.drv", "seq_item_port")
               and k.owner == "uvm_test_top.env" for k in st_test.links)


def test_a_link_to_a_handle_never_created(stitch_db):
    tree = _tree(stitch_db, "helper_test")
    assert any(k.state == "unresolved" and "ghost" in k.text for k in tree.links)


def test_an_inherited_connect_phase_naming_unbuilt_children(stitch_db):
    tree = _tree(stitch_db, "inherit_test")
    assert any(k.state == "unresolved" and k.owner == "uvm_test_top.nosup" for k in tree.links)


def test_a_global_override(st_test):
    o = next(o for o in st_test.overrides if o.replacement == P + "top_seqr")
    assert o.owner == "st_tb_top" and o.status == "applied"


def test_an_abstract_base_never_instantiated_is_quiet(st_test):
    assert "abstract_instance" not in _codes(st_test)


# -- two databases ------------------------------------------------------------------


@pytest.fixture(scope="module")
def vip_dbs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("vip")
    vip, tb = str(tmp / "vip.svdb"), str(tmp / "tb.svdb")
    _build(vip, "stitch_vip")
    _build(tb, "stitch_vip", "stitch_vip_tb")
    # A testbench database that does not describe the VIP's classes, as one
    # built against the VIP as an external would not.
    tb_only = str(tmp / "tb_only.svdb")
    with Database.open(tb) as db:
        recs = [r for r in exporter.iter_records(db.connection()) if not _vip_record(r)]
    importer.import_stream((json.dumps(r) for r in recs), tb_only).conn.close()
    return vip, tb, tb_only


def _vip_record(rec: dict) -> bool:
    ref = rec.get("type") if rec["r"] == "uvm.type" else rec.get("owner")
    return rec["r"] in ("uvm.type", "uvm.child", "uvm.conn") and (ref or {}).get("target", "").startswith("vip_pkg::")


def _summary(tree):
    return ([(n.path, n.type) for n in tree.nodes],
            sorted((k.source.path, k.source.port, k.target.path, k.target.port) for k in tree.links))


def test_the_vip_subtree_comes_from_the_vip_database(vip_dbs):
    vip, _tb, tb_only = vip_dbs
    with Database.open([tb_only]) as db:
        alone = db.uvm_tree()
    assert alone.node("uvm_test_top.env.mst").state == "unresolved"
    with Database.open([tb_only, vip]) as db:
        tree = db.uvm_tree()
    assert tree.node("uvm_test_top.env.mst.drv").type == "vtb_pkg::fast_vip_driver"
    assert tree.node("uvm_test_top.env.slv.seqr").type == "vip_pkg::vip_sequencer"
    links = {(k.source.path, k.target.path) for k in tree.links}
    assert ("uvm_test_top.env.mst.drv", "uvm_test_top.env.mst.seqr") in links
    assert ("uvm_test_top.env.slv.mon", "uvm_test_top.env.scb") in links
    assert all(k.state == "ok" for k in tree.links)


def test_federation_equals_one_database(vip_dbs):
    vip, tb, tb_only = vip_dbs
    with Database.open([tb]) as db:
        one = db.uvm_tree()
    with Database.open([tb_only, vip]) as db:
        two = db.uvm_tree()
    with Database.open([tb, vip]) as db:
        both = db.uvm_tree()
    assert _summary(one) == _summary(two) == _summary(both)
    assert "ambiguous_type" not in _codes(both)


# -- consistency with the Sphinx walk (plan D2) ---------------------------------------


@pytest.mark.parametrize("tb", ["basic_tb", "tlm_tb", "config_tb", "bridge_tb"])
def test_the_stitched_tree_matches_the_walk(tmp_path, tb):
    """With no overrides in play the stitched tree is the declared-type walk,
    laid out as instances."""
    from tests.conftest import uvm_stub_index

    structure = uvm_stub_index(f"{tb}.sv").uvm_structure
    walked = set()

    def visit(type_name, path, depth):
        walked.add((path, type_name.split("#")[0]))
        for c in structure.children_of(type_name):
            name = c.inst_name or c.handle
            if c.multiplicity != "1":
                name = c.inst_name or f"{c.handle}[*]"
            if depth < 16:
                visit(c.type_name, f"{path}.{name}", depth + 1)

    visit(structure.root, "uvm_test_top", 0)
    path = str(tmp_path / f"{tb}.svdb")
    _build(path, tb)
    with Database.open(path) as db:
        tree = db.uvm_tree()
    stitched = {(n.path, n.declared.rsplit("::", 1)[-1]) for n in tree.nodes}
    assert stitched == walked


# -- D1: the live provider stitches the same tree ---------------------------------------


@pytest.mark.parametrize("root", ["", "st_test", "derived_test", "late_test", "helper_test", "inherit_test"])
def test_the_live_provider_stitches_the_database_tree(stitch_db, root):
    """``sv:uvm-tree :resolved:`` stitches the provider's records without
    writing a database; the result must be the one ``svdb uvm-tree`` gives."""
    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "stitch_tb.sv")])
    live = parse(options).uvm_provider.uvm_tree(root).to_json()
    stored = stitch_db.uvm_tree(P + root if root else None).to_json()
    live.pop("sources"), stored.pop("sources")
    assert live == stored


@pytest.mark.parametrize("root", ["", "derived_test"])
def test_a_database_backed_index_stitches_from_the_database(stitch_db, root):
    """With ``sv_databases``, ``sv:uvm-tree :resolved:`` reads the stored
    per-class records; no sources are parsed."""
    from sphinx_systemverilog.model.db import DbIndex

    index = DbIndex([str(stitch_db.paths[0])])
    tree = index.uvm_provider.uvm_tree(root)
    assert tree.to_json() == stitch_db.uvm_tree(P + root if root else None).to_json()
    assert index._live is None
