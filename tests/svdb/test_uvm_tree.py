"""The stitcher over hand-written records (stitching plan §5.3).

No pyslang: each test imports a handful of ``uvm.*`` records and stitches
them, so the factory rules are pinned down exactly, one per test.  The
end-to-end cases over real sources are in ``tests/svdb/uvm/test_uvm_stitch.py``.
"""

from __future__ import annotations

import json

import pytest

from sphinx_systemverilog import svdb
from sphinx_systemverilog.svdb import Database, importer
from sphinx_systemverilog.svdb.uvm_tree import render_dot, render_text

pytestmark = pytest.mark.unit

HEADER = {"r": "header", "format": "svdb", "schema": "1.0", "producer": {"name": "test"},
          "sections": {"uvm.tree": "complete", "uvm.overrides": "complete"}}


def ref(key):
    return {"name": key.rsplit("::", 1)[-1], "target": key}


def T(key, base="uvm::uvm_component", methods=None, **kw):
    rec = {"r": "uvm.type", "type": ref(key), "base": ref(base), "kind": "component", **kw}
    rec["methods"] = methods if methods is not None else {"build_phase": {"virtual": True}}
    return rec


def C(owner, handle, type_key, step, **kw):
    return {"r": "uvm.child", "owner": ref(owner), "handle": handle, "inst_name": kw.pop("inst_name", handle),
            "type": ref(type_key), "step": step, **kw}


def O(owner, original, replacement, step=None, method="build_phase", **kw):
    rec = {"r": "uvm.override", "original": ref(original), "replacement": ref(replacement),
           "owner": ref(owner), "method": method, **kw}
    if step is not None:
        rec["step"] = step
    return rec


def W(owner, source, target, step, **kw):
    """A connection: *source*/*target* are ``(path tuple, port)``."""
    return {"r": "uvm.conn", "owner": ref(owner), "source": {"path": list(source[0]), "port": source[1]},
            "target": {"path": list(target[0]), "port": target[1]}, "kind": kw.pop("kind", "analysis"),
            "step": step, **kw}


def ROOT(key):
    return {"r": "uvm.root", "root": ref(key)}


def db_of(*recs):
    w = importer.import_stream([json.dumps(HEADER)] + [json.dumps(r) for r in recs], ":memory:")
    return Database.from_connection(w.conn)


def stitch(*recs, root="p::test", **kw):
    return db_of(*recs).uvm_tree(root, **kw)


def types(tree):
    return {n.path: n.type for n in tree.nodes}


# a test that builds env, which builds agt, which builds drv
BASE = [
    T("p::test"), T("p::env"), T("p::agt"), T("p::drv"), T("p::drv2", base="p::drv"),
    T("p::drv3", base="p::drv"), T("p::env2", base="p::env"),
    C("p::test", "env", "p::env", 5),
    C("p::env", "agt", "p::agt", 0),
    C("p::agt", "drv", "p::drv", 0),
]


# -- shape -------------------------------------------------------------------------


def test_the_tree_follows_the_creates():
    tree = stitch(*BASE)
    assert [n.path for n in tree.nodes] == [
        "uvm_test_top", "uvm_test_top.env", "uvm_test_top.env.agt", "uvm_test_top.env.agt.drv"]
    assert tree.node("uvm_test_top.env.agt").parent == "uvm_test_top.env"


def test_children_are_built_in_name_order():
    tree = stitch(T("p::test"), T("p::x"), C("p::test", "zed", "p::x", 0), C("p::test", "alpha", "p::x", 1))
    assert tree.root.children == ["uvm_test_top.alpha", "uvm_test_top.zed"]


def test_the_root_name_is_configurable():
    assert stitch(*BASE, name="top").root.path == "top"


def test_the_default_root_is_the_uvm_root_record():
    assert db_of(*BASE, ROOT("p::test")).uvm_tree().root.type == "p::test"


def test_no_root_is_a_lookup_error():
    with pytest.raises(LookupError):
        db_of(*BASE).uvm_tree()
    with pytest.raises(LookupError):
        db_of(*BASE).uvm_tree("p::nothing")


def test_a_bare_root_name_resolves():
    assert stitch(*BASE, root="test").root.type == "p::test"


# -- type overrides ------------------------------------------------------------------


def test_a_type_override_before_the_create_applies():
    tree = stitch(*BASE, O("p::test", "p::env", "p::env2", 2))
    assert types(tree)["uvm_test_top.env"] == "p::env2"
    assert tree.node("uvm_test_top.env").declared == "p::env"


def test_a_type_override_after_the_create_reaches_only_descendants():
    tree = stitch(*BASE, O("p::test", "p::env", "p::env2", 9), O("p::test", "p::drv", "p::drv2", 10))
    assert types(tree)["uvm_test_top.env"] == "p::env"
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"


def test_a_later_override_of_the_same_type_replaces_the_earlier():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), O("p::test", "p::drv", "p::drv3", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv3"
    first, second = tree.overrides
    assert (first.status, second.status) == ("unused", "applied")


def test_replace_zero_leaves_the_earlier_one():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), O("p::test", "p::drv", "p::drv3", 1, replace=False))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"
    assert "override_ignored" in {i.code for i in tree.issues}


def test_overrides_chain():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), O("p::test", "p::drv2", "p::drv3", 1))
    drv = tree.node("uvm_test_top.env.agt.drv")
    assert drv.type == "p::drv3"
    assert [v.replacement for v in drv.via] == ["p::drv2", "p::drv3"]


def test_a_loop_builds_the_type_asked_for():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), O("p::test", "p::drv2", "p::drv", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv"
    assert "override_loop" in {i.code for i in tree.issues}


def test_a_self_override_cancels_an_earlier_one():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), O("p::test", "p::drv", "p::drv", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv"


def test_new_children_keep_their_declared_type():
    tree = stitch(T("p::test"), T("p::drv"), T("p::drv2", base="p::drv"),
                  O("p::test", "p::drv", "p::drv2", 0),
                  C("p::test", "drv", "p::drv", 1, created_by="new"))
    assert types(tree)["uvm_test_top.drv"] == "p::drv"


# -- inst overrides ------------------------------------------------------------------


def INST(owner, original, replacement, path, step, base="owner", **kw):
    return O(owner, original, replacement, step, kind="inst", inst_path=path, path_base=base, **kw)


def test_an_owner_relative_path_is_rooted_at_the_registering_component():
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", "env.agt.drv", 0))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"
    assert tree.overrides[0].registered_by == ["uvm_test_top"]


def test_an_absolute_path_is_used_as_written():
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", "uvm_test_top.env.agt.drv", 0, base="absolute"))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"


def test_a_path_without_a_wildcard_must_match_exactly():
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", "env.agt", 0))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv"
    assert tree.overrides[0].status == "unused"


@pytest.mark.parametrize("pattern,hit", [("env.*", True), ("env.agt.dr?", True), ("env.?", False), ("*", True)])
def test_glob_paths(pattern, hit):
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", pattern, 0))
    assert (types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2") is hit


def test_the_first_registered_inst_override_wins():
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", "env.*", 0),
                  INST("p::test", "p::drv", "p::drv3", "env.agt.drv", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"


def test_an_inst_override_beats_a_type_override():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv3", 0), INST("p::test", "p::drv", "p::drv2", "env.*", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"


def test_an_inst_override_applies_to_what_a_type_override_produced():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0), INST("p::test", "p::drv2", "p::drv3", "env.*", 1))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv3"


def test_an_unknown_path_base_is_not_applied():
    tree = stitch(*BASE, INST("p::test", "p::drv", "p::drv2", "env.*", 0, base="unknown"))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv"
    assert tree.overrides[0].status == "unapplied"


def test_a_computed_path_is_not_applied():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0, kind="inst", inst_path=None, path_base="owner"))
    assert tree.overrides[0].status == "unapplied"


# -- where overrides are registered ---------------------------------------------------


def test_a_sibling_built_earlier_affects_a_later_siblings_subtree():
    tree = stitch(T("p::test"), T("p::cfg"), T("p::agt"), T("p::drv"), T("p::drv2", base="p::drv"),
                  C("p::test", "b_agt", "p::agt", 0), C("p::test", "a_cfg", "p::cfg", 1),
                  C("p::agt", "drv", "p::drv", 0),
                  O("p::cfg", "p::drv", "p::drv2", 0))
    assert types(tree)["uvm_test_top.b_agt.drv"] == "p::drv2"


def test_an_override_in_a_constructor_applies_when_the_child_is_created():
    tree = stitch(T("p::test"), T("p::env", methods={"new": {}, "build_phase": {}}), T("p::agt"), T("p::agt2"),
                  C("p::test", "env", "p::env", 0), C("p::env", "agt", "p::agt", 0),
                  O("p::env", "p::agt", "p::agt2", 0, method="new"))
    assert types(tree)["uvm_test_top.env.agt"] == "p::agt2"
    assert tree.overrides[0].registered_by == ["uvm_test_top.env"]


def test_global_overrides_apply_first():
    tree = stitch(*BASE, O("tb_top", "p::drv", "p::drv2", method=""))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv2"


def test_a_global_override_of_the_test_type_applies():
    tree = stitch(*BASE, T("p::test2", base="p::test"), O("tb_top", "p::test", "p::test2", method=""))
    assert tree.root.type == "p::test2"


def test_an_override_in_an_unreached_method_is_unplaced():
    tree = stitch(*BASE, O("p::test", "p::drv", "p::drv2", 0, method="run_phase"))
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv"
    assert tree.overrides[0].status == "unplaced"
    assert "unplaced_override" in {i.code for i in tree.issues}


def test_another_tests_override_is_unplaced_quietly():
    tree = stitch(*BASE, T("p::other"), O("p::other", "p::drv", "p::drv2", 0))
    assert tree.overrides[0].status == "unplaced"
    assert "unplaced_override" not in {i.code for i in tree.issues}


def test_an_override_through_a_helper_object_is_reported():
    """A non-component class's override (``cfg.apply()``) runs who knows when."""
    tree = stitch(*BASE, O("p::cfg_obj", "p::drv", "p::drv2", 0, method="apply"))
    assert tree.overrides[0].status == "unplaced"
    assert "unplaced_override" in {i.code for i in tree.issues}


def test_an_override_naming_no_class_is_unknown_type():
    tree = stitch(*BASE, O("p::test", "p::drv", "drv_typo", 0, unknown=["drv_typo"]))
    assert tree.overrides[0].status == "unknown_type"


# -- helpers and inheritance (the run rule) ------------------------------------------


def test_an_override_in_a_helper_called_before_the_create():
    tree = stitch(T("p::test", methods={"build_phase": {"calls": [{"step": 0, "method": "ovr"}]}, "ovr": {}}),
                  *BASE[1:], O("p::test", "p::env", "p::env2", 0, method="ovr"))
    assert types(tree)["uvm_test_top.env"] == "p::env2"


def test_a_virtual_helper_dispatches_from_the_actual_type():
    test = T("p::test", methods={"build_phase": {"virtual": True, "calls": [{"step": 0, "method": "ovr"}]},
                                 "ovr": {"virtual": True}})
    test2 = T("p::test2", base="p::test", methods={"ovr": {"virtual": True}})
    tree = stitch(test, test2, *BASE[1:], O("p::test", "p::drv", "p::drv2", 0, method="ovr"),
                  O("p::test2", "p::drv", "p::drv3", 0, method="ovr"), root="p::test2")
    assert types(tree)["uvm_test_top.env.agt.drv"] == "p::drv3"


def test_an_inherited_build_phase_builds_the_base_children():
    tree = stitch(*BASE, T("p::env3", base="p::env", methods={}), O("tb", "p::env", "p::env3", method=""))
    assert types(tree)["uvm_test_top.env"] == "p::env3"
    assert types(tree)["uvm_test_top.env.agt"] == "p::agt"


def test_helper_recursion_is_an_issue():
    t = T("p::test", methods={"build_phase": {"calls": [{"step": 0, "method": "a"}]},
                              "a": {"calls": [{"step": 0, "method": "b"}]},
                              "b": {"calls": [{"step": 0, "method": "a"}]}})
    tree = stitch(t)
    assert "inline_cycle" in {i.code for i in tree.issues}


def test_a_create_in_an_unreached_helper_is_reported():
    tree = stitch(*BASE, C("p::env", "spare", "p::agt", 0, method="never_called"))
    assert "uvm_test_top.env.spare" not in types(tree)
    assert "unplaced_create" in {i.code for i in tree.issues}


# -- conditions, loops, states, limits -----------------------------------------------


def test_a_conditional_child():
    recs = [*BASE[:-1], C("p::agt", "drv", "p::drv", 0, conditional=True)]
    assert stitch(*recs).node("uvm_test_top.env.agt.drv").conditional
    assert "uvm_test_top.env.agt.drv" not in types(stitch(*recs, include_conditional=False))


def test_a_loop_child_is_one_representative_node():
    tree = stitch(*BASE[:-1], C("p::agt", "drvs", "p::drv", 0, multiplicity="N", inst_name=None))
    node = tree.node("uvm_test_top.env.agt.drvs[*]")
    assert node.multiplicity == "N"


def test_a_missing_type_is_an_unresolved_leaf():
    tree = stitch(T("p::test"), C("p::test", "x", "q::elsewhere", 0))
    assert tree.node("uvm_test_top.x").state == "unresolved"
    assert "unknown_type" in {i.code for i in tree.issues}


def test_an_opaque_child_is_a_leaf():
    tree = stitch(T("p::test"), C("p::test", "fifo", "uvm::uvm_tlm_fifo", 0, state="opaque"))
    assert tree.node("uvm_test_top.fifo").state == "opaque"
    assert not {i.code for i in tree.issues} & {"unknown_type"}


def test_an_abstract_instance_is_an_issue():
    tree = stitch(T("p::test"), T("p::abs", abstract=True), C("p::test", "a", "p::abs", 0))
    assert "abstract_instance" in {i.code for i in tree.issues}


def test_max_nodes_truncates():
    tree = stitch(*BASE, max_nodes=2)
    assert tree.truncated and len(tree.nodes) == 2


# -- links -----------------------------------------------------------------------------


LINKED = [
    T("p::test"), T("p::env", methods={"build_phase": {}, "connect_phase": {}}),
    T("p::agt"), T("p::mon", ports=[{"name": "ap", "role": "port", "link": "analysis"}]),
    T("p::scb", ports=[{"name": "exp", "role": "imp", "link": "analysis"}]),
    C("p::test", "env", "p::env", 0), C("p::env", "agt", "p::agt", 0), C("p::env", "scb", "p::scb", 1),
    C("p::agt", "mon", "p::mon", 0),
]


def test_a_link_resolves_through_handles():
    tree = stitch(*LINKED, W("p::env", (("agt", "mon"), "ap"), (("scb",), "exp"), 0))
    (k,) = tree.links
    assert (k.source.path, k.source.port) == ("uvm_test_top.env.agt.mon", "ap")
    assert (k.target.path, k.target.port) == ("uvm_test_top.env.scb", "exp")
    assert k.owner == "uvm_test_top.env" and k.state == "ok"


def test_a_link_to_a_handle_never_created_is_unresolved():
    tree = stitch(*LINKED, W("p::env", (("ghost", "mon"), "ap"), (("scb",), "exp"), 0))
    assert tree.links[0].state == "unresolved"
    assert tree.links[0].text == "ghost.mon.ap -> scb.exp"


def test_a_link_to_a_missing_port_is_an_issue():
    tree = stitch(*LINKED, W("p::env", (("agt", "mon"), "nope"), (("scb",), "exp"), 0))
    assert "unknown_port" in {i.code for i in tree.issues}


def test_an_inherited_connect_phase_links_on_the_derived_instance():
    env2 = T("p::env2", base="p::env", methods={})
    tree = stitch(*LINKED, env2, W("p::env", (("agt", "mon"), "ap"), (("scb",), "exp"), 0),
                  O("tb", "p::env", "p::env2", method=""))
    assert types(tree)["uvm_test_top.env"] == "p::env2"
    assert len(tree.links) == 1 and tree.links[0].state == "ok"


# -- several databases ------------------------------------------------------------------


def _file(tmp_path, name, *recs):
    path = tmp_path / name
    importer.import_stream([json.dumps(HEADER)] + [json.dumps(r) for r in recs], str(path)).conn.close()
    return str(path)


def test_classes_in_another_database_are_stitched(tmp_path):
    vip = _file(tmp_path, "vip.svdb", T("v::agt"), T("v::drv"), C("v::agt", "drv", "v::drv", 0))
    tb = _file(tmp_path, "tb.svdb", T("p::test"), T("p::drv2", base="v::drv"),
               C("p::test", "agt", "v::agt", 1), O("p::test", "v::drv", "p::drv2", 0), ROOT("p::test"))
    with Database.open([tb, vip]) as db:
        tree = db.uvm_tree()
    assert types(tree)["uvm_test_top.agt.drv"] == "p::drv2"


def test_identical_duplicates_fold_silently(tmp_path):
    a = _file(tmp_path, "a.svdb", *BASE)
    b = _file(tmp_path, "b.svdb", *BASE)
    with Database.open([a, b]) as db:
        tree = db.uvm_tree("p::test")
    assert "ambiguous_type" not in {i.code for i in tree.issues}
    assert len(tree.nodes) == 4


def test_differing_duplicates_are_ambiguous_and_the_first_wins(tmp_path):
    a = _file(tmp_path, "a.svdb", *BASE)
    b = _file(tmp_path, "b.svdb", *BASE[:-1], C("p::agt", "other", "p::drv", 0))
    with Database.open([a, b]) as db:
        tree = db.uvm_tree("p::test")
    assert "ambiguous_type" in {i.code for i in tree.issues}
    assert "uvm_test_top.env.agt.drv" in types(tree)


# -- output --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tree_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = svdb.uvm_tree_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


SAMPLE = [*LINKED, W("p::env", (("agt", "mon"), "ap"), (("scb",), "exp"), 0),
          W("p::env", (("ghost",), "ap"), (("scb",), "exp"), 1), T("p::mon2", base="p::mon"),
          O("p::test", "p::mon", "p::mon2", 0), O("p::test", "p::x", "p::y", 0, method="run_phase")]


@pytest.mark.parametrize("nested", [False, True])
def test_json_validates(tree_validator, nested):
    data = stitch(*SAMPLE).to_json(nested=nested)
    errors = list(tree_validator.iter_errors(data))
    assert not errors, [f"{e.json_path}: {e.message}" for e in errors]


def test_flat_json_links_parents():
    data = stitch(*SAMPLE).to_json()
    assert data["format"] == "svdb-uvm-tree" and data["version"] == 1
    mon = next(n for n in data["nodes"] if n["path"].endswith(".mon"))
    assert mon["parent"] == "uvm_test_top.env.agt"
    assert (mon["declared"], mon["type"]) == ("p::mon", "p::mon2")


def test_nested_json_nests():
    data = stitch(*SAMPLE).to_json(nested=True)
    (root,) = data["nodes"]
    assert [c["name"] for c in root["children"]] == ["env"]


def test_text_and_dot_render():
    tree = stitch(*SAMPLE)
    text = render_text(tree)
    assert "mon : mon2 <- mon" in text and "env.agt.mon.ap -> env.scb.exp  (analysis)" in text
    dot = render_dot(tree)
    assert dot.startswith("digraph uvm {") and '"uvm_test_top.env.agt.mon" -> "uvm_test_top.env.scb"' in dot


def test_a_bare_override_owner_is_resolved_to_its_class():
    """``Ref.target`` is optional: an override whose owner is named bare still
    registers when its class's build_phase runs."""
    from sphinx_systemverilog.svdb.uvm_tree import stitch_records

    def ref(name):
        return {"name": name.rsplit("::", 1)[-1], "target": name}

    recs = [
        {"r": "uvm.root", "root": ref("p::t")},
        {"r": "uvm.type", "type": ref("p::t"), "tier": "test",
         "methods": {"build_phase": {"virtual": True, "calls": []}}},
        {"r": "uvm.type", "type": ref("p::a"), "tier": "component"},
        {"r": "uvm.type", "type": ref("p::b"), "tier": "component", "base": ref("p::a")},
        {"r": "uvm.override", "original": ref("p::a"), "replacement": ref("p::b"), "kind": "type",
         "owner": {"name": "t"}, "method": "build_phase", "step": 0},
        {"r": "uvm.child", "owner": ref("p::t"), "handle": "x", "type": ref("p::a"),
         "inst_name": "x", "method": "build_phase", "step": 1},
    ]
    tree = stitch_records(recs)
    assert tree.node("uvm_test_top.x").type == "p::b"
    assert tree.overrides[0].owner == "p::t" and tree.overrides[0].status == "applied"
