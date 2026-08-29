"""U5-TEST-2: the RTL <-> testbench bridge, both ends and the join.

Every other extraction in this feature reads one elaboration.  This one reads
two and joins them through a string, so there are three separate things to get
right, and a test that only covers the happy path covers none of them:

* **the set side** resolves a ``config_db`` value back to an *elaborated*
  interface instance --- a hierarchical path, not a name;
* **the RTL side** finds the module instances that interface actually reaches,
  including through a modport;
* **the get side** pairs by field name, and the pairing is narrowed to virtual
  interfaces, which the ordinary config table cannot do.

The three ways it fails --- read by nobody, wired to nothing, given a handle
instead of an instance --- are what the phase exists to report, so each has a
fixture shape of its own.
"""

from __future__ import annotations

import pytest

from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def provider():
    return uvm_stub_index("bridge_tb.sv").uvm_provider


@pytest.fixture
def bridge(provider):
    return provider.bridge()


def _by_field(bridge, name):
    return next(b for b in bridge.bindings if b.field == name)


# -- the set side -------------------------------------------------------------


def test_a_virtual_interface_set_is_told_from_every_other_set(provider):
    """Read from the specialization's ``T``, which slang models as a
    ``VirtualInterfaceType``, rather than from the type's spelling. A class
    named ``bus_if`` is not an interface and would fool a name test."""
    assert {b.field for b in provider.bridge().bindings} == {
        "vif", "vif_alias", "clk_vif", "spare_vif"
    }


def test_ordinary_settings_are_not_bindings():
    """Measured against a fixture that has both, so "only the virtual ones"
    is a filter that was exercised rather than one no input reached."""
    other = uvm_stub_index("config_tb.sv").uvm_provider
    config = other.config()

    assert {a.type_name for a in config.accesses} >= {"int", "string", "cfg_if"}
    assert not any(a.virtual_interface for a in config.accesses
                   if a.type_name in ("int", "string"))
    assert [b.field for b in other.bridge().bindings] == ["vif"]


def test_the_value_resolves_to_an_elaborated_instance_path(bridge):
    """The point of `U5-IMPL-2`: ``u_bus`` as written becomes
    ``bridge_tb_top.u_bus``, which is a fact about the elaboration and the only
    form that can be joined to the RTL."""
    assert _by_field(bridge, "vif").instance_path == "bridge_tb_top.u_bus"


def test_a_handle_rather_than_an_instance_is_reported_not_guessed(bridge):
    """``set(this, "drv", "vif_alias", vif)`` passes on a virtual-interface
    handle. There is no instance behind it here, and naming the one the handle
    happens to hold would be inventing a run-time fact."""
    alias = _by_field(bridge, "vif_alias")
    assert alias.resolved is False
    assert alias.instance_path == ""
    assert alias.drivers == ()
    assert bridge.unresolved == [alias]


# -- the RTL side -------------------------------------------------------------


def test_the_interface_is_joined_to_the_rtl_it_drives(bridge):
    """`U5-ACC`'s middle link: ``bridge_tb_top.u_bus`` -> ``u_dut``."""
    drivers = _by_field(bridge, "vif").drivers
    assert [(d.path, d.type_name, d.port) for d in drivers] == [
        ("bridge_tb_top.u_dut", "bridge_dut", "bus"),
        ("bridge_tb_top.u_probe", "bridge_probe", "bus"),
    ]


def test_a_modport_connection_still_names_the_interface_instance(bridge):
    """``u_probe`` connects ``.bus(u_bus.mon_mp)``. slang resolves that to the
    interface *instance*, which is why one rule covers both forms --- and why
    a fixture with only whole-interface connections would prove nothing."""
    probe = next(
        d for d in _by_field(bridge, "vif").drivers if d.type_name == "bridge_probe"
    )
    assert probe.port == "bus"


def test_more_than_one_instance_can_be_on_the_far_end(bridge):
    """"The DUT" is the obvious answer and not always the whole answer: a
    monitor or a protocol checker sits on the same interface."""
    assert len(_by_field(bridge, "vif").drivers) == 2


def test_an_interface_wired_to_no_rtl_is_reported(bridge):
    """``u_spare`` is handed over correctly and connects to nothing. The
    binding is fine; the testbench is driving air."""
    spare = _by_field(bridge, "spare_vif")
    assert spare.resolved is True
    assert spare.drivers == ()
    assert bridge.undriven == [spare]


def test_the_interface_does_not_list_itself_as_its_own_driver(bridge):
    """It is an instance declared in the same scope, so the obvious loop finds
    it unless it is excluded."""
    paths = [d.path for d in _by_field(bridge, "vif").drivers]
    assert "bridge_tb_top.u_bus" not in paths


def test_a_signal_port_is_not_an_interface_connection(bridge):
    """``bridge_dut`` also takes ``input logic rst``. Only ports of kind
    ``InterfacePort`` can carry a binding."""
    ports = {d.port for d in _by_field(bridge, "vif").drivers}
    assert "rst" not in ports


# -- the get side -------------------------------------------------------------


def test_the_readers_of_a_binding_are_paired_by_field_name(bridge):
    consumers = [a.where for a in _by_field(bridge, "vif").consumers]
    assert consumers == ["bridge_agent.build_phase", "bridge_test.build_phase"]


def test_a_binding_nothing_reads_is_an_orphan(bridge):
    """The same silent bug the config table reports, with a worse ending: a
    virtual interface has no usable default."""
    assert {b.field for b in bridge.orphans} == {
        "clk_vif", "spare_vif", "vif_alias"
    }


def test_pairing_is_narrowed_to_virtual_interface_gets(provider):
    """A narrowing the config table cannot make, because it does not know the
    type. ``clk_vif`` matches no get of any kind here, and the guard is that
    ``vif``'s consumers are virtual-interface gets rather than every get whose
    field happens to match."""
    binding = _by_field(provider.bridge(), "vif")
    assert all(a.virtual_interface for a in binding.consumers)


def test_two_testbenches_sharing_a_field_name_do_not_cross_pair():
    """``vif`` is the most common field name in UVM, and a project holding two
    testbenches has it twice. Field-name pairing alone reports each one's
    interface as read by the other's components.

    Narrowing on the interface type fixes it and gives up nothing:
    ``uvm_config_db#(T)`` is keyed on ``T``, so a ``get`` of ``virtual cfg_if``
    genuinely cannot read a ``set`` of ``virtual bridge_if``. Unlike scope,
    that is settled statically.

    Found by building the documentation, where four unrelated fixture
    testbenches share one index --- which no single-fixture test reproduces.
    """
    both = uvm_stub_index("bridge_tb.sv", "config_tb.sv").uvm_provider
    bridge = both.bridge()

    bus = next(b for b in bridge.bindings if b.interface_type == "bridge_if"
               and b.field == "vif")
    cfg = next(b for b in bridge.bindings if b.interface_type == "cfg_if")

    assert [a.where for a in bus.consumers] == [
        "bridge_agent.build_phase", "bridge_test.build_phase",
    ]
    assert [a.where for a in cfg.consumers] == ["cfg_test.build_phase"]


def test_the_full_path_from_component_to_dut_is_documented(bridge):
    """`U5-ACC` end to end, as data: a reader can get from a component name to
    an RTL instance without leaving the row."""
    binding = _by_field(bridge, "vif")
    assert "bridge_agent.build_phase" in [a.where for a in binding.consumers]
    assert binding.instance_path == "bridge_tb_top.u_bus"
    assert "bridge_tb_top.u_dut" in [d.path for d in binding.drivers]


# -- cost ---------------------------------------------------------------------


def test_the_bridge_is_scanned_once(provider):
    before = provider.bridge_walk_count
    provider.bridge()
    provider.bridge()
    assert provider.bridge_walk_count == before


def test_a_binding_table_pays_for_no_hierarchy_walk():
    """Neither the RTL hierarchy nor a single ``build_phase``. The RTL join
    descends one hierarchical name rather than searching, which is what keeps
    that true on a design where the walk would be expensive."""
    index = uvm_stub_index("bridge_tb.sv")
    provider = index.uvm_provider
    provider.bridge()

    assert provider.walk_count == 0
    assert provider.sequence_walk_count == 0
    assert index.structure_provider.walk_count == 0


def test_the_bridge_reuses_the_config_scan(provider):
    """A page showing both tables scans ``config_db`` once."""
    fresh = uvm_stub_index("bridge_tb.sv").uvm_provider
    fresh.config()
    fresh.bridge()
    assert fresh.config_walk_count == 1


# -- type identity ------------------------------------------------------------


@pytest.fixture(scope="module")
def typedef_bridge():
    return uvm_stub_index("bridge_typedef_tb.sv").uvm_provider.bridge()


def test_a_typedefd_virtual_interface_still_pairs(typedef_bridge):
    """Narrowing pairing by interface type is only safe if two spellings of the
    same interface unify. Here the ``set`` writes ``virtual td_if`` in full and
    the ``get`` writes a typedef; slang resolves both to one type, so the
    binding is not reported as an orphan it is not.

    This is the narrowing's failure mode arriving from the other direction, and
    ``bridge_tb.sv`` cannot ask the question --- both sides agree there.
    """
    binding = typedef_bridge.bindings[0]

    assert [a.where for a in binding.consumers] == ["td_agent.build_phase"]
    assert binding.orphan is False
    assert binding.drivers[0].path == "td_top.u_dut"


def test_the_type_column_shows_the_unified_spelling(typedef_bridge):
    """A caveat rather than a defect, and worth pinning because it surprises:
    slang reports the *first equivalent spelling it created*, which here is the
    typedef --- so the Interface column reads ``td_vif_t`` even on the row whose
    source says ``virtual td_if``. The same unification the U3 schematic found
    on parameterized ports. The join to the RTL is unaffected: that runs on the
    instance path, not on the type name.
    """
    assert typedef_bridge.bindings[0].interface_type == "td_vif_t"
