"""Tests for the structural prose repairs shared by the non-RST dialects."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.docparse.sanitize import (
    sanitize_prose,
    strip_rules,
    unwrap_continuations,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "line",
    [
        "----------------------------------------",
        "  ====================",
        "* * * * *",
        "^^^^^^^^^^^^",
        "////////////////",
        "~~~~~~~~",
    ],
)
def test_strip_rules_drops_banner_lines(line):
    assert strip_rules(f"Before\n{line}\nAfter") == "Before\nAfter"


@pytest.mark.parametrize(
    "line",
    ["-- not a rule, it has words", "a - b", "..."],
)
def test_strip_rules_keeps_content(line):
    assert strip_rules(line) == line


def test_unwrap_folds_aligned_continuations():
    # The construct docutils rejects: a term with its wrapped text aligned
    # under the description rather than under the term.
    text = (
        "UVM_PRE_START  - The sequence is started and the\n"
        "                 pre_start() task is being executed.\n"
        "UVM_STARTED    - The sequence is running.\n"
    )
    assert unwrap_continuations(text).splitlines() == [
        "UVM_PRE_START  - The sequence is started and the "
        "pre_start() task is being executed.",
        "UVM_STARTED    - The sequence is running.",
    ]


def test_unwrap_preserves_list_items():
    # docutils needs the blank line to see a list at all: without it the whole
    # thing is one run-on paragraph.
    text = "An error is asserted if-\n- opened twice\n- closed first\n"
    assert unwrap_continuations(text).splitlines() == [
        "An error is asserted if-",
        "",
        "- opened twice",
        "- closed first",
    ]


@pytest.mark.parametrize("marker", ["*", "-", "+"])
def test_unwrap_preserves_indented_bullets_under_a_lead_in(marker):
    # The common banner-comment shape: lead-in at indent 0, bullets indented
    # under it.  An indent-relative rule alone folds the whole list into the
    # lead-in; the marker has to win.
    text = (
        "Composes the reused components:\n"
        f"  {marker} four SDP agents\n"
        f"  {marker} the host memory model\n"
    )
    assert unwrap_continuations(text).splitlines() == [
        "Composes the reused components:",
        "",
        f"{marker} four SDP agents",
        f"{marker} the host memory model",
    ]


def test_unwrap_folds_wrapped_indented_item_into_its_own_item():
    # The continuation belongs to the bullet above it, not to the lead-in.
    text = (
        "Composes:\n"
        "  * an item whose text\n"
        "    wraps to a second line\n"
        "  * another item\n"
    )
    assert unwrap_continuations(text).splitlines() == [
        "Composes:",
        "",
        "* an item whose text wraps to a second line",
        "* another item",
    ]


def test_unwrap_adds_a_blank_line_after_a_list_run():
    # Without it docutils warns "Bullet list ends without a blank line".
    text = "- one\n- two\nTrailing paragraph.\n"
    assert unwrap_continuations(text).splitlines() == [
        "- one",
        "- two",
        "",
        "Trailing paragraph.",
    ]


def test_unwrap_keeps_nesting_and_separates_levels():
    text = "Lead in:\n  - a\n    - a1\n  - b\n"
    assert unwrap_continuations(text).splitlines() == [
        "Lead in:",
        "",
        "- a",
        "",
        "  - a1",
        "",
        "- b",
    ]


@pytest.mark.parametrize(
    "markers",
    [("1.", "2."), ("a)", "b)"), ("(1)", "(2)")],
)
def test_unwrap_handles_enumerated_lists(markers):
    first, second = markers
    text = f"Steps:\n  {first} do this\n  {second} then this\n"
    assert unwrap_continuations(text).splitlines() == [
        "Steps:",
        "",
        f"{first} do this",
        f"{second} then this",
    ]


@pytest.mark.parametrize(
    "line",
    ["*ptr = 5 assigns through the pointer", "- ", "-", "x-y interleaving"],
)
def test_unwrap_does_not_treat_non_markers_as_list_items(line):
    # These must keep folding like ordinary prose: a new logical line only
    # because they sit at the block indent, never because of a marker.
    text = f"Lead in:\n   {line}\n"
    assert unwrap_continuations(text).splitlines() == [f"Lead in: {line.strip()}"]


def test_unwrap_folds_wrapped_list_items():
    text = "- an item whose text\n  wraps to a second line\n- another item\n"
    assert unwrap_continuations(text).splitlines() == [
        "- an item whose text wraps to a second line",
        "- another item",
    ]


def test_unwrap_dedents_a_uniformly_indented_block():
    # Uniform indentation would parse as a block quote inside a directive body.
    assert unwrap_continuations("    indented\n    prose\n").splitlines() == [
        "indented",
        "prose",
    ]


def test_blocks_are_independent():
    text = "First\n   folded\n\nSecond\n   folded\n"
    assert sanitize_prose(text).splitlines() == [
        "First folded",
        "",
        "Second folded",
    ]
