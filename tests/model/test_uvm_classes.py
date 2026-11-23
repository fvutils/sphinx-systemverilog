"""Per-class extraction for every component class (stitching plan A3).

:meth:`UvmProvider.classes` is what a database records for the stitcher: one
entry per non-library component class, whether a root reaches it or not, each
holding only what the class itself writes.
"""

from __future__ import annotations

import pytest

from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def stitch():
    return uvm_stub_index("stitch_tb.sv").uvm_provider.classes()


@pytest.fixture(scope="module")
def dup():
    return uvm_stub_index("dup_names_tb.sv").uvm_provider.classes()


def test_every_component_class_is_present(stitch):
    names = {t.name for t in stitch.types.values()}
    # unreachable from any root, overridden-in only, abstract: all present
    assert {"fast_drv", "mon_c", "big_agent", "inh_env", "nosup_env", "abs_comp"} <= names


def test_non_components_and_library_classes_are_absent(stitch):
    names = {t.name for t in stitch.types.values()}
    assert not names & {"st_item", "st_cfg"}
    assert not any(n.startswith("uvm_") for n in names)


def test_keys_are_qualified_names(stitch):
    assert "stitch_tb_pkg::st_agent" in stitch.types
    assert stitch.types["stitch_tb_pkg::st_agent"].key == "stitch_tb_pkg::st_agent"


def test_nothing_is_merged_from_bases(stitch):
    """``inh_env`` writes nothing itself; ``sup_env`` only ``agt_b``."""
    assert stitch.children["stitch_tb_pkg::inh_env"] == []
    assert [c.handle for c in stitch.children["stitch_tb_pkg::sup_env"]] == ["agt_b"]


def test_helper_creates_and_connections_are_included(stitch):
    kids = {c.handle: c.method for c in stitch.children["stitch_tb_pkg::helper_env"]}
    assert kids == {"agts": "build_agents", "scb": "build_scb", "rec": "build_phase"}
    conns = {c.method for c in stitch.connections["stitch_tb_pkg::helper_env"]}
    assert conns == {"connect_phase", "connect_agents"}


def test_child_types_carry_their_key(stitch):
    kid = stitch.children["stitch_tb_pkg::st_agent"][0]
    assert (kid.type_name, kid.type_key) == ("st_mon", "stitch_tb_pkg::st_mon")


def test_same_named_classes_in_two_packages_stay_apart(dup):
    assert [c.handle for c in dup.children["dup_a_pkg::agent"]] == ["drv"]
    assert [c.handle for c in dup.children["dup_b_pkg::agent"]] == ["mon"]


def test_a_qualified_create_resolves_to_its_package(dup):
    kids = {c.handle: c.type_key for c in dup.children["dup_b_pkg::env"]}
    assert kids == {"a": "dup_a_pkg::agent", "b": "dup_b_pkg::agent"}


def test_memoized():
    provider = uvm_stub_index("stitch_tb.sv").uvm_provider
    assert provider.classes() is provider.classes()
