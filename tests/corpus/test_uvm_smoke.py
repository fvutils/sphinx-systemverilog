"""Slow smoke test over the full UVM source corpus (P2-TEST-7).

Run with ``pytest -m corpus``.  Skipped automatically if the UVM sources are
not present (they are fetched by ivpm into ``packages/uvm``).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.corpus

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UVM_SRC = os.path.join(_REPO, "packages", "uvm", "src")
_UVM_PKG = os.path.join(_UVM_SRC, "uvm_pkg.sv")

requires_uvm = pytest.mark.skipif(
    not os.path.isfile(_UVM_PKG), reason="UVM sources not present"
)


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
