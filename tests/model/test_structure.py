"""M1-TEST-2/3/6/7: what the hierarchy walk extracts.

The two regressions worth naming up front (design doc §3.1 and §3.2): before
this milestone the collector matched only ``SymbolKind.Instance`` at the top of
a module body, so a module whose children all sat inside a ``generate`` reported
*no children at all*, and an instance array reported none either.  Both cases
are ordinary in real RTL, and both failed silently --- the diagram rendered, it
was just wrong.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.index import build_index
from tests.conftest import DESIGN

pytestmark = pytest.mark.unit


@pytest.fixture
def structure():
    return build_index(source_dirs=[str(DESIGN)], use_cache=False).structure


def _by_type(instances, type_name):
    return [i for i in instances if i.type_name == type_name]


def test_tops_are_the_elaborated_roots(structure):
    # cluster/lane/leaf are all instantiated, so soc is the only real top.
    assert structure.tops == ["soc"]


def test_plain_instances(structure):
    soc = structure.children_of("soc")
    assert [(i.inst_name, i.type_name) for i in soc] == [
        ("u_narrow", "cluster"),
        ("u_wide", "cluster"),
    ]


def test_generate_blocks_are_not_dropped(structure):
    """Design §3.2: every child of ``cluster`` lives inside a generate."""
    cluster = structure.children_of("cluster")
    assert cluster, "a module whose children are all inside generate reported none"

    paths = {i.path for i in cluster}
    assert paths == {"g_narrow.u_leaf", "g_wide.u_lane"}


def test_untaken_generate_branch_is_excluded(structure):
    """An if-generate branch that did not elaborate is not part of the design.

    Both branches of ``cluster``'s if-generate appear here only because the two
    elaborations (WIDE=0 and WIDE=1) take different ones.  Neither elaboration
    contributes the branch it did not take.
    """
    narrow = [
        s for s in structure.sites_for("leaf") if s.parent_path == "soc.u_narrow"
    ]
    assert [s.elaborated_path for s in narrow] == ["g_narrow.u_leaf"]


def test_generate_loop_is_one_site_with_multiplicity(structure):
    """A for-generate is written once; it should be reported once."""
    lane = structure.children_of("lane")
    loop = [i for i in lane if i.generate_path == ("g_lp[*]",)]

    assert len(loop) == 1
    assert loop[0].inst_name == "u_g"
    assert loop[0].generate_count == 4
    assert loop[0].total_count == 4
    assert loop[0].path == "g_lp[*].u_g"


def test_instance_arrays_are_not_dropped(structure):
    """Design §3.1: ``leaf u_l [3:0] (...)`` is a site with four elements."""
    lane = structure.children_of("lane")
    arrays = [i for i in lane if i.array_range]

    assert len(arrays) == 1
    array = arrays[0]
    assert array.inst_name == "u_l"
    assert array.type_name == "leaf"
    assert array.array_range == "[3:0]"
    assert array.array_count == 4
    assert array.label == "u_l[3:0]"


def test_elaborated_parameter_values(structure):
    """Values are resolved, not echoed: ``#(.W(W))`` reports the actual width."""
    narrow, wide = structure.children_of("soc")

    assert [(p.name, p.value) for p in narrow.params] == [("W", "8"), ("WIDE", "1'b0")]
    assert [(p.name, p.value) for p in wide.params] == [("W", "32"), ("WIDE", "1'b1")]
    assert narrow.param_text == "#(W=8, WIDE=1'b0)"

    # The declared type is captured alongside the value; short values still
    # display as themselves.
    assert narrow.params[0].type_name == "int"
    assert narrow.params[0].display == "8"

    # The same definition, elaborated twice at different widths, stays distinct.
    leaves = structure.children_of("cluster") + structure.children_of("lane")
    widths = {tuple(p.value for p in i.params) for i in _by_type(leaves, "leaf")}
    assert ("8",) in widths
    assert ("32",) in widths


def test_instantiation_sites_carry_locations(structure):
    site = structure.children_of("soc")[0]
    assert site.location is not None
    assert site.location.file.endswith("soc.sv")
    assert site.location.line > 0


def test_used_by_is_the_inverse_map(structure):
    """M1-IMPL-7: derived by walking, because ``instanceCount`` reports 0."""
    paths = [s.hier_path for s in structure.sites_for("leaf")]

    assert "soc.u_narrow.g_narrow.u_leaf" in paths
    # Generate iterations are concrete here, unlike the collapsed source view.
    assert "soc.u_wide.g_wide.u_lane.g_lp[2].u_g" in paths
    # An array is walked once, so its path keeps the range: this single entry
    # stands for all four elements.
    assert "soc.u_wide.g_wide.u_lane.u_l[3:0]" in paths

    assert {s.parent_type for s in structure.sites_for("leaf")} == {"cluster", "lane"}
    assert [s.parent_type for s in structure.sites_for("cluster")] == ["soc", "soc"]


def test_module_never_instantiated_has_no_sites(structure):
    assert structure.sites_for("soc") == []


def test_param_usage_groups_values_by_site(structure):
    usage = structure.param_usage("cluster")

    assert set(usage) == {"W", "WIDE"}
    assert usage["W"] == {"8": ["soc.u_narrow"], "32": ["soc.u_wide"]}

    leaf_widths = structure.param_usage("leaf")["W"]
    assert set(leaf_widths) == {"8", "32"}
    assert leaf_widths["8"] == ["soc.u_narrow.g_narrow.u_leaf"]
    assert len(leaf_widths["32"]) == 5     # four loop iterations + the array


def test_elaborations_have_distinct_bodies(structure):
    """The type-union view and the per-elaboration view answer different questions.

    ``cluster`` takes different if-generate branches at ``WIDE=0`` and
    ``WIDE=1``.  ``edges`` unions them, which is right for a type graph; a tree
    that did the same would draw a design that does not exist.
    """
    variants = structure.elaborations_of("cluster")
    assert len(variants) == 2

    bodies = {
        params: [i.path for i in structure.children_of_elaboration("cluster", params)]
        for params in variants
    }
    assert list(bodies.values()) == [["g_narrow.u_leaf"], ["g_wide.u_lane"]]

    # The union across both is what ``children_of`` reports.
    assert len(structure.children_of("cluster")) == 2


def test_unknown_elaboration_falls_back_to_the_union(structure):
    """Asking about a parameterization that was never elaborated still answers."""
    fallback = structure.children_of_elaboration("cluster", (("W", "999"),))

    assert fallback == structure.children_of("cluster")


def test_legacy_edges_shape_is_preserved(structure):
    """The original ``{parent: [(name, type)]}`` contract still holds."""
    legacy = structure.legacy_edges()

    assert ("u_narrow", "cluster") in legacy["soc"]
    assert ("u_leaf", "leaf") in legacy["cluster"]
    assert ("u_l", "leaf") in legacy["lane"]
