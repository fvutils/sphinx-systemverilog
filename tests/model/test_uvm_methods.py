"""Per-class partial elaboration: the method table and call steps (plan A2).

The stitcher replays a class's functions in the order they run, so every
create, connection, override and followable helper call carries the function
it is written in and its position (``step``) among that function's calls.
These tests pin down what the producer records; the stitcher's use of it is
tested over hand-written records in ``tests/svdb/test_uvm_tree.py``.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import (BUILD_PHASE, PATH_BASE_ABSOLUTE, PATH_BASE_OWNER, UvmCall,
                                            _syntax_calls)
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def provider():
    return uvm_stub_index("stitch_tb.sv").uvm_provider


@pytest.fixture(scope="module")
def classes(provider):
    return provider._class_index()


def _type(provider, classes, name):
    return provider._describe(name, classes[name])


def _sites(provider, classes, name):
    return provider._creation_sites(classes[name])


def _conns(provider, classes, name):
    return provider._connections_of(name, classes[name])


def _override(provider, owner, replacement):
    return next(o for o in provider.overrides().overrides
                if o.owner == owner and o.replacement == replacement)


# -- the method table ------------------------------------------------------------


def test_every_own_function_is_listed(provider, classes):
    t = _type(provider, classes, "helper_env")
    assert [m.name for m in t.methods] == [
        "new", "build_phase", "build_agents", "build_scb", "connect_phase", "connect_agents"]


def test_an_inherited_function_is_absent(provider, classes):
    """``inh_env`` defines neither phase: a missing key means inherited."""
    t = _type(provider, classes, "inh_env")
    assert t.method("build_phase") is None
    assert t.method("connect_phase") is None
    assert t.method("new") is not None


def test_registration_macro_functions_are_not_listed(provider, classes):
    names = {m.name for m in _type(provider, classes, "st_agent").methods}
    assert not names & {"get_type", "get_type_name", "create"}


def test_builtin_methods_are_not_listed(provider, classes):
    names = {m.name for m in _type(provider, classes, "st_agent").methods}
    assert "randomize" not in names


def test_virtual_includes_implicit_overrides(provider, classes):
    """``late_test::set_overrides`` is not virtual anywhere; a phase is
    virtual because ``uvm_component`` declares it so."""
    t = _type(provider, classes, "late_test")
    assert t.method("set_overrides").virtual is False
    assert t.method("build_phase").virtual is True
    assert _type(provider, classes, "st_test").method("set_overrides").virtual is True


def test_a_helper_call_is_recorded_with_its_step(provider, classes):
    calls = _type(provider, classes, "st_test").method(BUILD_PHASE).calls
    assert calls == (UvmCall(step=2, method="set_overrides"),)


def test_a_conditional_helper_call(provider, classes):
    calls = _type(provider, classes, "helper_env").method(BUILD_PHASE).calls
    assert [(c.method, c.conditional) for c in calls] == [("build_agents", False), ("build_scb", True)]


def test_super_calls_are_marked(provider, classes):
    t = _type(provider, classes, "sup_env")
    assert t.method(BUILD_PHASE).calls == (UvmCall(step=0, method=BUILD_PHASE, super=True),)
    assert t.method("new").calls == (UvmCall(step=0, method="new", super=True),)
    derived = _type(provider, classes, "derived_test").method("set_overrides")
    assert derived.calls == (UvmCall(step=0, method="set_overrides", super=True),)


def test_library_calls_are_not_followable(provider, classes):
    """``super.build_phase`` into ``uvm_test`` and the override calls go to
    the library: nothing for the stitcher to follow."""
    st_test = _type(provider, classes, "st_test")
    assert all(c.method != "set_type_override_by_type" for c in st_test.method(BUILD_PHASE).calls)
    assert all(not c.super for c in st_test.method(BUILD_PHASE).calls)


def test_calls_through_another_object_are_not_followable(provider, classes):
    calls = _type(provider, classes, "st_test").method(BUILD_PHASE).calls
    assert "apply_overrides" not in {c.method for c in calls}


def test_recursive_helpers_are_recorded_as_written(provider, classes):
    t = _type(provider, classes, "rec_comp")
    assert [c.method for c in t.method("rec_a").calls] == ["rec_b"]
    assert [c.method for c in t.method("rec_b").calls] == ["rec_a"]
    assert t.method("rec_a").calls[0].conditional


def test_abstract(provider, classes):
    assert _type(provider, classes, "abs_comp").abstract
    assert not _type(provider, classes, "base_env").abstract


# -- creates and connections in every function ------------------------------------


def test_creates_in_helpers_carry_their_method(provider, classes):
    sites = {s.handle: s for s in _sites(provider, classes, "helper_env")}
    assert (sites["agts"].method, sites["agts"].step, sites["agts"].multiplicity) == ("build_agents", 1, "N")
    assert (sites["scb"].method, sites["scb"].step) == ("build_scb", 0)
    assert (sites["rec"].method, sites["rec"].step) == (BUILD_PHASE, 2)


def test_create_steps_follow_the_calls_before_them(provider, classes):
    """``st_test::build_phase``: ``uvm_factory::get()`` (0), ``super.build_phase``
    (1), ``set_overrides()`` (2), ``cfg = ...create`` (3),
    ``cfg.apply_overrides()`` (4), ``env = ...create`` (5)."""
    sites = {s.handle: s for s in _sites(provider, classes, "st_test")}
    assert sites["env"].step == 5
    assert sites["a_cfg"].step < sites["b_agent"].step


def test_the_sphinx_tree_follows_helpers(provider, classes):
    """Plan A4: the walk's children are what build_phase reaches."""
    kids = {c.handle: c for c in provider._children_of(classes["helper_env"])}
    assert set(kids) == {"agts", "scb", "rec"}
    assert kids["scb"].conditional and not kids["rec"].conditional
    assert kids["agts"].multiplicity == "N"


def test_the_sphinx_tree_follows_inherited_phases(provider, classes):
    assert [c.handle for c in provider._children_of(classes["inh_env"])] == ["agt_a", "scb"]
    assert [c.handle for c in provider._children_of(classes["sup_env"])] == ["agt_a", "scb", "agt_b"]
    assert [c.handle for c in provider._children_of(classes["nosup_env"])] == ["agt_b"]


def test_the_sphinx_connections_follow_inherited_phases_and_helpers(provider, classes):
    sup = provider._effective_connections("sup_env", classes["sup_env"])
    assert [c.source.text for c in sup] == ["agt_a.mon.ap", "agt_b.mon.ap", "agt_b.drv.seq_item_port"]
    assert all(c.owner == "sup_env" for c in sup)
    inh = provider._effective_connections("inh_env", classes["inh_env"])
    assert [c.source.text for c in inh] == ["agt_a.mon.ap"]
    helper = provider._effective_connections("helper_env", classes["helper_env"])
    assert [c.source.text for c in helper] == ["agts[i].mon.ap", "ghost.mon.ap"]


def test_recursive_helpers_terminate(provider, classes):
    assert provider._children_of(classes["rec_comp"]) == []


def test_connections_in_helpers_carry_their_method(provider, classes):
    conns = _conns(provider, classes, "helper_env")
    by_method = {c.method: c for c in conns}
    assert by_method["connect_agents"].source.path == ("agts[i]", "mon")
    assert by_method["connect_agents"].step == 0
    assert by_method["connect_phase"].source.path == ("ghost", "mon")


def test_connection_steps(provider, classes):
    conns = _conns(provider, classes, "sup_env")
    assert [(c.method, c.step) for c in conns] == [("connect_phase", 1), ("connect_phase", 2)]


# -- overrides -----------------------------------------------------------------------


def test_override_steps_are_numbered_in_their_method(provider):
    assert _override(provider, "st_test", "fast_drv").method == "set_overrides"
    assert _override(provider, "st_test", "fast_drv").step == 2
    assert _override(provider, "sup_env", "big_scb").method == "new"


def test_overrides_outside_a_class_have_no_step(provider):
    assert _override(provider, "st_tb_top", "top_seqr").step is None


def test_replace_zero_is_read(provider):
    assert _override(provider, "a_cfg_comp", "big_seqr").replace is False
    assert _override(provider, "st_test", "fast_drv").replace is True


def test_path_base(provider):
    assert _override(provider, "st_test", "slow_drv").path_base == PATH_BASE_OWNER
    assert _override(provider, "st_test", "mon_x").path_base == PATH_BASE_ABSOLUTE
    # the registry form with `parent` = this
    assert _override(provider, "late_test", "mon_c").path_base == PATH_BASE_OWNER
    assert _override(provider, "st_test", "mon_b").path_base == ""


# -- the syntax enumeration ----------------------------------------------------------


def test_steps_are_in_evaluation_order(provider, classes):
    """A call's arguments run before it, so they are numbered before it."""
    member = next(m for m in classes["sup_env"] if getattr(m, "name", "") == "new")
    calls = _syntax_calls(member.syntax)
    assert [c.name for c in calls] == ["new", "get_type", "get_type", "set_type_override_by_type"]
    assert calls[0].receiver == "super"


def test_the_invalid_body_fallback_gets_steps():
    """When slang invalidates the whole body, creates come from syntax and
    are numbered by the same enumeration."""
    provider = uvm_stub_index("missing_dep_tb.sv").uvm_provider
    sites = {s.handle: s for s in provider._creation_sites(provider._class_index()["reg_env"])}
    assert (sites["agt"].method, sites["agt"].step) == (BUILD_PHASE, 0)
