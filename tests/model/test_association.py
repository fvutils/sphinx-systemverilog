"""Tests for NaturalDocs detached-block association (P2-TEST-5)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit

UVM_STYLE = """
package uvm_pkg;

  // CLASS: my_object
  //
  // The base class for sample objects.
  virtual class my_object;

    // Group: Identification

    // Function -- NODOCS -- get_name
    //
    // Returns the name as set by ~set_name~.

    // @uvm-ieee 1800.2-2020 auto 5.3.4.2
    extern virtual function string get_name();

    // Group: Seeding

    // Function: reseed
    //
    // Reseeds the object.
    extern function void reseed();

  endclass

endpackage
"""


@pytest.fixture
def cls():
    roots = ModelBuilder(doc_style="naturaldocs").build_from_text(UVM_STYLE)
    pkg = roots[0]
    return next(c for c in pkg.children if c.name == "my_object")


def _m(cls, name):
    return next(c for c in cls.children if c.name == name)


def test_detached_block_associates_to_extern_method(cls):
    # The doc block is separated from the prototype by an @uvm-ieee annotation
    # and blank lines; named-block association still finds it.
    assert "Returns the name" in _m(cls, "get_name").raw_doc


def test_group_assignment(cls):
    assert _m(cls, "get_name").group == "Identification"
    assert _m(cls, "reseed").group == "Seeding"


def test_class_doc_from_named_block(cls):
    assert "base class for sample objects" in cls.raw_doc


def test_name_collision_resolved_by_proximity():
    code = """
    package p;
      // Function: f
      //
      // The A f.
      class a; extern function void f(); endclass
      // Function: f
      //
      // The B f.
      class b; extern function void f(); endclass
    endpackage
    """
    roots = ModelBuilder(doc_style="naturaldocs").build_from_text(code)
    pkg = roots[0]
    a = next(c for c in pkg.children if c.name == "a")
    b = next(c for c in pkg.children if c.name == "b")
    assert "The A f." in next(m for m in a.children if m.name == "f").raw_doc
    assert "The B f." in next(m for m in b.children if m.name == "f").raw_doc


def test_nodocs_skip_policy():
    code = """
    package p;
      class c;
        // Function -- NODOCS -- hidden
        //
        // Prose that is suppressed under skip policy.
        extern function void hidden();
      endclass
    endpackage
    """
    builder = ModelBuilder(doc_style="naturaldocs", nodocs_policy="skip")
    roots = builder.build_from_text(code)
    c = next(x for x in roots[0].children if x.name == "c")
    hidden = next(m for m in c.children if m.name == "hidden")
    assert hidden.raw_doc is None
