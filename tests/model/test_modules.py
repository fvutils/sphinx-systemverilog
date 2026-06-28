"""Tests for module/interface ports and parameters (P2-TEST-3)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from tests.conftest import read_fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def counter():
    roots = ModelBuilder().build_from_text(read_fixture("counter.sv"), "counter.sv")
    return next(r for r in roots if r.name == "counter")


def _child(obj, name):
    return next((c for c in obj.children if c.name == name), None)


def test_module_kind_and_doc(counter):
    assert counter.kind == "module"
    assert counter.raw_doc.startswith("A configurable up-counter.")


def test_parameters_extracted(counter):
    width = _child(counter, "WIDTH")
    assert width is not None and width.kind == "parameter"
    assert "WIDTH = 8" in width.signature
    assert width.raw_doc == "counter width in bits"
    assert _child(counter, "MAX").kind == "parameter"


def test_ports_extracted_with_direction(counter):
    clk = _child(counter, "clk")
    assert clk.kind == "port"
    assert "input" in clk.qualifiers
    assert clk.raw_doc == "clock"
    count = _child(counter, "count")
    assert "output" in count.qualifiers
    assert "[WIDTH-1:0]" in count.signature


def test_port_leading_comment(counter):
    rst = _child(counter, "rst")
    assert rst.raw_doc == "active-high synchronous reset"


def test_interface_supported():
    code = """
    // A simple bus interface.
    interface bus_if;
      logic req;
    endinterface
    """
    roots = ModelBuilder().build_from_text(code)
    iface = next(r for r in roots if r.name == "bus_if")
    assert iface.kind == "interface"
    assert iface.raw_doc.startswith("A simple bus interface.")
