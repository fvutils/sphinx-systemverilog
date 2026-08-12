"""Tests for per-comment dialect auto-detection (P2-TEST-2)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser_for

pytestmark = pytest.mark.unit


def test_auto_selects_naturaldocs_for_header():
    p = get_parser_for("auto", "Function: get_name\n\nReturns the name.")
    assert p.name == "naturaldocs"


def test_auto_selects_native_for_rst_signals():
    # A comment that was authored as RST keeps the pass-through parser.
    for raw in (
        "Drive one item.\n\n:param addr: the address\n",
        "Returns the ``name`` field.",
        "See :sv:obj:`uvm_object`.",
        "Example::\n\n    do_thing();\n",
    ):
        assert get_parser_for("auto", raw).name == "native", raw


def test_auto_falls_back_to_plain_for_unmarked_prose():
    # Prose with no dialect marker and no RST signal is not RST: passing it
    # through as RST is what turns a banner comment into a build warning.
    p = get_parser_for("auto", "Just a plain summary line.")
    assert p.name == "plain"


def test_plain_neutralizes_prose_that_is_not_rst():
    doc = get_parser_for("auto", "*** Do not call directly ***\n").parse(
        "*** Do not call directly ***\n"
    )
    assert "\\*" in doc.summary          # escaped, not emphasis
    assert "Do not call directly" in doc.summary


def test_explicit_style_overrides_content():
    # Even ND-looking content is parsed as native when explicitly requested.
    p = get_parser_for("native", "Function: get_name")
    assert p.name == "native"


def test_unknown_style_falls_back_to_native():
    p = get_parser_for("does-not-exist", "anything")
    assert p.name == "native"
