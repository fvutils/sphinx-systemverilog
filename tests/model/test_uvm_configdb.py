"""U2-TEST-2: `uvm_config_db` set/get extraction.

The extraction that matters most here is the one a naive walker gets wrong.
The dominant way a UVM component reads configuration is::

    if (!uvm_config_db #(int)::get(this, "", "n_items", n_items))

where the call is an `if`-**condition**, not a statement. A walker that only
inspects `ExpressionStatement` sees a `Conditional` and nothing inside it, so it
reports every such component as reading nothing at all --- and produces a
config table in which almost every setting looks orphaned. The assessment
(§8.2) flagged exactly this as an unconfirmed gap; these tests close it.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import ACTION_GET, ACTION_SET
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def index():
    return uvm_stub_index("config_tb.sv")


@pytest.fixture(scope="module")
def config(index):
    return index.uvm_provider.config()


def _find(config, action, field, owner=None):
    return next(
        a
        for a in config.accesses
        if a.action == action
        and a.field == field
        and (owner is None or a.owner == owner)
    )


def test_both_halves_are_extracted(config):
    assert len(config.sets) == 7
    assert len(config.gets) == 4


def test_a_get_inside_an_if_condition_is_found(config):
    """The idiom a statement-level walker cannot see."""
    get = _find(config, ACTION_GET, "n_items")

    assert get.owner == "cfg_driver"
    assert get.method == "build_phase"
    assert get.type_name == "int"


def test_a_get_inside_a_void_cast_is_found(config):
    get = _find(config, ACTION_GET, "mode")

    assert get.type_name == "string"
    assert get.value == "mode", "the get target is the variable being filled"


def test_the_get_target_comes_from_the_inout_assignment(config):
    """`get` returns through an `inout` argument, which slang models as an
    assignment; the variable being filled is on its left."""
    assert _find(config, ACTION_GET, "unset_depth").value == "depth"


def test_a_set_records_scope_field_and_value(config):
    st = _find(config, ACTION_SET, "n_items", owner="cfg_agent")

    assert (st.cntxt, st.scope, st.field, st.value) == ("this", "drv", "n_items", "8")
    assert st.type_name == "int"


def test_a_conditional_set_is_flagged(config):
    """A set under an `if` may not happen, and must not read as though it will."""
    assert _find(config, ACTION_SET, "n_items", owner="cfg_env").conditional is True
    assert _find(config, ACTION_SET, "n_items", owner="cfg_agent").conditional is False


def test_a_computed_field_name_is_none_not_a_guess(config):
    dynamic = config.dynamic

    assert len(dynamic) == 1
    assert dynamic[0].field is None
    assert dynamic[0].owner == "cfg_agent"


def test_a_wildcard_scope_is_reported_verbatim(config):
    assert _find(config, ACTION_SET, "mode").scope == "*"


def test_a_set_from_a_top_module_is_found(config):
    """The virtual-interface binding lives outside any class.

    A scan rooted at the test component would never reach it, which is why the
    config scan is project-wide rather than hierarchy-driven.
    """
    st = _find(config, ACTION_SET, "vif")

    assert st.owner == "cfg_tb_top"
    assert st.method == "", "a module procedural block has no method name"
    assert st.cntxt == "null"
    assert st.scope == "uvm_test_top"


def test_the_interface_instance_resolves_to_a_symbol_name(config):
    """`ArbitrarySymbol` has no syntax of its own; the name is on the symbol.

    This is the RTL-side half of the §8.2 bridge, and it is the value U5 needs
    in order to say "this agent is bound to `cfg_tb_top.u_if`".
    """
    assert _find(config, ACTION_SET, "vif").value == "u_if"


def test_the_matching_virtual_interface_get_is_extracted(config):
    """Closes the caveat §8.2 left open.

    The assessment confirmed the `set` side of the virtual-interface bridge
    end-to-end but not the `get`, because its probe's walker did not reach into
    if-conditions. With that fixed, the `get` extracts.
    """
    get = _find(config, ACTION_GET, "vif")

    assert get.owner == "cfg_test"
    assert get.type_name == "cfg_if"
    assert get.value == "vif"


def test_where_names_the_call_site(config):
    assert _find(config, ACTION_GET, "n_items").where == "cfg_driver.build_phase"
    assert _find(config, ACTION_SET, "vif").where == "cfg_tb_top"


def test_full_scope_joins_cntxt_and_inst_name(config):
    assert _find(config, ACTION_SET, "n_items", owner="cfg_agent").full_scope == (
        "this.drv"
    )
    assert _find(config, ACTION_SET, "vif").full_scope == "uvm_test_top"


def test_library_internal_accesses_are_not_reported(config):
    """The table is about the testbench, not about UVM.

    The library configures itself --- the stub's `uvm_component` reproduces
    real `set_config_object`, which calls `config_db::set`. Those accesses are
    real, and reporting them would bury the handful a reader actually wrote.
    """
    assert not any(a.owner.startswith("uvm_") for a in config.accesses)


def test_the_library_access_really_is_extractable(index):
    """...and the test above is not passing because nothing was there.

    This matters more than it looks. Against *real* UVM the same accesses are
    absent for an entirely different reason: slang does not elaborate the
    bodies of methods nothing calls, so a corpus test asserting their absence
    passed while the filter did not yet exist. Extracting the call directly
    proves the exclusion above is a rule being applied, not an accident.
    """
    from pyslang.ast import SymbolKind

    provider = index.uvm_provider
    component = next(
        c for c in provider._iter_classes() if c.name == "uvm_component"
    )
    method = next(
        m for m in component
        if getattr(m, "kind", None) == SymbolKind.Subroutine
        and m.name == "set_config_object"
    )

    from sphinx_systemverilog.model.uvm import _CallSink

    sink = _CallSink()
    provider._collect_config(
        getattr(method, "body", None), sink, "uvm_component", "set_config_object"
    )

    assert len(sink.accesses) == 1
    assert sink.accesses[0].action == ACTION_SET


def test_a_component_method_that_is_not_a_phase_is_scanned(config):
    """`connect_phase` here, but the point is the scan is not phase-filtered.

    Configuration is set from constructors and helper methods too, and a scan
    that only read `build_phase` would report those settings as absent.
    """
    assert any(
        a.method == "connect_phase" for a in config.accesses
    ), "accesses outside build_phase must still be found"
