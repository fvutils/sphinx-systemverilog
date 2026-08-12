"""Signature detail carried from source into the model.

Covers three things the model used to drop: default argument values, and the
SV declaration order of unpacked dimensions on both arguments and properties.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from sphinx_systemverilog.model.builder import _split_unpacked

pytestmark = pytest.mark.unit


SRC = """
package sig_pkg;

  class sig_cls;
    int m_q[$];
    byte m_dyn[];
    int m_assoc[string];
    logic [7:0] m_packed;
    int m_plain;

    virtual function int f_defaults(int a, int b = 3, string s = "hi");
      return a;
    endfunction

    static function int f_dims(int q[$], byte d[], bit fx[0:3], int assoc[string]);
      return 0;
    endfunction

    virtual task t_default(int cycles = 10);
    endtask

    function void f_void();
    endfunction
  endclass

endpackage
"""


@pytest.fixture
def roots():
    return ModelBuilder().build_from_text(SRC, "sig_pkg.sv")


def _find(roots, name):
    for root in roots:
        for o in root.walk():
            if o.name == name:
                return o
    return None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("int$[$]", ("int", "[$]")),          # queue
        ("byte$[]", ("byte", "[]")),          # dynamic array
        ("bit$[0:3]", ("bit", "[0:3]")),      # fixed unpacked
        ("int$[string]", ("int", "[string]")),  # associative
        ("int$[3]$[4]", ("int", "[3][4]")),   # multi-dimensional
        ("logic[7:0]", ("logic[7:0]", "")),   # packed: already correct
        ("int", ("int", "")),
        ("", ("", "")),
    ],
)
def test_split_unpacked(raw, expected):
    assert _split_unpacked(raw) == expected


def test_argument_defaults_are_captured(roots):
    fn = _find(roots, "f_defaults")
    assert fn.signature == (
        'function int f_defaults(int a, int b = 3, string s = "hi")'
    )


def test_task_argument_default_is_captured(roots):
    assert _find(roots, "t_default").signature == "task t_default(int cycles = 10)"


def test_argument_dimensions_follow_the_declarator(roots):
    fn = _find(roots, "f_dims")
    assert fn.signature == (
        "function int f_dims(int q[$], byte d[], bit fx[0:3], int assoc[string])"
    )


@pytest.mark.parametrize(
    "prop,expected",
    [
        ("m_q", "int m_q[$]"),
        ("m_dyn", "byte m_dyn[]"),
        ("m_assoc", "int m_assoc[string]"),
        ("m_packed", "logic[7:0] m_packed"),
        ("m_plain", "int m_plain"),
    ],
)
def test_property_dimensions_follow_the_declarator(roots, prop, expected):
    assert _find(roots, prop).signature == expected


def test_return_type_is_present(roots):
    assert _find(roots, "f_void").signature == "function void f_void()"
    assert _find(roots, "f_defaults").qualifiers == ["virtual"]
