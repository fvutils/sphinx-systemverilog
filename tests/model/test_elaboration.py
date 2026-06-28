"""Tests for include-dir / define-driven elaboration (P2-TEST-4)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit


def test_include_dir_resolves_include(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "defs.svh").write_text("typedef logic [7:0] byte_t;\n")
    top = tmp_path / "top.sv"
    top.write_text('package mp;\n`include "defs.svh"\n  class c; byte_t b; endclass\nendpackage\n')

    builder = ModelBuilder(include_dirs=[str(inc)])
    roots = builder.build_from_files([str(top)])
    pkg = next(r for r in roots if r.name == "mp")
    assert any(c.name == "c" for c in pkg.children)


def test_define_applied(tmp_path):
    top = tmp_path / "top.sv"
    top.write_text(
        "package mp;\n  class c; logic [`WIDTH-1:0] data; endclass\nendpackage\n"
    )
    builder = ModelBuilder(defines={"WIDTH": "8"})
    roots = builder.build_from_files([str(top)])
    pkg = next(r for r in roots if r.name == "mp")
    c = next(x for x in pkg.children if x.name == "c")
    # WIDTH was defined, so data elaborated without an unknown-macro error.
    assert any(m.name == "data" for m in c.children)


def test_diagnostics_surface_errors(tmp_path):
    top = tmp_path / "bad.sv"
    top.write_text("package p; class c endclass endpackage")  # missing ';'
    builder = ModelBuilder()
    builder.build_from_files([str(top)])
    assert any("error" in d.lower() or "expected" in d.lower()
               for d in builder.diagnostics)
