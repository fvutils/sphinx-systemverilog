"""U6-TEST-1 (`U6-IMPL-1`): factory overrides, every way they are written.

A factory override is the one construct in UVM that makes a component tree
*lie*. `build_phase` says ``ovr_driver::type_id::create(...)``, the extraction
reads ``ovr_driver``, and the simulation builds a ``fast_driver``. Nothing in
the agent's own source hints at it.

Two things carry this phase:

* **there are five ways to write one**, across four declaring classes, and two
  of those classes declare a method with the *same name and a different
  signature*. A detector keyed on the method name reports the arguments
  swapped;
* **they are annotated, never resolved** (plan Risk 2). Every way of resolving
  one would be a claim about a run.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import OVERRIDE_INST, OVERRIDE_TYPE
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def provider():
    return uvm_stub_index("override_tb.sv").uvm_provider


@pytest.fixture
def overrides(provider):
    return provider.overrides()


def _one(overrides, original, replacement):
    return next(
        o for o in overrides.overrides
        if o.original == original and o.replacement == replacement
    )


# -- the five call shapes -----------------------------------------------------


def test_the_component_convenience_wrapper_is_read(overrides):
    """``set_type_override_by_type(a::get_type(), b::get_type())``."""
    override = _one(overrides, "ovr_driver", "fast_driver")
    assert override.kind == OVERRIDE_TYPE
    assert override.where == "ovr_test.build_phase"


def test_the_factory_singleton_is_read(overrides):
    """``f.set_type_override_by_type(...)`` — same method name as the wrapper
    above, different declaring class. Both must resolve, and the discriminator
    is the lexical path rather than the name."""
    assert _one(overrides, "ovr_item", "big_item").kind == OVERRIDE_TYPE


def test_the_by_name_form_is_read(overrides):
    """Its arguments are string literals, not types."""
    assert _one(overrides, "ovr_monitor", "noisy_moniter").kind == OVERRIDE_TYPE


def test_the_registry_form_names_its_original_nowhere(overrides):
    """``ovr_monitor::type_id::set_type_override(noisy_monitor::get_type())``
    has one argument. The type being replaced is the specialization's own
    ``Tname`` — the same parameter ``create`` is read from — so an extractor
    that only reads arguments reports this override backwards."""
    override = _one(overrides, "ovr_monitor", "noisy_monitor")
    assert override.kind == OVERRIDE_TYPE


def test_an_inst_override_keeps_its_path(overrides):
    override = _one(overrides, "ovr_driver", "fast_driver")
    inst = next(
        o for o in overrides.overrides if o.kind == OVERRIDE_INST
    )
    assert inst.inst_path == "env.agt.drv"
    assert (inst.original, inst.replacement) == ("ovr_driver", "fast_driver")
    assert override is not inst


def test_argument_positions_are_read_per_method(overrides):
    """The guard on the subtlest bug available here. UVM's own argument orders
    disagree: ``uvm_component::set_inst_override_by_type`` takes the path
    *first*, ``uvm_factory::set_inst_override_by_type`` takes it *last*. A
    single "the path is argument N" rule reports one of them with the path and
    the original type swapped — and both spellings compile.
    """
    inst = next(o for o in overrides.overrides if o.kind == OVERRIDE_INST)

    assert inst.inst_path == "env.agt.drv"
    assert inst.original == "ovr_driver", "the path must not land in `original`"


def test_a_type_name_is_recovered_from_get_type(overrides):
    """``fast_driver::get_type()``'s *lexical path* names the class the
    ``uvm_*_utils`` macro expanded ``get_type`` into. The call's return type
    would give ``fast_driver::type_id`` instead."""
    assert _one(overrides, "ovr_driver", "fast_driver").replacement == "fast_driver"


# -- honesty ------------------------------------------------------------------


def test_a_conditional_override_is_marked(overrides):
    """It sits under ``if (want_noise)`` and may not run."""
    assert _one(overrides, "ovr_monitor", "noisy_moniter").conditional is True
    assert _one(overrides, "ovr_monitor", "noisy_monitor").conditional is False


def test_a_by_name_override_naming_nothing_is_reported(overrides):
    """``set_type_override("ovr_monitor", "noisy_moniter")`` — a typo for
    ``noisy_monitor``. It compiles, elaborates and simulates; the override
    silently never applies and the testbench quietly runs the type it meant to
    replace. Nothing at run time reports it."""
    broken = overrides.broken

    assert [o.replacement for o in broken] == ["noisy_moniter"]
    assert broken[0].unknown == ("noisy_moniter",)


def test_a_type_safe_override_can_never_be_broken(overrides):
    """Which is the argument for the ``::get_type()`` forms, and worth showing
    rather than asserting: an argument naming a type that does not exist would
    not have compiled."""
    assert all(
        not o.unknown for o in overrides.overrides
        if o.replacement != "noisy_moniter"
    )


def test_overrides_are_grouped_by_the_type_they_replace(overrides):
    labels = [o.label for o in overrides.for_type("ovr_driver")]
    assert labels == ["→ fast_driver", "→ fast_driver under env.agt.drv"]


def test_a_type_with_no_override_gets_none(overrides):
    assert overrides.for_type("ovr_env") == []
    assert overrides.replaced_types == ["ovr_driver", "ovr_item", "ovr_monitor"]


def test_nothing_is_resolved(provider):
    """Risk 2, as an assertion. The tree still reports the type the ``create``
    call names; the override is carried alongside it."""
    structure = provider.get("ovr_test")
    agent = next(
        c for c in structure.children_of("ovr_agent") if c.handle == "drv"
    )
    assert agent.type_name == "ovr_driver"


# -- cost ---------------------------------------------------------------------


def test_overrides_ride_the_config_scan(provider):
    """One expression walk serves both. Descending into if-conditions is the
    hard part and it is identical either way, so a page with an annotated tree
    and a config table pays for one scan."""
    fresh = uvm_stub_index("override_tb.sv").uvm_provider
    fresh.config()
    fresh.overrides()

    assert fresh.config_walk_count == 1


def test_the_override_scan_does_not_elaborate_the_hierarchy():
    fresh = uvm_stub_index("override_tb.sv").uvm_provider
    fresh.overrides()

    assert fresh.walk_count == 0
