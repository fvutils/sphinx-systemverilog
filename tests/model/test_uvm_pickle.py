"""U0-TEST-3: the UVM provider must never reach Sphinx's pickle either.

This is the same failure mode ``test_structure_pickle.py`` guards for the RTL
provider, and it is worth guarding twice because the consequence is
disproportionate: the index lives on ``env``, Sphinx pickles ``env``, and a
pyslang ``Compilation`` raises ``TypeError: cannot pickle``.  A second provider
left in place would break *every* build --- including projects that never write
a UVM directive.

Landing this before the extraction logic (U1) is deliberate.  A test that only
appears once there is something to extract is a test written after the trap has
already been sprung.
"""

from __future__ import annotations

import pickle

import pytest

from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


def test_index_with_live_uvm_provider_pickles():
    index = uvm_stub_index("basic_tb.sv")
    assert index.uvm_provider is not None

    restored = pickle.loads(pickle.dumps(index))

    assert restored.uvm_provider is None
    assert len(restored) == len(index)


def test_index_pickles_after_extraction():
    """A memoized UvmStructure must not keep the compilation alive either."""
    index = uvm_stub_index("basic_tb.sv")
    assert index.uvm_structure is not None

    restored = pickle.loads(pickle.dumps(index))

    assert restored.uvm_provider is None


def test_unpickled_index_degrades_instead_of_crashing():
    """No provider means no structure, not an exception."""
    index = uvm_stub_index("basic_tb.sv")
    restored = pickle.loads(pickle.dumps(index))

    assert restored.uvm_structure is None


def test_uvm_structure_is_picklable_on_its_own():
    """The data the walk produces holds no pyslang references."""
    structure = uvm_stub_index("basic_tb.sv").uvm_structure

    restored = pickle.loads(pickle.dumps(structure))

    assert restored.root == structure.root
    assert restored.children == structure.children


def test_both_providers_are_dropped_together():
    """The RTL provider must not be resurrected by the UVM one, or vice versa.

    Guards the shape of ``__getstate__`` rather than one of its entries: the
    realistic regression is adding a third provider and updating only the
    attribute that happened to be under test.
    """
    index = uvm_stub_index("basic_tb.sv")
    assert index.structure_provider is not None
    assert index.uvm_provider is not None

    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure_provider is None
    assert restored.uvm_provider is None
