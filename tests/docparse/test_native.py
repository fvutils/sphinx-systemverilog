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


def test_role_at_line_start_is_not_a_field(parse):
    # A wrapped sentence can put a role first on a line; it is prose.
    d = parse("A bundle type is written with the API, so its\n"
              ":sv:func:`build` has a body::\n\n    code;")
    assert d.fields == []
    assert d.summary.endswith(":sv:func:`build` has a body::")
    assert d.body == "    code;"


def test_role_at_line_start_in_body(parse):
    d = parse("Summary.\n\nSee the\n:sv:class:`thing` class.\n\n:param x: the x")
    assert [(f.kind, f.name) for f in d.fields] == [("param", "x")]
    assert d.body == "See the\n:sv:class:`thing` class."


def test_field_inside_literal_block_is_code(parse):
    d = parse("Summary::\n\n    :param x: not a field\n\n:param y: a field")
    assert [f.name for f in d.fields] == ["y"]
    assert ":param x: not a field" in d.body


def test_field_continuation_lines(parse):
    d = parse("Summary.\n\n"
              ":param T: the value type: a packed type (a vector,\n"
              "    packed struct or enum)\n"
              ":returns: the\n"
              "   result")
    assert [(f.kind, f.name, f.body) for f in d.fields] == [
        ("param", "T", "the value type: a packed type (a vector,\npacked struct or enum)"),
        ("returns", None, "the\nresult"),
    ]
    assert d.body == ""
    rst = d.as_rst()
    assert ":param T: the value type: a packed type (a vector," in rst
    assert "   packed struct or enum)" in rst


def test_field_continuation_keeps_relative_indent(parse):
    d = parse(":param x: one of:\n\n    - a\n    - b\n\n      nested\n\nTrailing body.")
    assert d.fields[0].body == "one of:\n\n- a\n- b\n\n  nested"
    assert d.body == "Trailing body."
