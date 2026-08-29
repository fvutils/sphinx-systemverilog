"""U3-TEST-2: ``connect_phase`` extraction and the TLM port inventory.

Two facts carry this phase, and both are about *where the information lives*
rather than about walking statements:

* a connection's endpoints are member-access chains, and what they end at ---
  port or component --- is decided by the chain's **type**, never by its name.
  ``agt_a.mon.ap`` and ``vseqr.seqr_a`` are written identically and mean
  entirely different things.
* a component's ports come from its **declared members**, not from creation
  sites.  U1 established that a TLM port is not a ``uvm_component`` and so
  never appears in a tree read from ``build_phase``; the declared type is the
  only place a port is visible at all.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import (
    LINK_ANALYSIS,
    LINK_HANDLE,
    LINK_SEQ_ITEM,
    classify_port,
)
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def structure():
    return uvm_stub_index("tlm_tb.sv").uvm_provider.get()


def _connection(structure, owner, source_text):
    return next(
        c for c in structure.connections_of(owner) if c.source.text == source_text
    )


# -- endpoints ----------------------------------------------------------------


def test_a_connect_call_resolves_both_endpoints(structure):
    """The §3.4 result, as the schematic consumes it."""
    connection = _connection(structure, "tlm_env", "agt_a.mon.ap")

    assert connection.source.path == ("agt_a", "mon")
    assert connection.source.port == "ap"
    assert connection.target.path == ("sb",)
    assert connection.target.port == "aimp"


def test_the_destination_survives_the_stubs_base_class_typing(structure):
    """``connect`` takes a ``uvm_port_base``, so the argument arrives converted.

    Real UVM types ``connect`` against the specific interface; the stub types it
    against the common base so fixtures stay writable. Either way the argument
    is wrapped, and the endpoint's real type has to come from inside the wrap.
    """
    connection = _connection(structure, "tlm_env", "agt_a.mon.ap")

    assert connection.target.type_name.startswith("uvm_analysis_imp")


def test_a_connection_written_inside_an_agent_is_recorded_on_the_agent(structure):
    """Not on the env: it is a property of the type, drawn once per instance."""
    connection = _connection(structure, "tlm_agent", "drv.seq_item_port")

    assert connection.source.path == ("drv",)
    assert connection.target.path == ("seqr",)
    assert structure.connections_of("tlm_env") != []


def test_a_conditional_connection_is_flagged(structure):
    """``if (is_active)`` around a connect means it may not happen."""
    assert _connection(structure, "tlm_agent", "drv.seq_item_port").conditional
    assert not _connection(structure, "tlm_env", "agt_a.mon.ap").conditional


# -- link kinds ---------------------------------------------------------------


def test_link_kinds_come_from_the_port_type(structure):
    assert _connection(structure, "tlm_env", "agt_a.mon.ap").kind == LINK_ANALYSIS
    assert (
        _connection(structure, "tlm_agent", "drv.seq_item_port").kind == LINK_SEQ_ITEM
    )


def test_a_virtual_sequencer_is_wired_by_assignment_not_by_connect(structure):
    """The edge a connect-only walker cannot see.

    ``vseqr.seqr_a = agt_a.seqr`` is an assignment. A virtual sequencer is the
    one component whose entire purpose is the connections it holds, so drawing
    it with none would be worse than not drawing it.
    """
    connection = _connection(structure, "tlm_env", "vseqr.seqr_a")

    assert connection.kind == LINK_HANDLE
    assert connection.source.port == "", "a handle is not a port"
    assert connection.target.path == ("agt_a", "seqr")
    assert connection.source.component and connection.target.component


def test_the_assignment_direction_is_the_one_stimulus_flows(structure):
    """LHS is the virtual sequencer, and that is the source of the edge."""
    connection = _connection(structure, "tlm_env", "vseqr.seqr_a")

    assert connection.source.path[0] == "vseqr"
    assert connection.target.path[0] == "agt_a"


def test_only_connect_phase_assignments_become_connections(structure):
    """Otherwise every ``m_parent = parent`` in a constructor would be an edge.

    A ``connect`` *call* is unambiguous wherever it appears; a component-handle
    assignment is wiring only by the convention that it happens here.
    """
    owners = {c.owner for conns in structure.connections.values() for c in conns}

    assert owners == {"tlm_env", "tlm_agent"}


def test_a_users_own_connect_method_is_not_a_connection(structure):
    """Keyed on ``uvm_port_base::connect``, not on the name ``connect``.

    The fixture calls ``cov.connect(sb)`` from ``connect_phase`` --- a method
    ``tlm_coverage`` declares itself. It is exactly where a name-based walker
    would be most confident, and it is not a TLM connection.
    """
    sources = {c.source.text for c in structure.connections_of("tlm_env")}

    assert "cov" not in sources, sources
    assert len(structure.connections_of("tlm_env")) == 5


# -- port inventory -----------------------------------------------------------


def test_ports_are_read_from_declared_members(structure):
    """U1 proved a port is not a component, so this is the only place they are.

    A port never appears in a tree read from ``build_phase`` --- real UVM
    declares ``uvm_port_base #(IF) extends IF``, not ``extends uvm_component``
    --- so a schematic that waited for one to show up there would draw boxes
    with no connection points at all.
    """
    monitor = structure.type_of("tlm_monitor")

    assert [p.name for p in monitor.ports] == ["ap"]
    assert monitor.ports[0].type_name.startswith("uvm_analysis_port")


def test_a_port_records_its_role(structure):
    assert structure.type_of("tlm_monitor").port("ap").role == "port"
    assert structure.type_of("tlm_scoreboard").port("aimp").role == "imp"
    assert (
        structure.type_of("tlm_sequencer").port("seq_item_export").role == "export"
    )


def test_a_component_handle_is_not_listed_as_a_port(structure):
    """``tlm_vseqr`` holds two sequencers; neither is a port."""
    assert structure.type_of("tlm_vseqr").ports == ()


def test_a_component_with_no_ports_reports_none(structure):
    assert structure.type_of("tlm_env").ports == ()


def test_inherited_ports_are_found_and_marked_as_the_librarys(structure):
    """``tlm_driver`` declares nothing; UVM gives it two ports.

    That is how real UVM behaves and it is now how the stub behaves, because
    the corpus gate found the divergence: against real ``uvm_driver`` a driver
    arrives with ``seq_item_port``, ``seq_item_prod_if`` and ``rsp_port``, and
    a schematic that drew all of them would be labelling plumbing.
    """
    driver = structure.type_of("tlm_driver")

    assert {p.name for p in driver.ports} == {"seq_item_port", "rsp_port"}
    assert all(p.library for p in driver.ports)
    assert driver.port("seq_item_port").declared_by == "uvm_driver"


def test_a_port_the_user_declared_is_not_marked_as_the_librarys(structure):
    """The distinction the schematic's port filter turns on."""
    assert structure.type_of("tlm_monitor").port("ap").library is False


@pytest.mark.parametrize(
    "chain, expected",
    [
        (["uvm_analysis_port", "uvm_port_base"], ("port", LINK_ANALYSIS)),
        (["uvm_analysis_export", "uvm_port_base"], ("export", LINK_ANALYSIS)),
        (["uvm_analysis_imp", "uvm_port_base"], ("imp", LINK_ANALYSIS)),
        (["uvm_seq_item_pull_port", "uvm_port_base"], ("port", LINK_SEQ_ITEM)),
        (["uvm_seq_item_pull_export", "uvm_port_base"], ("export", LINK_SEQ_ITEM)),
        # A user subclass: the convention is inherited along with the base.
        (["my_ap", "uvm_analysis_port", "uvm_port_base"], ("port", LINK_ANALYSIS)),
    ],
)
def test_port_classification_reads_the_naming_convention(chain, expected):
    """UVM records direction nowhere structural, so the suffix is all there is."""
    assert classify_port(chain) == expected
