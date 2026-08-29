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

#: A ~200-line stand-in for UVM.  It reproduces the static structure the
#: testbench elaborator reads --- the factory registry, the component base-class
#: chain, config_db and TLM signatures --- and compiles in ~0.02s against
#: ~0.10s for real UVM, so the bulk of UVM coverage can run as fast unit tests
#: with no ivpm dependency.  Real UVM remains the corpus gate.
UVM_STUB = Path(__file__).parent / "fixtures" / "uvm_stub"

#: Testbenches written against the stub, one per extraction behaviour.
UVM_TB = Path(__file__).parent / "fixtures" / "uvm_tb"

#: Real UVM sources, fetched by ivpm.  Tests needing them use ``requires_uvm``.
UVM_SRC = Path(__file__).parent.parent / "packages" / "uvm" / "src"

#: Skip marker for tests that need the real UVM library rather than the stub.
#: Promoted out of ``tests/corpus/`` so every test module can reuse it.
requires_uvm = pytest.mark.skipif(
    not (UVM_SRC / "uvm_pkg.sv").is_file(), reason="UVM sources not present"
)


def uvm_stub_index(*tb_files: str, **kwargs):
    """Build an index over the mini-UVM stub plus the named testbench files.

    *tb_files* are names within :data:`UVM_TB`.  Caching is off by default:
    these indexes are cheap, and a test that shares one with another test is a
    test that can pass for the wrong reason.
    """
    from sphinx_systemverilog.model.index import build_index

    units = [str(UVM_STUB / "mini_uvm.sv")]
    units += [str(UVM_TB / name) for name in tb_files]
    kwargs.setdefault("use_cache", False)
    return build_index(
        source_dirs=[str(UVM_STUB)],
        build_units=units,
        include_dirs=[str(UVM_STUB)],
        **kwargs,
    )


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
