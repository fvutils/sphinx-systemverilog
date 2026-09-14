"""End-to-end: a code sample written in a doc comment survives as a code block.

The structural repairs exist because source comments are not RST.  A literal
block is the one construct where that is false -- ``::`` plus an indented block
*is* RST, and its indentation is the whole of its meaning -- so every repair has
to leave it alone.  Getting this wrong is silent in the worst way: the code
renders as a run-on paragraph and docutils reports only "Literal block expected;
none found", which names no symbol and no file.

As in :mod:`test_lists_end_to_end`, the shape is checked against a real doctree
rather than a string, and each dialect is checked independently because they
call the repairs in different orders.
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


def _assert_renders_as_a_literal_block(body: str, *, contains: str) -> None:
    doctree = _doctree(body)
    messages = list(doctree.findall(nodes.system_message))
    assert not messages, [m.astext() for m in messages]
    blocks = list(doctree.findall(nodes.literal_block))
    assert len(blocks) == 1, doctree.pformat()
    assert contains in blocks[0].astext()


# No cross-references in the fixtures asserted against a doctree: bare docutils
# has no sv:obj role, so a stray one shows up as a system message and masks the
# thing under test.  Xref suppression inside a block is checked on the text.
DOXYGEN = """
Hosts a UVM component implemented in Python.

Set the pyclass property, and the proxy forwards each phase::

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        m_pycomp.pyclass = "pycomp::PyComp";
    endfunction

The Python class subclasses uvm_component_impl.
"""

NATURALDOCS = """
Hosts a UVM component implemented in Python.

Set the pyclass property, and the proxy forwards each phase::

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
    endfunction
"""


def test_doxygen_keeps_a_literal_block():
    parsed = get_parser("doxygen").parse(DOXYGEN)
    _assert_renders_as_a_literal_block(parsed.body, contains="super.build_phase")


def test_doxygen_keeps_the_indentation_inside_the_block():
    # The nested line is what the continuation-folder used to swallow.
    parsed = get_parser("doxygen").parse(DOXYGEN)
    block = list(_doctree(parsed.body).findall(nodes.literal_block))[0]
    lines = block.astext().splitlines()
    assert lines[0].startswith("function void")
    assert lines[1].startswith("    super.build_phase"), lines


def test_doxygen_does_not_escape_inside_the_block():
    # `*` and a trailing `_` are RST markup in prose and code in a sample.
    raw = "Example::\n\n    int *p = &x;\n    foo(bar_);\n"
    parsed = get_parser("doxygen").parse(raw)
    assert "\\*" not in parsed.body
    assert "\\_" not in parsed.body
    _assert_renders_as_a_literal_block(parsed.body, contains="int *p = &x;")


def test_doxygen_does_not_xref_inside_the_block():
    # `#foo` is a Doxygen cross-reference in prose; in a code sample it is a
    # macro, a bit-select or a comment.
    raw = "Example::\n\n    `define FOO 1\n    x = #5 y;\n"
    parsed = get_parser("doxygen").parse(raw)
    assert ":sv:obj:" not in parsed.body


def test_doxygen_handles_two_blocks_in_one_comment():
    raw = (
        "Name it as a parameter::\n\n"
        "    typedef proxy #(.PyClass(\"a\")) t;\n\n"
        "or by assignment::\n\n"
        "    seq.pyclass = \"b\";\n"
    )
    parsed = get_parser("doxygen").parse(raw)
    doctree = _doctree(parsed.body)
    assert not list(doctree.findall(nodes.system_message)), doctree.pformat()
    assert len(list(doctree.findall(nodes.literal_block))) == 2, doctree.pformat()


def test_doxygen_prose_after_a_block_is_still_prose():
    parsed = get_parser("doxygen").parse(DOXYGEN)
    doctree = _doctree(parsed.body)
    texts = [p.astext() for p in doctree.findall(nodes.paragraph)]
    assert any(t.startswith("The Python class subclasses") for t in texts), texts


def test_naturaldocs_keeps_a_literal_block():
    parsed = get_parser("naturaldocs").parse(NATURALDOCS)
    doctree = _doctree(parsed.body)
    assert not list(doctree.findall(nodes.system_message)), doctree.pformat()


def test_plain_keeps_a_literal_block():
    parsed = get_parser("plain").parse(DOXYGEN)
    _assert_renders_as_a_literal_block(parsed.body, contains="super.build_phase")
