"""Tests for the Doxygen dialect (P3-TEST-1)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser, get_parser_for

pytestmark = pytest.mark.unit


@pytest.fixture
def parse():
    return get_parser("doxygen").parse


def test_brief_is_summary(parse):
    d = parse("@brief A short summary.\n\nMore detail.")
    assert d.summary == "A short summary."
    assert "More detail." in d.body


def test_param_and_return_fields(parse):
    d = parse(
        "@brief f.\n"
        "@param[in] mask bits to include\n"
        "@param width the width\n"
        "@return the parity\n"
    )
    fields = {(f.kind, f.name): f.body for f in d.fields}
    assert fields[("param", "mask")] == "bits to include"
    assert fields[("param", "width")] == "the width"
    assert ("returns", None) in fields


def test_backslash_commands(parse):
    d = parse("\\brief Backslash brief.\n\\return a value")
    assert d.summary == "Backslash brief."
    assert any(f.kind == "returns" for f in d.fields)


def test_note_and_see_fields(parse):
    d = parse("@brief f.\n@note Careful.\n@see other_thing")
    kinds = {f.kind for f in d.fields}
    assert "note" in kinds
    assert "see" in kinds
    assert "other_thing" in d.xrefs


def test_inline_code_and_ref(parse):
    d = parse("@brief Uses @p mask and #helper; see @ref other.")
    assert "``mask``" in d.summary
    assert ":sv:obj:`helper`" in d.summary
    assert ":sv:obj:`other`" in d.summary


def test_brief_less_first_paragraph_is_summary(parse):
    d = parse("Just a plain first line.\n\nThen the body.")
    assert d.summary == "Just a plain first line."
    assert "Then the body." in d.body


def test_auto_detects_doxygen():
    assert get_parser_for("auto", "@brief x").name == "doxygen"
    assert get_parser_for("auto", "@param y z").name == "doxygen"
