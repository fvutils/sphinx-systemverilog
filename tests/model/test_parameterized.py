"""Tests for parameterized (generic) class extraction (P3-IMPL-6)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit

CODE = """
package p;
  // A parameterized container.
  class queue #(type T = int) extends base;
    // the backing store
    T data[$];
    // add an item
    extern function void add(T item);
    function int size(); return data.size(); endfunction
  endclass
  class base; endclass
endpackage
"""


@pytest.fixture
def queue():
    roots = ModelBuilder().build_from_text(CODE)
    return next(c for c in roots[0].children if c.name == "queue")


def _m(cls, name):
    return next((c for c in cls.children if c.name == name), None)


def test_generic_class_is_class(queue):
    assert queue.kind == "class"
    assert "parameterized" in queue.qualifiers


def test_generic_class_doc_and_extends(queue):
    assert queue.raw_doc == "A parameterized container."
    assert queue.extends == "base"


def test_generic_class_members(queue):
    assert _m(queue, "data").kind == "property"
    assert _m(queue, "data").raw_doc == "the backing store"
    add = _m(queue, "add")
    assert add.kind == "function"
    assert add.raw_doc == "add an item"


def test_inline_body_signature_trimmed(queue):
    # The signature must be the prototype only, not the method body.
    size = _m(queue, "size")
    assert "return" not in size.signature
    assert size.signature.startswith("function int size(")
