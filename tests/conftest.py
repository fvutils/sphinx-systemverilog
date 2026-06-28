"""Shared pytest fixtures for the sphinx-systemverilog test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest_plugins = ["sphinx.testing.fixtures"]

#: Directory holding hand-written SystemVerilog fixtures.
FIXTURES = Path(__file__).parent / "fixtures" / "sv"


@pytest.fixture(scope="session")
def rootdir() -> Path:
    """Root for sphinx.testing's ``@pytest.mark.sphinx(testroot=...)``."""
    return Path(__file__).parent.resolve() / "roots"


@pytest.fixture
def sv_source(tmp_path):
    """Write SystemVerilog *text* to a temp file and return its path."""

    def _write(text: str, name: str = "snippet.sv") -> str:
        p = tmp_path / name
        p.write_text(text)
        return str(p)

    return _write


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()
