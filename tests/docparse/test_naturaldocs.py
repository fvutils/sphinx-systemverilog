"""Tests for the NaturalDocs dialect (P2-TEST-1)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser
from sphinx_systemverilog.docparse.naturaldocs import parse_header

pytestmark = pytest.mark.unit


@pytest.fixture
def parse():
    return get_parser("naturaldocs").parse


@pytest.mark.parametrize(
    "line,kind,name,nodocs",
    [
        ("Class: uvm_object", "class", "uvm_object", False),
        ("Function: get_name", "function", "get_name", False),
        ("Function -- NODOCS -- new", "function", "new", True),
        ("Group -- NODOCS -- Verbosity Configuration", "group",
         "Verbosity Configuration", True),
        ("Variable - m_x", "property", "m_x", False),
        ("Task: run", "task", "run", False),
    ],
)
def test_header_variants(line, kind, name, nodocs):
    h = parse_header(line)
    assert h is not None
    assert (h.kind, h.name, h.nodocs) == (kind, name, nodocs)


def test_non_header_returns_none():
    assert parse_header("This Function does things") is None
    assert parse_header("just prose") is None


def test_banner_wrapped_header():
    raw = (
        "------------------------------------------\n"
        "\n"
        "CLASS -- NODOCS -- uvm_object\n"
        "\n"
        "The base class for all UVM objects.\n"
        "------------------------------------------"
    )
    h = parse_header(raw)
    assert h is not None and h.name == "uvm_object" and h.nodocs


def test_parse_strips_header_and_banner(parse):
    raw = (
        "----\nCLASS: my_obj\n\nThe summary line.\n\nMore detail.\n----"
    )
    d = parse(raw)
    assert d.summary == "The summary line."
    assert "More detail." in d.body
    assert "----" not in d.body


def test_inline_xref_and_code(parse):
    d = parse("Function: f\n\nReturns ~value~; see <other_fn>.")
    assert "``value``" in d.summary
    assert ":sv:obj:`other_fn`" in d.summary
    assert "other_fn" in d.xrefs


def test_stray_rst_is_escaped(parse):
    d = parse("Function: f\n\nMatches a *.txt pattern and `macro names.")
    # Stray * and ` are escaped so they do not break the RST parse.
    assert "\\*" in d.summary
    assert "\\`" in d.summary


def test_trailing_underscore_escaped_but_identifiers_preserved(parse):
    d = parse("Function: f\n\nThe rhs_ argument differs from get_name behaviour.")
    # A trailing underscore (an RST reference) is escaped...
    assert "rhs\\_" in d.summary
    # ...but an internal underscore in an identifier is left intact.
    assert "get_name" in d.summary


def test_matches_detects_dialect(parse):
    nd = get_parser("naturaldocs")
    assert nd.matches("Function: get_name\n\nDoes a thing.")
    assert not nd.matches("Just a plain comment.")
