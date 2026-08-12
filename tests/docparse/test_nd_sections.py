"""NaturalDocs ``Parameters:``/``Returns:`` sections -> structured fields."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser

pytestmark = pytest.mark.unit

ND = get_parser("naturaldocs")


def _fields(raw):
    return [(f.kind, f.name, f.body) for f in ND.parse(raw).fields]


def test_parameters_section_becomes_param_fields():
    doc = (
        "Function: m_do_open\n"
        "\n"
        "Initializes the state of the stream\n"
        "\n"
        "Parameters:\n"
        "db - Database which the stream belongs to\n"
        "scope - Optional scope\n"
    )
    assert _fields(doc) == [
        ("param", "db", "Database which the stream belongs to"),
        ("param", "scope", "Optional scope"),
    ]
    assert "Initializes the state of the stream" in ND.parse(doc).summary


@pytest.mark.parametrize(
    "header",
    [
        "Parameters:",
        "Parameters-",
        "Parameters -",
        "Parameters -- NODOCS --",
        "Parameters --NODOCS--",
        "Arguments:",
    ],
)
def test_section_header_spellings(header):
    # All four spellings occur in the UVM sources.
    assert _fields(f"Function: f\n\nDoes a thing.\n\n{header}\nname - Instance name\n") == [
        ("param", "name", "Instance name")
    ]


def test_returns_and_see_sections():
    doc = (
        "Function: get_name\n"
        "\n"
        "Gets the name.\n"
        "\n"
        "Returns:\n"
        "The name of the object.\n"
        "\n"
        "See Also:\n"
        "set_name\n"
    )
    assert _fields(doc) == [
        ("returns", None, "The name of the object."),
        ("see", None, "set_name"),
    ]


def test_section_text_is_removed_from_the_body():
    doc = (
        "Function: f\n\nSummary line.\n\nMore prose.\n\n"
        "Parameters:\nname - Instance name\n"
    )
    parsed = ND.parse(doc)
    assert "More prose." in parsed.body
    assert "Instance name" not in parsed.body


def test_prose_that_only_looks_like_a_section_is_left_alone():
    # 'Returns the name...' is a sentence, not a section header: UVM writes 236
    # of these and none of them is a Returns: section.
    doc = "Function: get_name\n\nReturns the name of the object.\n"
    assert _fields(doc) == []
    assert ND.parse(doc).summary == "Returns the name of the object."


def test_unparseable_entries_stay_as_prose():
    doc = "Function: f\n\nSummary.\n\nParameters:\njust some prose here\n"
    parsed = ND.parse(doc)
    assert parsed.fields == []
    assert "just some prose here" in parsed.body


def test_inline_markup_survives_into_a_field():
    doc = (
        "Function: m_do_open\n\nOpens it.\n\n"
        "Parameters:\ndb - Database, see <uvm_tr_database>\n"
    )
    assert _fields(doc) == [
        ("param", "db", "Database, see :sv:obj:`uvm_tr_database`")
    ]
