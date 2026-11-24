"""U4-TEST-3: ``sv:uvm-sequence`` emits the activity DOT it promises.

Assertions are on DOT source for the same reason the schematic's are: the
notation *is* in the text. A diamond either is a ``shape=diamond`` node or it
is not, and an image comparison would be brittle across Graphviz releases while
telling us nothing about why a layout changed.

The contrast with the schematic is the interesting part, and it is asserted
here rather than only described. There, every edge carries ``constraint=false``
because a TLM connection is not an ordering. Here the edges *are* the ordering,
so they must **not** carry it --- with one exception, the loop back-edge, which
is a genuine cycle.
"""

from __future__ import annotations

import re

import pytest

from sphinx_systemverilog.autodoc.uvm_activity import build_activity_dot, wrap
from tests.conftest import UVM_STUB, UVM_TB, uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def provider():
    return uvm_stub_index("seq_tb.sv").uvm_provider


@pytest.fixture
def main(provider):
    sequence = provider.sequence("main_seq")
    subs = {name: provider.sequence(name) for name in sequence.subsequences()}
    return build_activity_dot(sequence, subs)


@pytest.fixture
def dot(main):
    return main[0]


def _edges(dot: str) -> list[str]:
    return [line.strip() for line in dot.splitlines() if "->" in line]


# -- the notation -------------------------------------------------------------


def test_a_conditional_is_a_diamond(dot):
    assert re.search(r'shape=diamond[^\n]*label="do_cfg"', dot)


def test_both_outcomes_of_a_bare_if_are_drawn(dot):
    """The fixture's ``if`` has no ``else``. Drawing only the arm that was
    written would say the branch always runs."""
    labels = [
        match for line in _edges(dot)
        for match in re.findall(r'label="(yes|no)"', line)
    ]
    assert sorted(labels) == ["no", "yes"]


def test_a_fork_is_a_pair_of_bars(dot):
    bars = [line for line in dot.splitlines() if "height=0.06" in line]
    assert len(bars) == 2


def test_the_join_bar_carries_the_join_semantics(dot):
    """Read from ``StatementBlockKind``, not guessed from the fixture's name."""
    assert 'xlabel="join_any"' in dot


def test_join_none_gets_no_join_bar(provider):
    """The branches genuinely do not rejoin; a bar would assert a
    synchronisation the source refuses."""
    code, _ = build_activity_dot(provider.sequence("join_seq"))
    assert 'xlabel="join"' in code
    assert 'xlabel="join_none"' not in code


def test_fork_branches_are_labelled_from_the_source(dot):
    assert 'label="traffic"' in dot
    assert 'label="timeout"' in dot


def test_a_loop_is_a_labelled_cluster(dot):
    assert 'label="repeat (n_bursts)"' in dot
    assert "subgraph cluster_" in dot


def test_a_delay_is_its_own_node(dot):
    assert 'label="#100ns"' in dot


def test_a_sub_sequence_node_names_its_type(dot):
    assert 'label="cfg: cfg_seq"' in dot


def test_the_diagram_has_a_start_and_an_end(dot):
    assert "shape=circle" in dot
    assert "shape=doublecircle" in dot


# -- ordering, which is the opposite of the schematic's rule -------------------


def test_ordinary_edges_are_ranking_constraints(dot):
    """The whole point of the difference from ``uvm_diagram``: here an edge
    means "after", and a rank is exactly that."""
    ordinary = [
        line for line in _edges(dot)
        if "constraint=false" not in line and "style=invis" not in line
    ]
    assert ordinary
    assert not any("constraint=false" in line for line in ordinary)


def test_only_a_loop_back_edge_escapes_ranking(provider):
    """A back-edge is a real cycle and would pull the end of the body above its
    start; it is the single case where the §7.3 knob still applies."""
    code, _ = build_activity_dot(provider.sequence("noisy_seq"))
    assert "constraint=false" not in code, "no loop, so no exception"

    looped = [
        line for line in _edges(build_activity_dot(provider.sequence("join_seq"))[0])
        if "constraint=false" in line
    ]
    assert len(looped) == 1


# -- depth --------------------------------------------------------------------


def test_a_sub_sequence_is_one_box_by_default(main):
    code, diagram = main
    assert diagram.unexpanded == ["cfg_seq", "traf_seq"]
    assert diagram.expanded == []
    assert 'label="it: seq_item"' not in code


def test_depth_two_opens_the_sub_sequences(provider):
    sequence = provider.sequence("main_seq")
    subs = {name: provider.sequence(name) for name in sequence.subsequences()}
    code, diagram = build_activity_dot(sequence, subs, depth=2)

    assert diagram.expanded == ["cfg_seq", "traf_seq"]
    assert diagram.unexpanded == []
    assert 'label="cfg: cfg_seq"' in code       # now a cluster label
    assert "it: seq_item" in code               # the sub-sequence's own step


def test_depth_counts_sub_sequences_and_not_statement_nesting(provider):
    """``cfg`` is started inside an ``if`` and ``traf`` inside a fork *and* a
    loop. Both are one level down, and counting braces instead would make
    ``:depth:`` mean something no reader could predict."""
    sequence = provider.sequence("main_seq")
    subs = {name: provider.sequence(name) for name in sequence.subsequences()}
    _, diagram = build_activity_dot(sequence, subs, depth=2)

    assert diagram.expanded == ["cfg_seq", "traf_seq"]


def test_a_sub_sequence_that_cannot_be_resolved_is_reported(provider):
    sequence = provider.sequence("main_seq")
    _, diagram = build_activity_dot(sequence, {}, depth=2)

    assert diagram.unresolved == ["cfg_seq", "traf_seq"]


def test_a_macro_step_says_which_macro_it_came_from(provider):
    """A reader looking for ``start_item`` in the source will find `` `mini_do ``
    instead, so the node says so."""
    code, _ = build_activity_dot(provider.sequence("noisy_seq"))
    assert code.count("`mini_do") == 2


# -- labels -------------------------------------------------------------------


def test_long_labels_wrap_rather_than_stretch_a_rank():
    assert wrap("a b c d", width=3) == "a b\nc d"
    assert wrap("short") == "short"


def test_a_newline_in_a_label_survives_escaping(provider):
    r"""It has to become DOT's ``\n``, and the escaping has to happen in the
    right order: doubling backslashes *after* inserting the newline escape puts
    a literal ``\n`` in the picture, which is what the first version did."""
    code, _ = build_activity_dot(provider.sequence("noisy_seq"))
    assert r"\n`mini_do" in code
    assert r"\\n" not in code


# -- through Sphinx -----------------------------------------------------------


CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "seq_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-sequence", srcdir="uvm-sequence", confoverrides=CONF
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

    assert len(codes) == 2, "silent_seq draws nothing, and says so instead"
    for code in codes:
        assert code.startswith("digraph uvm_activity {")


@pytest.mark.sphinx
@sphinx_config
def test_the_depth_option_reaches_the_dot(doctree):
    default, expanded = _graphviz_code(doctree)

    assert "it: seq_item" not in default
    assert "it: seq_item" in expanded


@pytest.mark.sphinx
@sphinx_config
def test_the_page_reports_what_is_not_drawn(app):
    app.build()
    page = (app.outdir / "index.html").read_text()

    assert "not a simulation trace" in page
    assert "3 statement(s) in body() are not drawn" in page
    assert "2 sub-sequence(s) are drawn as a single step" in page


@pytest.mark.sphinx
@sphinx_config
def test_a_sequence_without_a_body_says_so_rather_than_drawing_nothing(app):
    """An empty diagram would read as "this sequence does nothing", which is a
    claim about the testbench rather than about the source."""
    app.build()
    page = (app.outdir / "index.html").read_text()

    assert "silent_seq does not define a body()" in page
    assert "uvm_sequence_base" in page


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-sequence-missing", srcdir="uvm-sequence-missing",
    confoverrides=CONF,
)
def test_a_non_sequence_warns(app, warning):
    """Asking for the activity of a component is a reasonable mistake; it is
    also not something that can be answered, so it is said rather than drawn."""
    app.build()
    text = warning.getvalue()

    assert "cannot find a UVM sequence named 'seq_env'" in text


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-sequence-quiet", srcdir="uvm-sequence-quiet",
    confoverrides=CONF,
)
def test_optional_silences_the_missing_case(app, warning):
    """Distinct ``srcdir`` from the test above on purpose: a shared one caches
    the doctree, the directive never re-runs, and the assertion passes on an
    empty warning stream having tested nothing."""
    app.build()

    assert "cannot find a UVM sequence" not in warning.getvalue()


# -- sv:uvm-activity: component task phases ---------------------------------------


def test_waits_and_objections_have_their_own_shapes(provider):
    dot, _ = build_activity_dot(provider.activity("seq_test"))
    assert re.search(r'shape=cds[^\n]*label="raise objection"', dot)
    assert re.search(r'dashed[^\n]*label="@\(settled\)"', dot)
    assert "main_seq" in dot


activity_config = pytest.mark.sphinx(
    "html", testroot="uvm-activity", srcdir="uvm-activity", confoverrides=CONF
)


@pytest.mark.sphinx
@activity_config
def test_the_activity_directive_draws_a_run_phase(app):
    app.build()
    codes = _graphviz_code(app.env.get_doctree("index"))
    assert len(codes) == 2, "seq_test's run_phase and main_seq's body; the rest say why not"
    assert "raise objection" in codes[0]
    assert "do_cfg" in codes[1]

    page = (app.outdir / "index.html").read_text()
    assert "Control flow as written in run_phase()" in page
    # The database knows seq_env is a component, not which library class its
    # empty run_phase comes from; that half of the sentence is live-only.
    assert "seq_env does not define run_phase()" in page
    assert "seq_test does not define main_phase()." in page


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-activity-missing", srcdir="uvm-activity-missing",
    confoverrides=CONF,
)
def test_a_function_phase_warns(app, warning):
    app.build()
    text = warning.getvalue()
    assert "cannot find build_phase() on a UVM class named 'seq_test'" in text


# -- sv:uvm-sequence-catalog ------------------------------------------------------

catalog_config = pytest.mark.sphinx(
    "html", testroot="uvm-catalog", srcdir="uvm-catalog", confoverrides=CONF
)


def _catalog_tables(doctree):
    from docutils import nodes

    return [t for t in doctree.findall(nodes.table) if "sv-uvm-catalog" in t["classes"]]


@pytest.mark.sphinx
@catalog_config
def test_the_catalog_lists_every_sequence_once(app):
    app.build()
    tables = _catalog_tables(app.env.get_doctree("index"))
    assert len(tables) == 3, "seq_test, rec_seq, and the :catalog: under the diagram"
    first = tables[0].astext()
    for name in ("main_seq", "cfg_seq", "traf_seq", "env.seqr", "m_sequencer", "seq_item"):
        assert name in first

    page = (app.outdir / "index.html").read_text()
    assert "run_phase() depends on 3 sequence(s): 1 started directly " \
           "and 2 through other sequences." in page


@pytest.mark.sphinx
@catalog_config
def test_the_catalog_marks_recursion_and_declared_types(app):
    app.build()
    second = _catalog_tables(app.env.get_doctree("index"))[1].astext()
    assert "(recursive)" in second
    assert "declared type only" in second
    page = (app.outdir / "index.html").read_text()
    assert "starts no sub-sequences" in page
    assert "drives transactions itself" in page
    assert "seq_env does not define run_phase(), so it depends on no sequences." in page


# -- phase 3: member handles, factory overrides, sequence users --------------------

deps_config = pytest.mark.sphinx(
    "html", testroot="uvm-sequence-deps", srcdir="uvm-sequence-deps",
    confoverrides={**CONF, "sv_build_units": [str(UVM_STUB / "mini_uvm.sv"),
                                              str(UVM_TB / "seq_dep_tb.sv")]},
)


def _text(app) -> str:
    import re

    page = (app.outdir / "index.html").read_text()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", page)).replace("&gt;", ">")


@pytest.mark.sphinx
@deps_config
def test_the_catalog_resolves_members_and_applies_overrides(app):
    app.build()
    assert app._warning.getvalue().strip() == ""
    tables = _catalog_tables(app.env.get_doctree("index"))
    first = tables[0].astext()
    assert "created in build_phase()" in first
    assert "created, overridden from base_seq" in first
    # fast_seq is what runs, so what it starts is a dependency.
    assert "burst_seq" in first
    text = _text(app)
    assert "base_seq → fast_seq (in dep_test.build_phase)" in text
    assert "cool_seq → cold_seq (conditional, in dep_test.build_phase)" in text
    assert "warm_seq → cool_seq (in other_test.build_phase)" in text
    # The subclass registers the warm_seq override itself: applied there.
    second = tables[1].astext()
    assert "created in build_phase(), overridden from warm_seq" in second


@pytest.mark.sphinx
@deps_config
def test_the_users_table_lists_every_task_that_depends(app):
    app.build()
    from docutils import nodes

    doctree = app.env.get_doctree("index")
    users = [t for t in doctree.findall(nodes.table) if "sv-uvm-sequence-users" in t["classes"]]
    assert len(users) == 2, "burst_seq, and the :used-by: under fast_seq"
    assert "fast_seq.body()" in users[0].astext()
    text = _text(app)
    assert "burst_seq is started in 1 place(s). 2 component task(s) and 1 sequence(s) depend on it." in text
    assert "dep_test.run_phase() (through 1 other sequence level(s))" in text
    assert "Nothing in this design starts cold_seq" in text
    assert "cold_seq can also run in place of another sequence, through a factory " \
           "override: cool_seq → cold_seq (conditional, in dep_test.build_phase)." in text
    assert "fast_seq is started in 2 place(s)." in text


calls_config = pytest.mark.sphinx(
    "html", testroot="uvm-sequence-calls", srcdir="uvm-sequence-calls",
    confoverrides={**CONF, "sv_build_units": [str(UVM_STUB / "mini_uvm.sv"),
                                              str(UVM_TB / "seq_call_tb.sv")]},
)


@pytest.mark.sphinx
@calls_config
def test_helper_tasks_are_drawn_in_place_and_catalogued(app):
    app.build()
    assert app._warning.getvalue().strip() == ""
    doctree = app.env.get_doctree("index")
    test_dot, seq_dot = _graphviz_code(doctree)
    assert 'label="super.run_phase()"' in test_dot
    assert 'label="traffic()"' in test_dot
    assert 'label="do_steps()"' in seq_dot
    first = _catalog_tables(doctree)[0].astext()
    assert "super.run_phase() → traffic()" in first
    text = _text(app)
    assert "Tasks of the class that it calls (super.run_phase(), traffic(), drain())" in text
    assert "Drawn as a single box" in text and ": drain()." in text


@pytest.mark.sphinx
@calls_config
def test_the_tree_directive_renders_nested_starts(app):
    app.build()
    from docutils import nodes

    doctree = app.env.get_doctree("index")
    lists = [b for b in doctree.findall(nodes.bullet_list) if "sv-uvm-sequence-tree" in b["classes"]]
    outer = lists[0]
    assert len(outer.children) == 2, "call_seq and tail_seq"
    text = _text(app)
    assert "call_test.run_phase() starts sequences in 4 place(s)" in text
    assert "in repeat (2); through do_steps()" in text
    assert "(shown above)" in text


@pytest.mark.sphinx
@deps_config
def test_the_tree_option_names_the_override(app):
    app.build()
    assert app._warning.getvalue().strip() == ""
    text = _text(app)
    assert "created, overridden from base_seq" in text
    assert "dep_test.run_phase() starts sequences in 5 place(s)" in text


@pytest.mark.sphinx
@calls_config
def test_the_tree_names_sequencer_instances(app):
    app.build()
    text = _text(app)
    assert "on env.vseqr = uvm_test_top.env.vseqr (call_vsequencer)" in text
    assert "on p_sequencer.agt_sqr = uvm_test_top.env.agt.sqr (call_sequencer)" in text
    assert "Sequencer instances are found in the component tree built from vseq_test" in text
