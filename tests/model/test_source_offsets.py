"""Signature text after a multi-byte character in the source.

slang's offsets count bytes; pyslang hands back the source decoded. Slicing
the decoded text by them shifted every later signature by the number of
extra bytes before it (``nput wire clock,`` for ``input wire clock``).
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit

CODE = """\
// Section §3.1, and § again: two characters of two bytes each.
interface ia (
        input  wire       clock,
        output reg  [7:0] d
    );
endinterface
// → a three-byte character, before a second interface
interface ib (
        input  wire       clock,
        output reg  [7:0] d
    );
endinterface
"""


def _ports(name):
    roots = ModelBuilder().build_from_text(CODE, "offsets.sv")
    obj = next(r for r in roots if r.name == name)
    return {c.name: c.signature for c in obj.children if c.kind == "port"}


@pytest.mark.parametrize("name", ["ia", "ib"])
def test_port_signatures_after_multibyte_comment(name):
    ports = _ports(name)
    assert ports["clock"] == "input wire clock"
    assert ports["d"] == "output reg [7:0] d"
