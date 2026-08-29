"""U1-TEST-5: the regression guard for the silent-drop bug (§8.7).

This is the most important test in the phase, so it is worth stating plainly
what it protects against.

When a component's type cannot be resolved, slang discards the whole statement
that used it. The `create` call is simply **not in the AST**. A walk that reads
`build_phase` and nothing else therefore produces a tree that is short by
exactly the components that failed to resolve --- and reports no error, because
from its point of view nothing went wrong.

The output of that walk is indistinguishable from a healthy testbench. A reader
cannot tell an environment with no register model from one whose register model
failed to parse, which means a build problem is being concealed by the tool
whose job is to explain the design.

Recovering those nodes needs a second, independent source: the class's own
properties, where the declaration survives with an `<error>` type even though
the statement using it did not.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import STATE_OK, STATE_UNRESOLVED
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def missing():
    return uvm_stub_index("missing_dep_tb.sv").uvm_structure


def test_the_resolvable_sibling_is_still_extracted(missing):
    """Degradation is local: one bad type does not cost the whole class."""
    agt = next(c for c in missing.children_of("reg_env") if c.handle == "agt")

    assert agt.type_name == "good_agent"
    assert agt.state == STATE_OK


def test_the_unresolvable_child_is_present(missing):
    """The bug itself: `ral` used to vanish, leaving a tree that looked fine."""
    handles = [c.handle for c in missing.children_of("reg_env")]

    assert "ral" in handles, (
        "an unresolvable component must appear in the tree; dropping it "
        "produces output that cannot be distinguished from a healthy testbench"
    )


def test_the_unresolvable_child_is_marked_unresolved(missing):
    ral = next(c for c in missing.children_of("reg_env") if c.handle == "ral")

    assert ral.state == STATE_UNRESOLVED
    assert "[unresolved]" in ral.label


def test_the_declared_type_name_is_recovered_from_source(missing):
    """The elaborated type is `<error>` and says nothing.

    The name a reader needs is in the CST, one hop above the member's own
    syntax node --- which is only the declarator (`ral`). Without this hop the
    node appears but cannot say what it was supposed to be, which is barely
    better than dropping it.
    """
    ral = next(c for c in missing.children_of("reg_env") if c.handle == "ral")

    assert ral.type_name == "my_reg_block"


def test_unresolved_nodes_are_enumerable_for_reporting(missing):
    """Views must be able to say "2 unresolved" without re-walking the tree."""
    assert [c.handle for c in missing.unresolved] == ["ral"]


def test_the_walk_does_not_descend_below_an_unresolved_node(missing):
    """Nothing is known below it, and nothing is invented."""
    ral = next(c for c in missing.children_of("reg_env") if c.handle == "ral")

    assert missing.children_of(ral.type_name) == []


def test_the_rest_of_the_testbench_still_elaborates(missing):
    """A missing package is 2 errors, not a failed build."""
    assert missing.root == "reg_test"
    assert [c.type_name for c in missing.children_of("reg_test")] == ["reg_env"]
    assert "good_agent" in missing.children


def test_unresolved_is_distinct_from_opaque():
    """Two different facts that must not be conflated.

    `opaque` says "the tool was told to stop here". `unresolved` says "the tool
    could not get here". Collapsing them would let a genuine build failure
    render as a deliberate editorial choice.
    """
    missing = uvm_stub_index("missing_dep_tb.sv").uvm_structure
    boxed = uvm_stub_index(
        "blackbox_tb.sv", uvm_blackbox=["acme_vip_*"]
    ).uvm_structure

    assert [c.handle for c in missing.unresolved] == ["ral"]
    assert missing.opaque == []

    assert [c.handle for c in boxed.opaque] == ["ral", "vip"]
    assert boxed.unresolved == []
