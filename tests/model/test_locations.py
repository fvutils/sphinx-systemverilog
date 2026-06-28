"""Tests for source-location helpers (lifts locations.py coverage)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.locations import is_real_location, resolve_location

pytestmark = pytest.mark.unit


class _FakeSM:
    """Minimal SourceManager stand-in."""

    def __init__(self, file="f.sv", line=3, col=5, raise_on=None):
        self._file, self._line, self._col = file, line, col
        self._raise_on = raise_on

    def getFileName(self, loc):
        if self._raise_on == "file":
            raise RuntimeError("boom")
        return self._file

    def getLineNumber(self, loc):
        if self._raise_on == "line":
            raise RuntimeError("boom")
        return self._line

    def getColumnNumber(self, loc):
        return self._col


def test_none_location_is_not_real():
    assert is_real_location(_FakeSM(), None) is False


def test_synthesized_location_filtered():
    # Empty file name or non-positive line => synthesized / invalid.
    assert is_real_location(_FakeSM(file=""), object()) is False
    assert is_real_location(_FakeSM(line=0), object()) is False


def test_exception_treated_as_unreal():
    assert is_real_location(_FakeSM(raise_on="file"), object()) is False
    assert is_real_location(_FakeSM(raise_on="line"), object()) is False


def test_resolve_real_location():
    ref = resolve_location(_FakeSM(file="a.sv", line=7, col=2), object())
    assert ref is not None
    assert (ref.file, ref.line, ref.column) == ("a.sv", 7, 2)
    assert ref.is_valid


def test_resolve_returns_none_for_synthesized():
    assert resolve_location(_FakeSM(line=0), object()) is None
    assert resolve_location(_FakeSM(), None) is None
