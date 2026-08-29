"""U1-TEST-4: black-boxing stops the walk without hiding the node.

Black-boxing exists because parts of a testbench legitimately should not be
walked into --- generated register models, vendor VIP, the UVM library itself.
The thing being tested here is not that the walk stops, which is easy, but that
stopping is *reported*: an opaque node is present, named and counted.

A boundary is a statement about how far the tool looked. It must never read as
a statement about what exists.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import STATE_OK, STATE_OPAQUE
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


def _boxed(**kwargs):
    return uvm_stub_index("blackbox_tb.sv", **kwargs).uvm_structure


def _child(structure, parent, handle):
    return next(c for c in structure.children_of(parent) if c.handle == handle)


# -- the three matching rules -------------------------------------------------


def test_base_class_match_uses_the_whole_chain():
    """`my_reg_block extends uvm_reg_block`, so one entry covers the family."""
    structure = _boxed(uvm_blackbox_bases=["uvm_reg_block"])

    ral = _child(structure, "bb_env", "ral")
    assert ral.state == STATE_OPAQUE
    assert ral.type_name == "my_reg_block"


def test_glob_match_on_the_type_name():
    structure = _boxed(uvm_blackbox=["acme_vip_*"])

    assert _child(structure, "bb_env", "vip").state == STATE_OPAQUE


def test_library_types_are_stopped_at_without_configuration():
    """The always-on rule. UVM's own internals are never the subject."""
    structure = uvm_stub_index("basic_tb.sv").uvm_structure

    fifo = _child(structure, "my_scoreboard", "fifo")
    assert fifo.state == STATE_OPAQUE
    assert fifo.type_name.startswith("uvm_")


# -- what stopping means ------------------------------------------------------


def test_an_opaque_node_is_present_and_named():
    """The whole point: the reader is told the register model is there."""
    structure = _boxed(uvm_blackbox_bases=["uvm_reg_block"])

    handles = [c.handle for c in structure.children_of("bb_env")]
    assert handles == ["ral", "vip", "agt"]


def test_an_opaque_node_is_not_descended_into():
    """`my_reg_block` builds a field; the field must not appear."""
    structure = _boxed(uvm_blackbox_bases=["uvm_reg_block"])

    assert structure.children_of("my_reg_block") == []
    assert "my_reg_field" not in structure.children


def test_opaque_nodes_are_enumerable_for_reporting():
    structure = _boxed(
        uvm_blackbox=["acme_vip_*"], uvm_blackbox_bases=["uvm_reg_block"]
    )

    assert [c.handle for c in structure.opaque] == ["ral", "vip"]


# -- selectivity --------------------------------------------------------------


def test_boundaries_are_selective():
    """A configured boundary must not spill onto its siblings."""
    structure = _boxed(
        uvm_blackbox=["acme_vip_*"], uvm_blackbox_bases=["uvm_reg_block"]
    )

    agt = _child(structure, "bb_env", "agt")
    assert agt.state == STATE_OK
    assert agt.type_name == "plain_agent"


def test_no_configuration_means_no_user_boundaries():
    """Everything except library types is walked when nothing is configured."""
    structure = _boxed(uvm_blackbox=[], uvm_blackbox_bases=[])

    assert _child(structure, "bb_env", "ral").state == STATE_OK
    assert _child(structure, "bb_env", "vip").state == STATE_OK
    assert "my_reg_field" in structure.children
    assert "acme_vip_driver" in structure.children


def test_a_glob_that_matches_nothing_changes_nothing():
    structure = _boxed(uvm_blackbox=["nothing_matches_*"], uvm_blackbox_bases=[])

    assert [c.state for c in structure.children_of("bb_env")] == [STATE_OK] * 3


def test_glob_matching_ignores_specialization_parameters():
    """`uvm_tlm_analysis_fifo#(my_item)` is matched as `uvm_tlm_analysis_fifo`.

    Requiring a user to write the parameter list into a glob would make the
    setting unusable for exactly the types most worth black-boxing, which are
    routinely parameterized.
    """
    structure = uvm_stub_index(
        "basic_tb.sv", uvm_blackbox=["uvm_tlm_analysis_fifo"]
    ).uvm_structure

    assert _child(structure, "my_scoreboard", "fifo").state == STATE_OPAQUE
