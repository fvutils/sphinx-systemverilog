"""Slow smoke test over the full UVM source corpus (P2-TEST-7).

Run with ``pytest -m corpus``.  Skipped automatically if the UVM sources are
not present (they are fetched by ivpm into ``packages/uvm``).
"""

from __future__ import annotations

import os

import pytest

from tests.conftest import UVM_SRC, requires_uvm

pytestmark = pytest.mark.corpus

_UVM_SRC = str(UVM_SRC)
_UVM_PKG = os.path.join(_UVM_SRC, "uvm_pkg.sv")


@pytest.fixture(scope="module")
def uvm_index():
    from sphinx_systemverilog.model.index import build_index

    return build_index(
        source_dirs=[_UVM_SRC],
        build_units=[_UVM_PKG],
        include_dirs=[_UVM_SRC],
        doc_style="naturaldocs",
    )


@requires_uvm
def test_uvm_parses_without_crashing(uvm_index):
    # A floor on object count guards against silent regressions in elaboration.
    assert len(uvm_index) > 1000


@requires_uvm
@pytest.mark.parametrize(
    "name,base",
    [
        ("uvm_object", "uvm_void"),
        ("uvm_component", "uvm_report_object"),
        ("uvm_sequence_item", "uvm_transaction"),
    ],
)
def test_key_classes_present(uvm_index, name, base):
    obj = uvm_index.get(name)
    assert obj is not None, f"{name} missing"
    assert obj.kind == "class"
    assert obj.extends == base


@requires_uvm
def test_uvm_object_has_documented_members(uvm_index):
    from sphinx_systemverilog.docparse import get_parser

    obj = uvm_index.get("uvm_object")
    methods = [c for c in obj.children if c.kind in ("function", "task")]
    assert len(methods) >= 10

    nd = get_parser("naturaldocs")
    get_name = next((c for c in obj.children if c.name == "get_name"), None)
    assert get_name is not None
    assert nd.parse(get_name.raw_doc).summary  # non-empty prose


@requires_uvm
def test_groups_assigned(uvm_index):
    obj = uvm_index.get("uvm_object")
    groups = {c.group for c in obj.children if c.group}
    assert "Seeding" in groups
    assert "Identification" in groups


@requires_uvm
def test_a_class_library_pays_nothing_for_structure(uvm_index):
    """M2-TEST-7 (adapted): the lazy-elaboration contract at corpus scale.

    UVM is ~5700 objects and the largest thing this project indexes, so it is
    the right place to prove that a project with no structural directive is
    never charged for the hierarchy walk.

    The plan called for an instance-tree corpus test over "a real design
    corpus".  There isn't one: UVM is a class library with no module hierarchy
    at all, so a structural assertion over it would assert nothing.  The
    valuable claim about UVM is the negative one below.
    """
    provider = uvm_index.structure_provider
    assert provider is not None
    assert provider.computed is False


@requires_uvm
def test_uvm_has_no_instance_hierarchy_to_walk(uvm_index):
    """And when something does ask, the answer is honestly empty, not a crash."""
    structure = uvm_index.structure

    assert structure is not None
    assert structure.tops == []
    assert structure.edges == {}
    assert structure.truncated is False
