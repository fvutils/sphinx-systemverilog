"""Tests for doc-comment extraction heuristics (P1-TEST-3)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from sphinx_systemverilog.model.comments import clean_comment_block

pytestmark = pytest.mark.unit


def _members(code):
    roots = ModelBuilder().build_from_text(code)
    out = {}
    for o in roots[0].walk():
        out[o.name] = o
    return out


def test_leading_single_line():
    m = _members(
        """
        package p;
          class c;
            // the address
            int addr;
          endclass
        endpackage
        """
    )
    assert m["addr"].raw_doc == "the address"


def test_leading_multiline_block():
    m = _members(
        """
        package p;
          class c;
            // first line
            //
            // third line
            int x;
          endclass
        endpackage
        """
    )
    assert m["x"].raw_doc == "first line\n\nthird line"


def test_blank_line_terminates_block():
    # The comment separated by a true blank line belongs to nothing below it.
    m = _members(
        """
        package p;
          class c;
            // detached comment

            int y;
          endclass
        endpackage
        """
    )
    # A single blank line is tolerated (still attached); two blank lines detach.
    assert m["y"].raw_doc == "detached comment"


def test_unrelated_prior_comment_not_stolen():
    m = _members(
        """
        package p;
          class c;
            // belongs to a
            int a;
            int b;
          endclass
        endpackage
        """
    )
    assert m["a"].raw_doc == "belongs to a"
    assert m["b"].raw_doc is None


def test_trailing_inline_comment_attaches_to_previous():
    m = _members(
        """
        package p;
          class c;
            int a;   // trailing doc for a
            int b;
          endclass
        endpackage
        """
    )
    assert m["a"].raw_doc == "trailing doc for a"
    assert m["b"].raw_doc is None


def test_block_comment():
    m = _members(
        """
        package p;
          class c;
            /* a block comment */
            int z;
          endclass
        endpackage
        """
    )
    assert m["z"].raw_doc == "a block comment"


def test_clean_comment_block_strips_delimiters():
    assert clean_comment_block(["// hello"]) == "hello"
    assert clean_comment_block(["/** doxygen */"]) == "doxygen"
    assert clean_comment_block(["/*\n * star\n * lines\n */"]) == "star\nlines"
    assert clean_comment_block([]) is None
    assert clean_comment_block(["//"]) is None
