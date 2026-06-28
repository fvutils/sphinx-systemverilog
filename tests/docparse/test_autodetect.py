"""Tests for per-comment dialect auto-detection (P2-TEST-2)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse import get_parser_for

pytestmark = pytest.mark.unit


def test_auto_selects_naturaldocs_for_header():
    p = get_parser_for("auto", "Function: get_name\n\nReturns the name.")
    assert p.name == "naturaldocs"


def test_auto_falls_back_to_native():
    p = get_parser_for("auto", "Just a plain summary line.")
    assert p.name == "native"


def test_explicit_style_overrides_content():
    # Even ND-looking content is parsed as native when explicitly requested.
    p = get_parser_for("native", "Function: get_name")
    assert p.name == "native"


def test_unknown_style_falls_back_to_native():
    p = get_parser_for("does-not-exist", "anything")
    assert p.name == "native"
