"""U0-TEST-2: testbench extraction is paid for only when something asks.

The contract test for the UVM feature, mirroring ``test_lazy_elaboration.py``.
Extracting the component hierarchy means visiting every ``build_phase`` in the
project, and the overwhelming majority of builds --- including every RTL-only
project --- render no UVM directive at all.  Those builds must pay nothing.

Anything that reintroduces an eager walk breaks this test rather than quietly
costing every user time on every build.
"""

from __future__ import annotations

import pytest

from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


def test_build_index_does_not_extract():
    """Building the index attaches a provider but never calls it."""
    index = uvm_stub_index("basic_tb.sv")

    provider = index.uvm_provider
    assert provider is not None, "the provider must be attached during build"
    assert provider.computed is False
    assert provider.walk_count == 0


def test_extraction_happens_once_and_is_memoized():
    index = uvm_stub_index("basic_tb.sv")
    provider = index.uvm_provider

    first = index.uvm_structure
    assert provider.computed is True
    assert provider.walk_count == 1

    second = index.uvm_structure
    assert second is first, "the second call must reuse the memoized result"
    assert provider.walk_count == 1


def test_rtl_and_uvm_walks_are_independent():
    """Asking for one hierarchy must not compute the other.

    They are separate costs answering separate questions; a project that only
    documents its testbench should not pay to walk the RTL instance tree.
    """
    index = uvm_stub_index("basic_tb.sv")

    index.uvm_structure

    assert index.uvm_provider.walk_count == 1
    assert index.structure_provider.computed is False


def test_the_config_scan_is_lazy_too():
    index = uvm_stub_index("config_tb.sv")
    provider = index.uvm_provider

    assert provider.config_computed is False
    assert provider.config_walk_count == 0

    first = provider.config()
    assert provider.config_computed is True
    assert provider.config_walk_count == 1

    assert provider.config() is first
    assert provider.config_walk_count == 1


def test_the_config_scan_does_not_elaborate_the_hierarchy():
    """A page with only a config table must not walk a single build_phase.

    The two are separate scans answering separate questions, and the config one
    is project-wide rather than rooted --- so tying it to the tree walk would
    both cost more and fail on a project with no detectable root at all.
    """
    index = uvm_stub_index("config_tb.sv")

    index.uvm_provider.config()

    assert index.uvm_provider.walk_count == 0
    assert index.uvm_provider.computed is False


def test_a_schematic_shares_the_trees_walk():
    """Ports and connections are read during the component walk, not after it.

    The claim the cost section makes: a tree and a schematic rooted at the same
    component pay for one walk between them. It is only true because the walk
    collects all three things at once, so it is worth asserting rather than
    describing.
    """
    provider = uvm_stub_index("tlm_tb.sv").uvm_provider

    structure = provider.get("tlm_env")
    assert provider.walk_count == 1

    provider.get("tlm_env")
    assert provider.walk_count == 1, "memoized per root"
    assert structure.connections_of("tlm_env"), "and it already has the wiring"
    assert structure.type_of("tlm_monitor").ports, "and the ports"
