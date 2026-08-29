"""U5-TEST-3: ``sv:uvm-binding`` renders the bridge, and both ends link.

The table is the deliverable, but the *cross-references* are what make it the
thing `U5-ACC` asks for: a reader lands on a component, follows the interface
to an RTL instance, and follows that to the module's own page. A table of
strings would show the same facts and be a dead end.

The three failure shapes each get a rendering test rather than only a model
test, because a finding the model produces and the page does not print is a
finding nobody sees.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from sphinx import addnodes

from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "bridge_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-binding", srcdir="uvm-binding", confoverrides=CONF
)


@pytest.fixture
def doctree(app):
    app.build()
    return app.env.get_doctree("index")


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


def _tables(doctree) -> list[nodes.table]:
    return list(doctree.findall(nodes.table))


def _rows(table) -> list[list[str]]:
    body = next(iter(table.findall(nodes.tbody)))
    return [
        [entry.astext() for entry in row.findall(nodes.entry)]
        for row in body.findall(nodes.row)
    ]


def _row_for(table, field: str) -> list[str]:
    """The row whose Field cell *is* *field*, ignoring any appended marker."""
    return next(row for row in _rows(table) if row[2].split()[0] == field)


# -- the table ----------------------------------------------------------------


@pytest.mark.sphinx
@sphinx_config
def test_the_directive_emits_a_table_of_every_binding(doctree):
    rows = _rows(_tables(doctree)[0])
    assert len(rows) == 4


@pytest.mark.sphinx
@sphinx_config
def test_a_row_carries_the_whole_path(doctree):
    """The acceptance criterion, read off one row: which component reads it,
    which interface instance it is, and which RTL that instance reaches."""
    row = _row_for(_tables(doctree)[0], "vif")

    assert row[0] == "bridge_tb_top"
    assert row[3] == "bridge_if"
    assert row[4] == "bridge_tb_top.u_bus"
    assert "bridge_tb_top.u_dut : bridge_dut" in row[5]
    assert "bridge_agent.build_phase" in row[6]


@pytest.mark.sphinx
@sphinx_config
def test_both_ends_of_the_bridge_are_cross_references(doctree):
    """`U5-IMPL-3`: the RTL end is a live link to the module's own page, not a
    string that happens to match one."""
    targets = {
        node["reftarget"]
        for node in _tables(doctree)[0].findall(addnodes.pending_xref)
    }
    assert {"bridge_if", "bridge_dut", "bridge_probe"} <= targets


@pytest.mark.sphinx
@sphinx_config
def test_the_argument_globs_the_interface_type(doctree):
    rows = _rows(_tables(doctree)[1])
    assert [row[3] for row in rows] == ["bridge_clk_if"]


# -- the three failures -------------------------------------------------------


@pytest.mark.sphinx
@sphinx_config
def test_a_binding_nothing_reads_is_marked_in_its_row(doctree):
    row = _row_for(_tables(doctree)[0], "clk_vif")
    assert "← unread" in row[2]
    assert "(none)" in row[6]


@pytest.mark.sphinx
@sphinx_config
def test_an_interface_that_reaches_no_rtl_says_nothing_rather_than_nothing_at_all(
    doctree,
):
    """An empty cell reads as "not analysed"; the finding is that the analysis
    ran and the answer is none."""
    row = _row_for(_tables(doctree)[0], "spare_vif")
    assert row[4] == "bridge_tb_top.u_spare"
    assert row[5] == "(nothing)"


@pytest.mark.sphinx
@sphinx_config
def test_a_handle_is_shown_as_a_handle(doctree):
    row = _row_for(_tables(doctree)[0], "vif_alias")
    assert row[4] == "(handle: vif)"
    assert row[5] == "(unknown)"


@pytest.mark.sphinx
@sphinx_config
def test_the_page_reports_each_failure_under_the_table(page):
    assert "3 binding(s) are read by no component" in page
    assert "1 interface instance(s) are handed to the testbench but connect" in page
    assert "1 binding(s) pass a virtual-interface handle" in page


@pytest.mark.sphinx
@sphinx_config
def test_the_page_states_the_scope_of_the_rtl_side(page):
    """The join looks in the interface's own declaring scope only, and a
    reader has no way to know that from the table itself."""
    assert "declared in the same scope as the interface" in page


# -- resolution ---------------------------------------------------------------


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-binding-missing", srcdir="uvm-binding-missing",
    confoverrides=CONF,
)
def test_a_glob_matching_nothing_warns(app, warning):
    app.build()
    assert "found no virtual-interface bindings matching 'no_such_if'" in \
        warning.getvalue()


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="uvm-binding-quiet", srcdir="uvm-binding-quiet",
    confoverrides=CONF,
)
def test_optional_silences_the_missing_case(app, warning):
    """Distinct ``srcdir`` from the test above on purpose: sharing one caches
    the doctree, the directive never re-runs, and the assertion passes on an
    empty warning stream having tested nothing."""
    app.build()
    assert "found no virtual-interface bindings" not in warning.getvalue()
