"""Shared pytest fixtures for the sphinx-systemverilog test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest_plugins = ["sphinx.testing.fixtures"]

#: Directory holding hand-written SystemVerilog fixtures.
FIXTURES = Path(__file__).parent / "fixtures" / "sv"

#: A small but structurally complete RTL design: generate loops, if-generate
#: branches, instance arrays and the same module elaborated at two widths.
#: Kept out of ``FIXTURES`` so it does not perturb the tests that index the
#: whole fixture directory.
DESIGN = Path(__file__).parent / "fixtures" / "design"

#: A deliberately large elaboration (4680 instances from 29 lines) used to
#: exercise the instance budget and to show how far index cost and walk cost
#: diverge.
DEEP = Path(__file__).parent / "fixtures" / "deep"

#: A design with structurally identical siblings, for exercising ``:collapse:``.
COLLAPSE = Path(__file__).parent / "fixtures" / "design_collapse"

#: A design parameterized by a configuration struct -- the shape CVA6 and other
#: modern cores use, where a parameter's value is unreadable but its type is not.
CONFIG = Path(__file__).parent / "fixtures" / "design_config"


@pytest.fixture(autouse=True)
def _clear_index_cache():
    """Isolate tests from the in-process index cache."""
    from sphinx_systemverilog.model.index import clear_index_cache

    clear_index_cache()
    yield
    clear_index_cache()


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
