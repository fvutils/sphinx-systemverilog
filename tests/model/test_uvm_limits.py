"""U1-TEST-6: pathological input terminates, and says that it did.

A testbench cannot recurse the way generate-guarded RTL can, but a
mutually-recursive ``build_phase`` is legal to write and would otherwise walk
forever. The ceilings exist so a bad build fails visibly instead of hanging.

Truncation is always reported. A silently shortened tree is the same failure
mode as a silently dropped node --- output that looks complete and is not.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import MAX_DEPTH, UvmProvider
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


def _provider(**kwargs) -> UvmProvider:
    """A provider over the basic testbench, with overridable limits."""
    index = uvm_stub_index("basic_tb.sv")
    base = index.uvm_provider
    return UvmProvider(base._compilation, base._source_manager, **kwargs)


def test_an_unbounded_walk_is_not_truncated():
    structure = _provider().get()

    assert structure.truncated is False
    assert structure.component_count == 8


def test_the_component_budget_stops_the_walk():
    structure = _provider(max_components=3).get()

    assert structure.truncated is True
    assert structure.component_count == 3


def test_a_truncated_walk_still_returns_what_it_found():
    """Partial output beats no output, provided it is labelled partial."""
    structure = _provider(max_components=2).get()

    assert structure.root == "my_test"
    assert structure.children_of("my_test") != []
    assert structure.truncated is True


def test_a_budget_of_zero_falls_back_to_the_default():
    """Zero is not a meaningful ceiling, so it is read as "unset".

    Consistent with `sv_structure_max_instances`, and it keeps a mistyped
    `conf.py` from producing an empty tree with no explanation.
    """
    structure = _provider(max_components=0).get()

    assert structure.truncated is False
    assert structure.component_count == 8


def test_depth_is_bounded_independently_of_the_budget():
    """A cycle would exhaust depth long before it exhausts a 5000 budget.

    In practice the type-name memo already terminates cycles, so this asserts
    the second line of defence rather than the first.
    """
    assert MAX_DEPTH < 5000

    structure = _provider(max_components=10_000).get()
    assert structure.truncated is False


def test_no_root_yields_an_empty_structure_not_an_error():
    """A project with no testbench is not a broken project."""
    structure = UvmProvider(
        uvm_stub_index()._uvm_provider._compilation, root=""
    ).get()

    assert structure.root == ""
    assert structure.children == {}
    assert structure.truncated is False


def test_an_unknown_configured_root_yields_an_empty_structure():
    """Reported by the directive as a warning; the model just says nothing."""
    structure = _provider(root="no_such_test").get()

    assert structure.root == "no_such_test"
    assert structure.root_origin == "config"
    assert structure.children == {}
