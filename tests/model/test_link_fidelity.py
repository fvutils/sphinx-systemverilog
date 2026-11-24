"""Linking plan L1: what a generated declaration needs from a database.

A class's ``extends`` type arguments and ``implements`` list, the written
qualifiers of a property, class-scope imports, and a header that declares
its ``bodies`` section."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.svdb import exporter
from sphinx_systemverilog.svdb.validate import validate

pytestmark = pytest.mark.unit

SRC = """\
package q;
  int qq;
endpackage

package p;
  interface class ic #(type T = int);
    pure virtual function void put(T x);
  endclass
  interface class ic2;
  endclass
  virtual class base #(type T = int, int N = 4);
  endclass
  class ordered extends base #(byte, 8) implements ic #(int), ic2;
    static const int k = 3;
    randc bit [3:0] r;
    rand int z;
    var int v;
    local static int w;
    protected int plain;
    virtual function void put(int x);
    endfunction
  endclass
  class named #(int M = 1) extends p::base #(.T(byte), .N(M));
  endclass
  class bare extends base;
    import q::qq;
  endclass
endpackage
"""


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    sv = tmp_path_factory.mktemp("l1") / "fidelity.sv"
    sv.write_text(SRC)
    options = Options.make(build_units=[str(sv)], doc_style="native")
    w = write(parse(options), options, ":memory:")
    recs = list(exporter.iter_records(w.conn))
    w.conn.close()
    return recs


def _obj(records, qname):
    return next(r for r in records if r["r"] == "object" and r["qname"] == qname)


def test_records_are_valid(records):
    report = validate(records)
    assert report.schema_checked and report.errors == []


def test_extends_args_ordered(records):
    detail = _obj(records, "p::ordered")["detail"]
    assert detail["extends"]["text"] == "base"
    assert [a["text"] for a in detail["extends_args"]] == ["byte", "8"]


def test_extends_args_named(records):
    detail = _obj(records, "p::named")["detail"]
    assert [a["text"] for a in detail["extends_args"]] == [".T(byte)", ".N(M)"]


def test_extends_without_args(records):
    assert "extends_args" not in _obj(records, "p::bare")["detail"]


def test_implements(records):
    impl = _obj(records, "p::ordered")["detail"]["implements"]
    assert [i["text"] for i in impl] == ["ic #(int)", "ic2"]
    assert [i["refs"][0]["name"] for i in impl] == ["ic", "ic2"]


@pytest.mark.parametrize("name, quals", [
    ("k", ["static", "const"]),
    ("r", ["randc"]),
    ("z", ["rand"]),
    ("v", ["var"]),
    ("w", ["static", "local"]),
    ("plain", ["protected"]),
])
def test_property_qualifiers(records, name, quals):
    assert _obj(records, f"p::ordered::{name}").get("quals", []) == quals


def test_package_variable_is_not_marked_static(records):
    assert "quals" not in _obj(records, "q::qq")


def test_class_scope_import(records):
    imports = [(r["scope"], r["package"]["name"], r["item"]) for r in records if r["r"] == "import"]
    assert ("p::bare", "q", "qq") in imports


def test_header_declares_bodies(records):
    header = next(r for r in records if r["r"] == "header")
    assert header["sections"]["bodies"] == "complete"
