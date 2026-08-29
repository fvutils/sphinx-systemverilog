"""U1-TEST-3: creation-site extraction from ``build_phase``.

The testbench hierarchy is not elaborated by anything, so every fact in the
model is read off a statement someone wrote. These tests pin what is read, and
--- just as importantly --- what is *not* claimed when the source does not say.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import (
    BY_FACTORY,
    BY_NEW,
    KIND_COMPONENT,
    KIND_PORT,
    STATE_OK,
    STATE_OPAQUE,
    classify,
)
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def basic():
    return uvm_stub_index("basic_tb.sv").uvm_structure


def _child(structure, parent, handle):
    return next(c for c in structure.children_of(parent) if c.handle == handle)


# -- the containment spine ----------------------------------------------------


def test_root_is_detected_from_run_test(basic):
    """U1-IMPL-10: no configuration needed when the testbench names its test."""
    assert basic.root == "my_test"
    assert basic.root_origin == "run_test"


def test_the_spine_is_extracted(basic):
    assert [c.type_name for c in basic.children_of("my_test")] == ["my_env"]

    env = {c.handle: c.type_name for c in basic.children_of("my_env")}
    assert env["agt_a"] == "my_agent"
    assert env["agt_b"] == "my_agent"
    assert env["sb"] == "my_scoreboard"

    agent = {c.handle: c.type_name for c in basic.children_of("my_agent")}
    assert agent["mon"] == "my_monitor"
    assert agent["drv"] == "my_driver"


def test_a_type_used_twice_is_described_once(basic):
    """Two agents of one type are one type, not two.

    Memoizing by type name is also what terminates a mutually-recursive
    ``build_phase``, which is legal to write.
    """
    handles = [c.handle for c in basic.children_of("my_env")]
    assert handles.count("agt_a") == 1 and handles.count("agt_b") == 1

    assert len(basic.children_of("my_agent")) == 3


def test_instance_name_and_handle_are_both_recorded(basic):
    """They are usually equal, and nothing guarantees it."""
    child = _child(basic, "my_env", "agt_a")

    assert child.handle == "agt_a"
    assert child.inst_name == "agt_a"


# -- what the source does not say ---------------------------------------------


def test_a_conditional_create_is_flagged_not_hidden(basic):
    """U1-IMPL-6: `if (is_active)` means *may* be built.

    Both alternatives are wrong: omitting the driver hides a component that
    usually exists, and showing it plainly asserts something the source does
    not. It is reported, and marked.
    """
    drv = _child(basic, "my_agent", "drv")
    mon = _child(basic, "my_agent", "mon")

    assert drv.conditional is True
    assert mon.conditional is False
    assert "[conditional]" in drv.label


def test_a_loop_create_reports_multiplicity_n_not_a_number(basic):
    """U1-IMPL-6: the trip count is not constant-foldable, so it is not faked.

    `for (int i = 0; i < n_extra; i++)` where `n_extra` is a variable: slang
    reports no constant value for the stop expression, and guessing 4 from the
    array declaration would be a fabrication that happens to be right here and
    wrong the moment the count comes from `config_db`.
    """
    extra = _child(basic, "my_env", "extra")

    assert extra.multiplicity == "N"
    assert extra.type_name == "my_agent"


def test_a_computed_instance_name_is_reported_as_unknown(basic):
    """`$sformatf("extra_%0d", i)` has no value until the simulation runs."""
    extra = _child(basic, "my_env", "extra")

    assert extra.inst_name is None
    assert extra.handle == "extra", "the array handle is still knowable"


# -- how it was created -------------------------------------------------------


def test_factory_creates_are_recorded_as_such(basic):
    assert _child(basic, "my_env", "agt_a").created_by == BY_FACTORY


def test_direct_new_is_a_separate_path(basic):
    """U1-IMPL-5: `new()` is `ExpressionKind.NewClass`, never a `Call`.

    A walker that only looks at call expressions silently misses every
    directly-constructed component. Bypassing the factory is legal and common
    for components nobody expects to override, so those components would
    disappear from the tree with no indication that anything was missing.
    """
    cov = _child(basic, "my_env", "cov")

    assert cov.created_by == BY_NEW
    assert cov.type_name == "my_coverage"
    assert cov.inst_name == "cov"
    assert cov.state == STATE_OK, "a direct new is not a boundary"


# -- classification -----------------------------------------------------------


@pytest.mark.parametrize(
    "type_name,tier",
    [
        ("my_test", "test"),
        ("my_env", "env"),
        ("my_agent", "agent"),
        ("my_driver", "driver"),
        ("my_monitor", "monitor"),
        ("my_sequencer", "sequencer"),
        ("my_scoreboard", "analysis"),
    ],
)
def test_tier_is_derived_from_the_base_chain(basic, type_name, tier):
    """U1-IMPL-2: the §7.4 taxonomy, with zero authoring required."""
    assert basic.type_of(type_name).tier == tier


def test_a_tlm_port_is_not_a_component_and_is_not_in_the_tree(basic):
    """Real UVM: `uvm_port_base #(IF) extends IF`, and `IF` is `uvm_void`-derived.

    A port holds an internal component proxy rather than being a component, so
    it never appears in a hierarchy read from `build_phase`. Worth asserting
    because the test stub originally modelled this wrongly, which put a port
    under every monitor and was only caught against real UVM.
    """
    assert [c.handle for c in basic.children_of("my_monitor")] == []


def test_port_types_are_still_classified_for_the_schematic(basic):
    """The classification survives even though the tree has no use for it.

    The schematic is made of ports, and reads them from declared member types
    rather than from creation sites.
    """
    assert classify(["uvm_analysis_port", "uvm_port_base"])[0] == KIND_PORT
    assert classify(["my_agent", "uvm_agent", "uvm_component"])[0] == KIND_COMPONENT


def test_library_types_are_stopped_at_but_still_shown(basic):
    """The always-on library rule (U1-IMPL-7): stop, do not drop.

    A `uvm_tlm_analysis_fifo` *is* a component, so it belongs in the tree ---
    and its internals are UVM's business, not the testbench author's.
    """
    fifo = _child(basic, "my_scoreboard", "fifo")

    assert fifo.state == STATE_OPAQUE
    assert fifo.type_name.startswith("uvm_tlm_analysis_fifo")
    assert basic.children_of(fifo.type_name) == [], "not descended into"


def test_user_components_deriving_from_uvm_are_not_black_boxed(basic):
    """Every component in a testbench derives from a `uvm_` base.

    The library rule matches the type's *own* name, so `my_agent` stays walkable
    while `uvm_analysis_port` does not. Getting this backwards would black-box
    the entire testbench.
    """
    assert _child(basic, "my_env", "agt_a").state == STATE_OK
    assert basic.children_of("my_agent") != []


def test_non_component_classes_are_not_children(basic):
    """`my_item` is a sequence item, not a component; it is not in the tree."""
    assert "my_item" not in basic.children


# -- root resolution (U1-IMPL-10) ---------------------------------------------


def test_configured_root_overrides_auto_detection():
    structure = uvm_stub_index("basic_tb.sv", uvm_root="my_env").uvm_structure

    assert structure.root == "my_env"
    assert structure.root_origin == "config"
    assert "my_test" not in structure.children


def test_a_requested_root_overrides_the_configured_one():
    """A directive naming its own root is the most specific request."""
    provider = uvm_stub_index("basic_tb.sv", uvm_root="my_env").uvm_provider

    structure = provider.get(root="my_agent")

    assert structure.root == "my_agent"
    assert structure.root_origin == "directive"


def test_each_root_is_extracted_and_memoized_separately():
    """A page may document two testbenches; neither may evict the other."""
    provider = uvm_stub_index("basic_tb.sv").uvm_provider

    first = provider.get()
    second = provider.get(root="my_agent")

    assert provider.walk_count == 2
    assert provider.get() is first
    assert provider.get(root="my_agent") is second
    assert provider.walk_count == 2


def test_several_testbenches_are_all_reported_as_candidates():
    """Two `run_test` calls is a normal project, not an error.

    One is picked so the common case needs no configuration, but all of them
    are reported so a directive can tell the reader there was a choice rather
    than presenting an arbitrary pick as the answer.
    """
    structure = uvm_stub_index(
        "basic_tb.sv", "missing_dep_tb.sv"
    ).uvm_structure

    assert set(structure.root_candidates) == {"my_test", "reg_test"}
    assert structure.root in structure.root_candidates


def test_no_run_test_means_no_root_and_no_guess():
    """Nothing names a test, so nothing is invented."""
    structure = uvm_stub_index().uvm_structure

    assert structure.root == ""
    assert structure.root_origin == ""
    assert structure.children == {}


# -- structure bookkeeping ----------------------------------------------------


def test_component_count_and_truncation_are_reported(basic):
    assert basic.component_count == len(basic.children)
    assert basic.truncated is False
