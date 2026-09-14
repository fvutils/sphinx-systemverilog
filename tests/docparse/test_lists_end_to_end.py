"""End-to-end: a bullet list written in a source banner comment survives.

The three non-RST dialects call ``sanitize_prose`` and ``escape_rst_inline`` in
three different orders, so each has to be checked independently -- Doxygen in
particular escapes *before* it sanitizes.  And because asserting on strings is
how a run-on paragraph passed a green test suite once already, the shape is also
checked by handing the body to docutils and looking for a real ``bullet_list``.
"""

from __future__ import annotations

import docutils.core
import pytest
from docutils import nodes

from sphinx_systemverilog.docparse import get_parser

pytestmark = pytest.mark.unit


def _doctree(body: str):
    return docutils.core.publish_doctree(
        body,
        settings_overrides={
            "report_level": 1,
            "halt_level": 5,
            "warning_stream": False,
            "file_insertion_enabled": False,
            "_disable_config": True,
        },
    )


def _assert_renders_as_a_list(body: str, *, items: int = 2) -> None:
    doctree = _doctree(body)
    messages = list(doctree.findall(nodes.system_message))
    assert not messages, [m.astext() for m in messages]
    lists = list(doctree.findall(nodes.bullet_list))
    assert len(lists) == 1, doctree.pformat()
    assert len(lists[0].children) == items
    # The list must not be wrapped in a block quote (i.e. left indented).
    assert not list(doctree.findall(nodes.block_quote)), doctree.pformat()
    assert list(doctree.findall(nodes.paragraph))[0].astext().startswith("Composes")


def _comment(marker: str) -> str:
    return (
        "my_env -- UVM environment for the bypass sanity TB.\n"
        "\n"
        "Composes ONLY the reused verification components:\n"
        f"  {marker} four wrapped bus iUVC agents (from uvc/bus_uvc)\n"
        f"  {marker} the host memory model + responder (from memory/)\n"
    )


@pytest.mark.parametrize("dialect", ["plain", "naturaldocs", "doxygen"])
@pytest.mark.parametrize("marker", ["*", "-"])
def test_bullets_survive_every_call_ordering(dialect, marker):
    parsed = get_parser(dialect).parse(_comment(marker))
    assert parsed.body.lstrip().startswith("Composes")
    _assert_renders_as_a_list(parsed.body)


@pytest.mark.parametrize("dialect", ["plain", "naturaldocs", "doxygen"])
def test_a_list_followed_by_a_paragraph_emits_no_warning(dialect):
    raw = (
        "Summary line.\n"
        "\n"
        "Composes:\n"
        "  - one\n"
        "  - two\n"
        "Trailing paragraph.\n"
    )
    body = get_parser(dialect).parse(raw).body
    doctree = _doctree(body)
    assert not list(doctree.findall(nodes.system_message)), doctree.pformat()
    assert len(list(doctree.findall(nodes.bullet_list))) == 1
    assert doctree.astext().endswith("Trailing paragraph.")


def test_nested_list_nests_in_the_doctree():
    raw = "Summary.\n\nComposes:\n  - a\n    - a1\n  - b\nTrailing.\n"
    doctree = _doctree(get_parser("plain").parse(raw).body)
    assert not list(doctree.findall(nodes.system_message)), doctree.pformat()
    lists = list(doctree.findall(nodes.bullet_list))
    assert len(lists) == 2, doctree.pformat()
    outer, inner = lists
    assert len(outer.children) == 2
    assert inner.parent is outer.children[0]
    assert inner.astext() == "a1"


def test_native_dialect_is_left_alone():
    # RST by definition: indentation is meaningful and must pass through.
    raw = "Summary.\n\n.. note::\n\n   Indented body.\n"
    assert get_parser("native").parse(raw).body == ".. note::\n\n   Indented body."
