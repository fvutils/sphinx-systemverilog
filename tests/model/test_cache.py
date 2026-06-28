"""Tests for the in-process index cache (P4-TEST-1)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import index as index_mod
from sphinx_systemverilog.model.index import build_index, clear_index_cache

pytestmark = pytest.mark.unit


def _write(tmp_path, text):
    p = tmp_path / "p.sv"
    p.write_text(text)
    return str(tmp_path)


def test_cache_hit_returns_same_object(tmp_path):
    src = _write(tmp_path, "package p; class c; endclass endpackage")
    clear_index_cache()
    i1 = build_index(source_dirs=[src])
    i2 = build_index(source_dirs=[src])
    assert i1 is i2


def test_cache_invalidated_on_change(tmp_path):
    src = _write(tmp_path, "package p; class c; endclass endpackage")
    clear_index_cache()
    i1 = build_index(source_dirs=[src])
    # Change the source (different content + mtime).
    import os, time

    (tmp_path / "p.sv").write_text("package p; class c; class d; endclass endpackage")
    os.utime(tmp_path / "p.sv", (time.time() + 10, time.time() + 10))
    i2 = build_index(source_dirs=[src])
    assert i1 is not i2


def test_use_cache_false_always_rebuilds(tmp_path):
    src = _write(tmp_path, "package p; class c; endclass endpackage")
    clear_index_cache()
    i1 = build_index(source_dirs=[src], use_cache=False)
    i2 = build_index(source_dirs=[src], use_cache=False)
    assert i1 is not i2
