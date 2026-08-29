"""U6-TEST-1 (`U6-IMPL-2`, `U6-IMPL-3`, `U6-IMPL-4`): the three smaller follow-ons.

All three answer questions a reader has *on a page that is not a testbench
view*: what is this class, what does it do and when, and who builds it. That is
why two of them are rendered by the documenter rather than by a UVM directive —
they have to work on a class page that names no testbench, and on an index that
has been pickled and reloaded with the live compilation gone.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from sphinx import addnodes

from sphinx_systemverilog.model.uvm import phase_inventory, uvm_role
from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "override_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-followons", srcdir="uvm-followons", confoverrides=CONF
)


@pytest.fixture
def doctree(app):
    app.build()
    return app.env.get_doctree("index")


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


# -- U6-IMPL-3: classification ------------------------------------------------


def test_a_sequence_is_not_reported_as_a_sequence_item():
    """The one place a naive reading goes wrong, and the reason the role table
    is ordered: every sequence *is* a ``uvm_sequence_item``."""
    chain = ["my_seq", "uvm_sequence", "uvm_sequence_base",
             "uvm_sequence_item", "uvm_object"]
    assert uvm_role(chain) == "sequence"
    assert uvm_role(["my_item", "uvm_sequence_item", "uvm_object"]) == "sequence item"


def test_a_class_that_is_not_uvm_gets_no_badge():
    """``""`` is a real answer. A plain SystemVerilog class in the same package
    must not be labelled."""
    assert uvm_role(["plain_helper"]) == ""


@pytest.mark.sphinx
@sphinx_config
def test_the_role_appears_on_the_class_signature(doctree):
    """Read off the doctree rather than the HTML: Sphinx wraps a multi-word
    annotation in per-word spans, so ``[sequence item]`` is never one string in
    the markup even though it is one on the page."""
    badges = {
        node.astext().strip() for node in doctree.findall(addnodes.desc_annotation)
        if node.astext().strip().startswith("[")
    }
    assert badges == {"[component]", "[sequence item]"}


@pytest.mark.sphinx
@sphinx_config
def test_the_role_is_derived_from_the_stored_extends_chain(doctree):
    """Derived from names in the index rather than from the live compilation,
    which is what lets a class page carry the badge with no UVM directive on it
    and after the index has been unpickled."""
    roles = [
        node.astext() for node in doctree.findall(addnodes.desc_annotation)
        if node.astext().strip().startswith("[")
    ]
    assert any("component" in role for role in roles)


# -- U6-IMPL-2: phase inventory -----------------------------------------------


def test_phases_are_listed_in_execution_order_not_alphabetical():
    """Alphabetical would put ``build`` after ``run``, which reads as nonsense
    to anyone who knows UVM and teaches the wrong thing to anyone who does not."""
    assert phase_inventory(["run_phase", "build_phase", "connect_phase"]) == [
        "build_phase", "connect_phase", "run_phase",
    ]


def test_the_run_time_schedule_counts_as_phases():
    """A component using ``main_phase`` uses it *instead of* ``run_phase``; a
    list that omitted it would report that component as doing nothing."""
    assert phase_inventory(["main_phase", "reset_phase"]) == [
        "reset_phase", "main_phase",
    ]


def test_a_method_that_is_not_a_phase_is_not_listed():
    assert phase_inventory(["build_phase", "do_the_thing", "new"]) == ["build_phase"]


@pytest.mark.sphinx
@sphinx_config
def test_the_phase_inventory_renders_on_a_component_page(page):
    assert "UVM phases" in page
    assert "build_phase" in page


@pytest.mark.sphinx
@sphinx_config
def test_a_class_with_no_phases_gets_no_field(doctree):
    """``ovr_item`` is a sequence item and implements none. An empty "UVM
    phases" heading would read as a component that does nothing."""
    fields = [
        node for node in doctree.findall(nodes.field_list)
        if "sv-uvm-phases" in node.get("classes", [])
    ]
    # `ovr_agent` and `ovr_env` have build_phase; `ovr_item` has none.
    assert len(fields) == 2


# -- U6-IMPL-4: used-by -------------------------------------------------------


def _table(doctree, index=0):
    return list(doctree.findall(nodes.table))[index]


def _rows(table):
    body = next(iter(table.findall(nodes.tbody)))
    return [
        [entry.astext() for entry in row.findall(nodes.entry)]
        for row in body.findall(nodes.row)
    ]


@pytest.mark.sphinx
@sphinx_config
def test_used_by_names_the_component_that_builds_it(doctree):
    rows = _rows(_table(doctree))
    assert rows == [["ovr_agent", "drv", "factory"]]


@pytest.mark.sphinx
@sphinx_config
def test_the_parent_is_a_cross_reference(doctree):
    targets = {
        node["reftarget"] for node in _table(doctree).findall(addnodes.pending_xref)
    }
    assert "ovr_agent" in targets


@pytest.mark.sphinx
@sphinx_config
def test_a_component_nothing_builds_says_so_rather_than_rendering_empty(page):
    """``fast_driver`` exists only as an override target. "Registered and never
    instantiated" is a finding; an empty table is a shrug."""
    assert "fast_driver is not built by name anywhere" in page


@pytest.mark.sphinx
@sphinx_config
def test_a_component_reached_only_by_override_is_told_it_may_still_appear(page):
    """The honest half of the previous finding: ``fast_driver`` is not built
    anywhere *by name*, and it may well be what runs."""
    assert "stands in for ovr_driver through a factory override" in page


def test_a_role_is_found_without_the_library_in_the_index():
    """The finding the documentation build produced, and the one no fixture
    test could: a real project indexes *its own* sources, not UVM's. A chain
    walk over ``extends`` names reaches ``uvm_agent`` and stops there, because
    ``uvm_agent`` is not an object in that index and never will be.

    The fixture tests all compile the stub into the same index, so the walk
    reaches ``uvm_component`` and everything passed while the badge rendered on
    nothing in a real build.
    """
    assert uvm_role(["ovr_agent", "uvm_agent"]) == "component"
    assert uvm_role(["my_item", "uvm_sequence_item"]) == "sequence item"
    assert uvm_role(["my_seq", "uvm_sequence"]) == "sequence"
    assert uvm_role(["helper", "some_base"]) == ""
