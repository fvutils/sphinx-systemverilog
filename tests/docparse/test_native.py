"""Tests for the native doc-comment dialect (P1-TEST-5)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser

pytestmark = pytest.mark.unit


@pytest.fixture
def parse():
    return get_parser("native").parse


def test_summary_only(parse):
    d = parse("Just a summary.")
    assert d.summary == "Just a summary."
    assert d.body == ""
    assert d.fields == []


def test_multiline_summary_joined(parse):
    d = parse("a summary that\nwraps two lines")
    assert d.summary == "a summary that wraps two lines"


def test_summary_and_body(parse):
    d = parse("Summary.\n\nMore detail here.\nSecond body line.")
    assert d.summary == "Summary."
    assert d.body == "More detail here.\nSecond body line."


def test_param_and_returns(parse):
    d = parse(
        "Compute parity.\n\n"
        ":param mask: bits to include\n"
        ":returns: the parity bit\n"
    )
    kinds = [(f.kind, f.name, f.body) for f in d.fields]
    assert ("param", "mask", "bits to include") in kinds
    assert ("returns", None, "the parity bit") in kinds


def test_return_normalized_to_returns(parse):
    d = parse(":return: a value")
    assert d.fields[0].kind == "returns"


def test_empty(parse):
    d = parse("")
    assert d.is_empty
    d2 = parse("   \n  \n")
    assert d2.is_empty


def test_xref_tokens_collected(parse):
    d = parse("See :sv:class:`other_pkg::thing` for details.")
    assert "other_pkg::thing" in d.xrefs


def test_as_rst_roundtrip(parse):
    d = parse("Summary.\n\nBody.\n\n:param x: the x")
    rst = "\n".join(d.as_rst())
    assert "Summary." in rst
    assert ":param x: the x" in rst
