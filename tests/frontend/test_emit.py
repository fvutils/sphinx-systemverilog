"""D2-IMPL-1 and D2-TEST-3: the front end's records.

The records round-trip: the index Sphinx reads (``DbIndex``) hands out the
same objects, field for field, as the in-memory ``SvIndex`` the builder makes,
and resolves names the same way.  The records are valid against the schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sphinx_systemverilog.frontend import emit
from sphinx_systemverilog.frontend.build import Options, open_index
from sphinx_systemverilog.model.builder import ModelBuilder
from sphinx_systemverilog.model.index import build_index
from sphinx_systemverilog.model.objects import SourceRef, SvObject
from sphinx_systemverilog.svdb.validate import validate
from tests.conftest import requires_uvm, UVM_SRC

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIELDS = ("kind", "name", "qualifiers", "signature", "extends", "raw_doc", "doc_style", "location", "group",
          "qualified_name", "from_macros")


def _same(a: SvObject, b: SvObject, path: str = "") -> None:
    path = f"{path}/{a.name}"
    for f in FIELDS:
        assert getattr(a, f) == getattr(b, f), f"{path}: {f}"
    assert [c.name for c in a.children] == [c.name for c in b.children], path
    for x, y in zip(a.children, b.children):
        _same(x, y, path)


def _compare(exact_counts: bool = True, **kw) -> None:
    legacy = build_index(use_cache=False, **kw)
    db = open_index(Options.make(**kw), cache_dir=None)
    assert len(db.roots) == len(legacy.roots)
    for a, b in zip(legacy.roots, db.roots):
        _same(a, b)
    for root in legacy.roots:
        for o in root.walk():
            for name in {o.qualified_name, o.name, o.qualified_name.replace("::", ".")}:
                x, y = legacy.get(name), db.get(name)
                assert (x and x.qualified_name) == (y and y.qualified_name), name
                assert [c.qualified_name for c in legacy.candidates(name)] == \
                       [c.qualified_name for c in db.candidates(name)], name
    assert db.diagnostics == legacy.diagnostics
    if exact_counts:
        assert db.suppressed_count == legacy.suppressed_count
    # The database holds more (plan D3); Sphinx sees what the index had.
    assert sum(1 for r in db.roots for _ in r.walk()) == len(legacy)
    assert len(db) >= len(legacy)


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()))
@pytest.mark.parametrize("style", ["native", "naturaldocs", "auto"])
def test_the_database_hands_out_the_builders_objects(fixture, style):
    d = FIXTURES / fixture
    _compare(source_dirs=[str(d)], include_dirs=[str(d)], doc_style=style)


@requires_uvm
@pytest.mark.corpus
def test_the_database_hands_out_the_builders_objects_for_uvm():
    # The number of suppressed lint diagnostics slang reports for UVM varies
    # from one compilation to the next in the same process (1094 to 1102), so
    # two compilations cannot be compared on it.
    _compare(exact_counts=False, source_dirs=[str(UVM_SRC)], build_units=[str(UVM_SRC / "uvm_pkg.sv")],
             include_dirs=[str(UVM_SRC)], doc_style="naturaldocs")


@pytest.mark.parametrize("fixture", ["sv", "uvm_tb", "design", "qualifiers"])
def test_records_are_valid(fixture):
    pytest.importorskip("jsonschema")
    d = FIXTURES / fixture
    index = build_index(source_dirs=[str(d)], include_dirs=[str(d)], doc_style="auto", use_cache=False)
    report = validate(emit.emit(index.roots, doc_style="auto", diagnostics=index.diagnostics,
                                suppressed=index.suppressed_count))
    assert report.ok, [str(i) for i in report.errors]
    assert report.schema_checked and report.objects == len(index)


# -- D2-TEST-3: identity (§3.3) -------------------------------------------------------

IDENTITY = r'''
package p;
  typedef class C;
  class D; C c; endclass
  // C doc
  class C;
    // proto doc
    extern function void f(int a);
  endclass
  // body doc
  function void C::f(int a); endfunction
endpackage
module m(a, b);
  input a;
  output b;
  wire a;
  logic b;
endmodule
`define FOO 1
`define FOO 2
'''


@pytest.fixture(scope="module")
def identity(tmp_path_factory):
    path = tmp_path_factory.mktemp("identity") / "identity.sv"
    path.write_text(IDENTITY)
    return open_index(Options.make(source_dirs=[str(path)]), cache_dir=None)


def _qnames(index) -> list[str]:
    return [o.qualified_name for r in index.roots for o in r.walk()]


def test_out_of_block_method_is_one_object_documented_at_the_prototype(identity):
    assert _qnames(identity).count("p::C::f") == 1
    assert identity.get("p::C::f").raw_doc == "proto doc"


def test_typedef_class_is_merged_into_the_class(identity):
    assert _qnames(identity).count("p::C") == 1
    assert identity.get("p::C").raw_doc == "C doc"


def test_non_ansi_port_and_net_are_not_two_objects(identity):
    for name in ("m::a", "m::b"):
        assert _qnames(identity).count(name) <= 1


def test_a_redefined_macro_is_its_last_definition(identity):
    assert _qnames(identity).count("FOO") == 1
    foo = identity.get("FOO")
    assert foo.signature == "`define FOO 2"
    rec = identity.database.record(identity.database.get("macro:FOO"))
    assert [l["line"] for l in rec["detail"]["redefined_at"]] == [foo.location.line - 1]


def test_unit_scope_declarations_in_two_units_build(tmp_path):
    """``$unit`` items are not documented yet (D3e adds ``unit`` records), but
    two units declaring the same name must not break the build."""
    a, b = tmp_path / "a.sv", tmp_path / "b.sv"
    a.write_text("class X; endclass\nmodule ma; endmodule\n")
    b.write_text("class X; int i; endclass\nmodule mb; endmodule\n")
    index = open_index(Options.make(source_dirs=[str(tmp_path)], build_units=[str(a), str(b)]),
                       cache_dir=None)
    assert {"ma", "mb"} <= set(_qnames(index))


def test_any_other_repeated_key_keeps_the_first_and_says_so():
    loc = SourceRef("x.sv", 3)
    roots = [SvObject("package", "p", qualified_name="p", location=loc, children=[
        SvObject("function", "f", qualified_name="p::f", signature="function void f()", location=loc),
        SvObject("task", "f", qualified_name="p::f", signature="task f()", location=SourceRef("x.sv", 9)),
    ]), SvObject("module", "p", qualified_name="p")]
    recs = list(emit.emit(roots, doc_style="native"))
    objs = [r for r in recs if r["r"] == "object"]
    assert [(o["ns"], o["qname"], o["kind"]) for o in objs] == [
        ("package", "p", "package"), ("package", "p::f", "function"), ("design", "p", "module")]
    (diag,) = [r for r in recs if r["r"] == "diag"]
    assert diag["code"] == "DuplicateObject" and "x.sv:9" in diag["message"] and "x.sv:3" in diag["message"]
