"""Tests for the pyslang-backed model builder (P1-TEST-2)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from sphinx_systemverilog.model.objects import (
    KIND_CLASS,
    KIND_FUNCTION,
    KIND_PACKAGE,
    KIND_PROPERTY,
    KIND_TASK,
)
from tests.conftest import read_fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def sample_roots():
    return ModelBuilder().build_from_text(read_fixture("sample_pkg.sv"), "sample_pkg.sv")


def _find(obj, name):
    for o in obj.walk():
        if o.name == name:
            return o
    return None


def test_package_is_root(sample_roots):
    assert len(sample_roots) == 1
    pkg = sample_roots[0]
    assert pkg.kind == KIND_PACKAGE
    assert pkg.name == "sample_pkg"
    assert pkg.qualified_name == "sample_pkg"


def test_classes_discovered(sample_roots):
    pkg = sample_roots[0]
    classes = [c for c in pkg.children if c.kind == KIND_CLASS]
    assert {c.name for c in classes} == {"sample_base", "sample_txn"}


def test_inheritance_and_qualifiers(sample_roots):
    txn = _find(sample_roots[0], "sample_txn")
    assert txn.extends == "sample_base"
    base = _find(sample_roots[0], "sample_base")
    assert "virtual" in base.qualifiers


def test_member_kinds_and_signatures(sample_roots):
    txn = _find(sample_roots[0], "sample_txn")
    addr = _find(txn, "addr")
    assert addr.kind == KIND_PROPERTY
    assert "rand" in addr.qualifiers
    assert "bit[31:0]" in addr.signature

    parity = _find(txn, "parity")
    assert parity.kind == KIND_FUNCTION
    assert parity.signature.startswith("function bit parity(")
    assert "mask" in parity.signature

    drive = _find(txn, "drive")
    assert drive.kind == KIND_TASK
    assert "virtual" in drive.qualifiers


def test_visibility_qualifier(sample_roots):
    m_count = _find(sample_roots[0], "m_count")
    assert "local" in m_count.qualifiers


def test_synthesized_members_filtered(sample_roots):
    # Classes get compiler-injected methods (randomize, srandom, ...) with
    # bogus locations; none of them should leak into the model.
    names = {o.name for o in sample_roots[0].walk()}
    assert "randomize" not in names
    assert "srandom" not in names


def test_locations_resolved(sample_roots):
    txn = _find(sample_roots[0], "sample_txn")
    assert txn.location is not None
    assert txn.location.is_valid
    assert txn.location.file.endswith("sample_pkg.sv")
    assert txn.location.line > 0


def test_doc_comments_attached(sample_roots):
    txn = _find(sample_roots[0], "sample_txn")
    assert txn.raw_doc.startswith("A bus transaction.")
    addr = _find(txn, "addr")
    assert addr.raw_doc == "The target address."


def test_undocumented_member_has_no_doc():
    code = """
    package p;
      class c;
        int documented;   // a field
        int undocumented;
      endclass
    endpackage
    """
    roots = ModelBuilder().build_from_text(code)
    c = _find(roots[0], "c")
    assert _find(c, "undocumented").raw_doc is None
    # The undocumented field must not inherit the class's doc comment.


def test_module_documented():
    code = """
    // A configurable counter.
    module counter;
      int count;
    endmodule
    """
    roots = ModelBuilder().build_from_text(code)
    counter = next(r for r in roots if r.name == "counter")
    assert counter.kind == "module"
    assert counter.raw_doc == "A configurable counter."


def test_typedef_discovered():
    code = """
    package p;
      class c;
        typedef enum {A, B} state_e;
      endclass
    endpackage
    """
    roots = ModelBuilder().build_from_text(code)
    state = _find(roots[0], "state_e")
    assert state is not None
    assert state.kind == "typedef"


def test_diagnostics_collected_on_parse_error():
    builder = ModelBuilder()
    # Missing semicolon after the class declaration.
    builder.build_from_text("package p; class c endclass endpackage")
    assert len(builder.diagnostics) >= 1


def test_build_from_files(tmp_path):
    src = tmp_path / "p.sv"
    src.write_text("// pkg\npackage p;\n  class c; endclass\nendpackage\n")
    roots = ModelBuilder().build_from_files([str(src)])
    assert roots[0].name == "p"
    assert _find(roots[0], "c") is not None
