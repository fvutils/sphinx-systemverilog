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


# -- Real-world header handling ------------------------------------------------
#
# Every case below was found by running the extension over CVA6.  Fixtures had
# no license headers and no `include directives, so none of this was visible.


def _module_doc(code: str, name: str = "m") -> str | None:
    for obj in ModelBuilder().build_from_text(code):
        if obj.name == name:
            return obj.raw_doc
    return None


LICENSE = """\
// Copyright 2018 ETH Zurich and University of Bologna.
// Copyright and related rights are licensed under the Solderpad Hardware
// License, Version 0.51 (the "License"); you may not use this file except in
// compliance with the License.  You may obtain a copy of the License at
// http://solderpad.org/licenses/SHL-0.51. Unless required by applicable law
// or agreed to in writing, software, hardware and materials distributed under
// this License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied.
"""


def test_license_header_is_not_documentation():
    """A license contiguous with the description must not become the doc.

    Almost every real HDL file opens this way, so without stripping, every
    module in a licensed codebase is documented as "Copyright 2018 ...".
    """
    doc = _module_doc(LICENSE + "//\n// Description: Does the thing\nmodule m; endmodule")

    assert doc is not None
    assert "Copyright" not in doc
    assert "Description: Does the thing" in doc


def test_license_only_header_leaves_module_undocumented():
    """Not "documented by its license" -- undocumented, which is the truth."""
    assert _module_doc(LICENSE + "module m; endmodule") is None


def test_description_mentioning_a_license_is_kept():
    """The strip is a leading run only; it must not eat real prose."""
    doc = _module_doc("// Checks the Copyright field of a header\nmodule m; endmodule")

    assert doc == "Checks the Copyright field of a header"


def test_first_line_of_file_is_leading_doc_not_a_trailing_comment():
    """There is no previous declaration for line 1 to be a trailing comment of."""
    doc = _module_doc("// First line.\n// Second line.\nmodule m; endmodule")

    assert doc == "First line.\nSecond line."


def test_comment_after_a_directive_is_not_adopted():
    """After include expansion, adjacent text can belong to the included file.

    CVA6's top-level module sits below two ``\\`include`` lines and was being
    documented with the closing comment of an include guard.
    """
    doc = _module_doc(
        "// Real description of m.\n"
        "\n"
        "`define SOMETHING 1\n"
        "// TAIL_OF_INCLUDED_FILE\n"
        "\n"
        "\n"
        "module m; endmodule"
    )

    assert doc != "TAIL_OF_INCLUDED_FILE"


def test_adjacent_comment_still_wins_after_a_directive():
    """The rule tightens only for *detached* comments, not adjacent ones."""
    doc = _module_doc(
        "`define SOMETHING 1\n"
        "// Documentation for m.\n"
        "module m; endmodule"
    )

    assert doc == "Documentation for m."
