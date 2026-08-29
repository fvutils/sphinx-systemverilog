"""U3-TEST-3/4/5: ``sv:uvm-schematic`` emits the DOT the layout depends on.

Every assertion here is on **DOT source**, never on rendered pixels. That is a
deliberate choice, not a convenience: an image comparison is brittle across
Graphviz releases and would tell us nothing about *why* a layout changed, while
the four techniques the schematic depends on are all literally present in the
DOT. ``constraint=false`` either is on that edge or it is not.

The failure being guarded against is specific and documented (§7.1): with TLM
edges left as ranking constraints, an analysis connection from a monitor drags
the scoreboard *below* the agents, and the diagram stops resembling a testbench.
"""

from __future__ import annotations

import re

import pytest

from sphinx_systemverilog.autodoc.uvm_diagram import (
    build_schematic,
    build_schematic_dot,
)
from tests.conftest import UVM_STUB, UVM_TB, uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def structure():
    return uvm_stub_index("tlm_tb.sv").uvm_provider.get()


@pytest.fixture
def schematic(structure):
    return build_schematic(structure, "tlm_env")


@pytest.fixture
def dot(schematic):
    return build_schematic_dot(schematic)


def _edges(dot: str) -> list[str]:
    return [line for line in dot.splitlines() if "->" in line]


def _tlm_edges(dot: str) -> list[str]:
    return [line for line in _edges(dot) if "style=invis" not in line]


# -- the four knobs -----------------------------------------------------------


def test_newrank_is_present(dot):
    """Knob 1, and it is not optional.

    Graphviz documents that under the default ranking a node cannot be both
    inside a cluster and constrained by ``rank=same`` with a node outside it.
    Agents are asked to be exactly that, so without ``newrank`` the layout is
    not merely worse --- it is inexpressible.
    """
    assert "newrank=true" in dot


def test_every_tlm_edge_is_unconstrained(dot):
    """Knob 2: the single attribute that separates this from the naive graph."""
    edges = _tlm_edges(dot)

    assert edges, "the fixture has connections; something is wrong upstream"
    for edge in edges:
        assert "constraint=false" in edge, edge


def test_the_tiers_are_pinned_with_rank_groups(dot):
    """Knob 3."""
    groups = [line for line in dot.splitlines() if "rank=same" in line]

    assert len(groups) == 3, "sequencer / analysis / agent tiers"


def test_one_invisible_edge_joins_each_pair_of_tiers(dot):
    """Knob 3's other half: rank groups alone do not order the tiers."""
    invisible = [
        line for line in _edges(dot)
        if "style=invis" in line and "weight" not in line
    ]

    assert len(invisible) == 2, "three tiers, two boundaries"


def test_cluster_members_are_ordered_by_an_invisible_chain(dot):
    """Knob 4: what removes the remaining crossings."""
    chains = [line for line in _edges(dot) if "weight=10" in line]

    assert len(chains) == 2, "one per agent"
    for chain in chains:
        assert "style=invis" in chain


# -- what gets drawn ----------------------------------------------------------


def test_one_cluster_per_agent(dot, schematic):
    assert len(schematic.clusters) == 2
    assert dot.count("subgraph cluster_") == 2
    assert "cluster_agt_a" in dot and "cluster_agt_b" in dot


def test_agents_are_on_the_bottom_tier(dot):
    """``U3-ACC``: the whole point of the layout work."""
    groups = [line for line in dot.splitlines() if "rank=same" in line]
    bottom = groups[-1]

    for handle in ("agt_a__mon", "agt_a__drv", "agt_b__mon", "agt_b__drv"):
        assert handle in bottom, bottom


def test_the_scoreboard_is_not_displaced_below_the_agents(dot):
    """The documented failure mode, asserted directly.

    §7.1's diagram failed because the analysis edge from monitor to scoreboard
    ranked the scoreboard beneath the monitor. Here the scoreboard shares a rank
    group with the coverage collector, above the agent tier.
    """
    groups = [line for line in dot.splitlines() if "rank=same" in line]
    middle = next(line for line in groups if "n_sb" in line)

    assert "n_cov" in middle
    assert groups.index(middle) < len(groups) - 1, "not the bottom tier"


def test_ports_are_drawn_as_addressable_anchors(dot):
    """A connection arrives at a *port*, and the DOT says which one."""
    assert 'PORT="ap"' in dot
    assert 'PORT="aimp"' in dot
    assert "n_agt_a__mon:ap -> n_sb:aimp" in dot


def test_a_component_with_no_ports_still_draws(dot):
    assert "n_vseqr" in dot


def test_an_unconnected_library_port_is_hidden_and_counted(dot, schematic):
    """``rsp_port`` comes from ``uvm_driver`` and nothing here connects to it.

    Drawing it would label plumbing the reader did not write. Hiding it without
    saying so would make the box claim to be a complete port list, so the count
    is kept and the directive reports it.
    """
    assert 'PORT="rsp_port"' not in dot
    assert schematic.hidden_ports == 2, "one per agent"


def test_a_connected_library_port_is_still_drawn(dot):
    """...which is what stops that rule from being a blanket exclusion.

    Both ends of a driver/sequencer connection are declared by UVM, not by the
    user. Hiding them for that reason would remove the most recognizable
    connection in a UVM testbench.
    """
    assert 'PORT="seq_item_port"' in dot
    assert 'PORT="seq_item_export"' in dot


def test_the_virtual_sequencer_edges_are_drawn(dot):
    """Assignment-wired, and so invisible to a connect-only walker."""
    assert "n_vseqr -> n_agt_a__seqr" in dot
    assert "n_vseqr -> n_agt_b__seqr" in dot


def test_an_agents_internal_connection_is_drawn_once_per_instance(dot):
    """The source describes the type; each instance really makes the connection."""
    for agent in ("agt_a", "agt_b"):
        assert f"n_{agent}__drv:seq_item_port -> n_{agent}__seqr:seq_item_export" in dot


def test_a_conditional_connection_is_drawn_dotted(dot):
    line = next(
        edge for edge in _tlm_edges(dot) if "seq_item_port" in edge
    )

    assert "style=dotted" in line


def test_edges_carry_no_labels(dot):
    """§7.5 named edge labels as the weak point, and there is nothing to say.

    Both ends of every edge already terminate at a named port anchor, so a
    label would repeat what the boxes show while adding the clutter that made
    the reference diagram unreadable.
    """
    for edge in _tlm_edges(dot):
        assert "label=" not in edge, edge


def test_the_dot_is_valid(dot):
    """Balanced braces and a single digraph --- a cheap structural floor."""
    assert dot.startswith("digraph tlm_env {")
    assert dot.count("{") == dot.count("}")


# -- endpoint placement -------------------------------------------------------


def test_a_handle_below_a_drawn_box_clamps_to_that_box(schematic):
    """``vseqr.seqr_a`` names a handle inside ``vseqr``, which has no children.

    The edge belongs on ``vseqr`` itself. Clamping to the deepest *drawn*
    ancestor is what makes a single-level view able to show a connection whose
    source reaches deeper than the view does.
    """
    sources = {edge[0] for edge in schematic.edges}

    assert (("vseqr",), "") in sources


def test_nothing_is_dropped_from_the_fixture(schematic):
    """If this ever fails, the note under the diagram is what a reader sees."""
    assert schematic.dropped == []


# -- overrides ----------------------------------------------------------------


def test_a_tier_override_moves_a_component(structure):
    """``U3-TEST-4``: the override changes the emitted rank groups."""
    default = build_schematic_dot(build_schematic(structure, "tlm_env"))
    moved = build_schematic_dot(
        build_schematic(structure, "tlm_env", tiers={"sb": "top"})
    )

    def top_group(dot):
        return next(line for line in dot.splitlines() if "rank=same" in line)

    assert "n_sb" not in top_group(default)
    assert "n_sb" in top_group(moved)


def test_a_tier_override_may_name_a_type(structure):
    """A page documenting a component class does not know the handle."""
    dot = build_schematic_dot(
        build_schematic(structure, "tlm_env", tiers={"tlm_scoreboard": "top"})
    )
    top = next(line for line in dot.splitlines() if "rank=same" in line)

    assert "n_sb" in top


def test_an_unknown_tier_override_name_changes_nothing(structure):
    """No crash, no invented box: an override for a component not in this view."""
    dot = build_schematic_dot(
        build_schematic(structure, "tlm_env", tiers={"nothing_here": "top"})
    )

    assert build_schematic_dot(build_schematic(structure, "tlm_env")) == dot


def test_order_reorders_within_a_tier_and_emits_a_chain(structure):
    """``:order:`` maps to knob 4 at the top level."""
    dot = build_schematic_dot(
        build_schematic(structure, "tlm_env", order=["cov", "sb"])
    )
    middle = next(
        line for line in dot.splitlines() if "rank=same" in line and "n_sb" in line
    )

    assert middle.index("n_cov") < middle.index("n_sb")
    assert "n_cov -> n_sb [style=invis, weight=10]" in dot


def test_order_leaves_unnamed_components_in_source_order(structure):
    """A partial ordering is the common request and must not be refused."""
    dot = build_schematic_dot(build_schematic(structure, "tlm_env", order=["cov"]))
    middle = next(
        line for line in dot.splitlines() if "rank=same" in line and "n_sb" in line
    )

    assert middle.index("n_cov") < middle.index("n_sb")


# -- degradation --------------------------------------------------------------


def test_without_newrank_the_pinning_is_dropped_and_the_dot_stays_valid(schematic):
    """``U3-TEST-5``: a worse layout, never broken source.

    ``rank=same`` across a cluster boundary is precisely what the pre-2.30
    ranking algorithm refuses, so the pinning has to go with ``newrank``.
    Everything that does not depend on it stays.
    """
    dot = build_schematic_dot(schematic, newrank=False)

    assert "newrank" not in dot
    assert "rank=same" not in dot
    assert dot.count("{") == dot.count("}")
    assert "subgraph cluster_agt_a" in dot, "clusters do not need newrank"
    for edge in _tlm_edges(dot):
        assert "constraint=false" in edge, edge


def test_the_graphviz_probe_answers_false_for_a_missing_binary():
    from sphinx_systemverilog.autodoc.uvm_diagram import supports_newrank

    assert supports_newrank("definitely-not-a-real-dot-binary") is False


def test_the_graphviz_probe_reads_a_version(tmp_path):
    """A too-old ``dot`` must answer False, and only a real probe proves it."""
    from sphinx_systemverilog.autodoc.uvm_diagram import supports_newrank

    fake = tmp_path / "dot"
    fake.write_text(
        "#!/bin/sh\necho 'dot - graphviz version 2.28.0 (20110507.0327)' >&2\n"
    )
    fake.chmod(0o755)

    assert supports_newrank(str(fake)) is False


# -- through Sphinx -----------------------------------------------------------


CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "tlm_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-schematic", srcdir="uvm-schematic", confoverrides=CONF
)


@pytest.fixture
def doctree(app):
    app.build()
    return app.env.get_doctree("index")


def _graphviz_code(doctree) -> list[str]:
    from sphinx.ext.graphviz import graphviz as graphviz_node

    return [node["code"] for node in doctree.findall(graphviz_node)]


@pytest.mark.sphinx
@sphinx_config
def test_the_directive_emits_graphviz_nodes(doctree):
    codes = _graphviz_code(doctree)

    assert len(codes) == 3
    for code in codes:
        assert "newrank=true" in code


@pytest.mark.sphinx
@sphinx_config
def test_the_root_is_auto_detected_down_to_the_env(doctree):
    """A test containing one env draws as a single box, which helps nobody.

    So the default descends while there is exactly one child and stops at the
    env, which is the level where wiring exists.
    """
    codes = _graphviz_code(doctree)

    assert codes[1].startswith("digraph tlm_env {")


@pytest.mark.sphinx
@sphinx_config
def test_the_directive_options_reach_the_dot(doctree):
    default, _auto, overridden = _graphviz_code(doctree)
    groups = [line for line in overridden.splitlines() if "rank=same" in line]

    def top_group(code):
        return next(line for line in code.splitlines() if "rank=same" in line)

    assert "n_sb" not in top_group(default), "not on the top tier by default"
    assert "n_sb" in top_group(overridden), ":tier: sb=top moved it"
    # Ordering acts *within* a tier, which is the only place it can: two boxes
    # on different ranks have no left-to-right relationship to state.
    assert re.search(r"n_sb;\s*n_vseqr;", groups[0]), ":order: sb before vseqr"
    assert overridden.index("cluster_agt_b") < overridden.index("cluster_agt_a"), (
        ":order: reaches clusters, which is what agents are drawn as"
    )


@pytest.mark.sphinx
@sphinx_config
def test_the_page_states_what_the_diagram_is_not(app):
    app.build()
    page = (app.outdir / "index.html").read_text()

    assert "not a simulation trace" in page
    assert "one level deep" in page


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-schematic-leaf", srcdir="uvm-schematic-leaf",
    confoverrides=CONF,
)
def test_a_leaf_component_warns_rather_than_drawing_an_empty_box(app, warning):
    """Asking for a schematic of a driver is a reasonable mistake to make.

    A driver builds nothing, so there is no wiring to draw. An empty diagram
    would read as "this driver is unconnected", which is a claim about the
    testbench rather than about the request.
    """
    app.build()
    text = warning.getvalue()

    assert "nothing to draw" in text
    assert "tlm_driver" in text


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-schematic-quiet", srcdir="uvm-schematic-quiet",
    confoverrides=CONF,
)
def test_optional_silences_the_empty_case(app, warning):
    """A page shared across projects must not fail a build it does not own.

    Distinct ``srcdir`` from the test above on purpose: a shared one caches the
    doctree, the directive never re-runs, and the assertion passes on an empty
    warning stream having tested nothing. That failure mode has bitten this
    suite twice.
    """
    app.build()

    assert "nothing to draw" not in warning.getvalue()
