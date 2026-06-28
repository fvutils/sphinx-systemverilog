"""Tests for the project-wide SvIndex (P1-TEST-4)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.index import SvIndex, build_index
from sphinx_systemverilog.model import ModelBuilder
from tests.conftest import FIXTURES, read_fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def index():
    roots = ModelBuilder().build_from_text(read_fixture("sample_pkg.sv"), "sample_pkg.sv")
    idx = SvIndex()
    idx.add_roots(roots)
    return idx


def test_qualified_lookup(index):
    obj = index.get("sample_pkg::sample_txn")
    assert obj is not None
    assert obj.name == "sample_txn"


def test_member_qualified_lookup(index):
    obj = index.get("sample_pkg::sample_txn::parity")
    assert obj is not None
    assert obj.kind == "function"


def test_bare_name_lookup_when_unique(index):
    obj = index.get("sample_base")
    assert obj is not None
    assert obj.kind == "class"


def test_dot_separator_accepted(index):
    assert index.get("sample_pkg.sample_txn") is index.get("sample_pkg::sample_txn")


def test_missing_returns_none(index):
    assert index.get("does_not_exist") is None
    assert "does_not_exist" not in index


def test_contains(index):
    assert "sample_pkg::sample_txn" in index


def test_build_index_from_dir():
    idx = build_index(source_dirs=[str(FIXTURES)], doc_style="native")
    assert "sample_pkg::sample_txn" in idx
    assert len(idx) > 0


def test_parse_once_for_many_lookups(monkeypatch):
    # build_index parses once; repeated lookups never reparse.
    calls = {"n": 0}
    real = ModelBuilder.build_from_files

    def counting(self, paths):
        calls["n"] += 1
        return real(self, paths)

    monkeypatch.setattr(ModelBuilder, "build_from_files", counting)
    idx = build_index(source_dirs=[str(FIXTURES)])
    for _ in range(10):
        idx.get("sample_pkg::sample_txn")
    assert calls["n"] == 1
