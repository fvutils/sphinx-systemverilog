"""Tests for the shared inline-markup escaping.

The load-bearing property here is that a *leading* list marker survives
escaping: the Doxygen dialect escapes before it sanitizes, so an escaped
``\\*`` would be invisible to the list-aware folder in ``sanitize``.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse.inline import escape_rst_inline

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("marker", ["*", "-", "+", "1.", "a)", "(2)"])
def test_leading_marker_is_not_escaped(marker):
    assert escape_rst_inline(f"{marker} item") == f"{marker} item"


def test_marker_and_indent_survive_while_prose_escapes():
    assert escape_rst_inline("  * a *starred* word") == "  * a \\*starred\\* word"


def test_every_line_keeps_its_marker():
    text = "Lead in:\n\n* one *emph*\n* two\n"
    assert escape_rst_inline(text) == "Lead in:\n\n* one \\*emph\\*\n* two\n"


@pytest.mark.parametrize("line", ["*ptr", "*not a marker*", "-dash", "a.b"])
def test_non_markers_still_escape(line):
    escaped = escape_rst_inline(line)
    assert escaped == line.replace("*", "\\*")
    if "*" in line:
        assert "\\*" in escaped


def test_other_specials_are_unaffected_by_the_marker_split():
    assert escape_rst_inline("* a `tick` and a |bar| and rhs_") == (
        "* a \\`tick\\` and a \\|bar\\| and rhs\\_"
    )
    assert escape_rst_inline("a `tick`") == "a \\`tick\\`"


def test_trailing_underscore_still_escapes_after_a_marker():
    assert escape_rst_inline("- see rhs_") == "- see rhs\\_"
