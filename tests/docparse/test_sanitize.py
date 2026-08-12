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
    text = "An error is asserted if-\n- opened twice\n- closed first\n"
    assert unwrap_continuations(text).splitlines() == [
        "An error is asserted if-",
        "- opened twice",
        "- closed first",
    ]


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
