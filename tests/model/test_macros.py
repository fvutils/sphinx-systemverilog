"""Tests for `\\`define` macro extraction (P4-TEST-1)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from tests.conftest import FIXTURES

pytestmark = pytest.mark.unit


@pytest.fixture
def macros():
    builder = ModelBuilder()
    roots = builder.build_from_files([str(FIXTURES / "macros.svh")])
    return {o.name: o for o in roots if o.kind == "macro"}


def test_simple_macro(macros):
    m = macros["SAMPLE_WIDTH"]
    assert m.kind == "macro"
    assert m.signature == "`define SAMPLE_WIDTH 32"
    assert m.raw_doc == "Width of the sample bus in bits."


def test_function_macro_with_args(macros):
    m = macros["SAMPLE_MK"]
    assert "SAMPLE_MK(T, name)" in m.signature
    assert m.raw_doc == "Declare and construct a typed object."


def test_undocumented_macro(macros):
    m = macros["SAMPLE_UNDOCUMENTED"]
    assert m.raw_doc is None


def test_macros_can_be_disabled():
    builder = ModelBuilder(document_macros=False)
    roots = builder.build_from_files([str(FIXTURES / "macros.svh")])
    assert not [o for o in roots if o.kind == "macro"]
