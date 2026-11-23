"""D2-IMPL-3 and D2-TEST-2: the one-shot database cache.

A Sphinx build writes the front end's database (and the snapshot of the
structure and UVM views) into ``<doctreedir>/svdb/`` and reuses it while the
sources are unchanged.  "Does not parse" is observed by replacing
``ModelBuilder.build_from_files`` with a stand-in that records the process it
ran in; forked parallel readers inherit the stand-in, so a parse in a worker
is recorded too.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from sphinx.testing.util import SphinxTestApp

from sphinx_systemverilog.model import builder
from sphinx_systemverilog.model.index import clear_index_cache
from tests.conftest import DESIGN, UVM_STUB, UVM_TB

pytestmark = pytest.mark.sphinx

ROOTS = Path(__file__).resolve().parents[1] / "roots"

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "basic_tb.sv"),
        *(str(DESIGN / n) for n in ("bus_if.sv", "leaf.sv", "lane.sv", "cluster.sv", "soc.sv")),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}


@pytest.fixture
def parses(monkeypatch, tmp_path):
    """The pids that parsed, as a list read back after a build."""
    log = tmp_path / "parses"
    log.mkdir()
    real = builder.ModelBuilder.build_from_files

    def spy(self, paths):
        (log / str(os.getpid())).write_text("")
        return real(self, paths)

    monkeypatch.setattr(builder.ModelBuilder, "build_from_files", spy)

    def read() -> list[int]:
        found = sorted(int(p.name) for p in log.iterdir())
        for p in log.iterdir():
            p.unlink()
        return found

    return read


def _app(srcdir: Path, *, parallel: int = 0, fresh: bool = False, **conf) -> SphinxTestApp:
    if not srcdir.exists():
        shutil.copytree(ROOTS / "test-parallel", srcdir)
    return SphinxTestApp("html", srcdir=srcdir, confoverrides={**CONF, **conf},
                         parallel=parallel, freshenv=fresh)


def _doctrees(app) -> dict[str, str]:
    return {d: app.env.get_doctree(d).pformat().replace(str(app.srcdir), "<SRC>")
            for d in sorted(app.env.found_docs)}


def _build(app) -> SphinxTestApp:
    try:
        app.build()
    finally:
        app.cleanup()
    return app


def test_a_second_build_does_not_parse(tmp_path, parses):
    src = tmp_path / "parallel"
    first = _build(_app(src))
    assert parses() == [os.getpid()]
    cache = sorted(p.name for p in (Path(first.doctreedir) / "svdb").iterdir())
    assert [n.rsplit(".", 1)[1] for n in cache] == ["snapshot", "svdb"]

    clear_index_cache()  # a new process, as far as the index is concerned
    second = _build(_app(src, fresh=True))
    assert parses() == [], "the cached database answers everything"
    assert _doctrees(second) == _doctrees(first)
    assert "Instance tree" in second.env.get_doctree("module").astext()


def test_a_changed_source_rebuilds_and_replaces_the_entry(tmp_path, parses):
    src = tmp_path / "parallel"
    lane = tmp_path / "lane.sv"
    shutil.copy(DESIGN / "lane.sv", lane)
    units = [str(lane) if u.endswith("lane.sv") else u for u in CONF["sv_build_units"]]
    first = _build(_app(src, sv_build_units=units))
    before = sorted((Path(first.doctreedir) / "svdb").iterdir())
    parses()

    clear_index_cache()
    st = lane.stat()
    os.utime(lane, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    second = _build(_app(src, fresh=True, sv_build_units=units))
    after = sorted((Path(second.doctreedir) / "svdb").iterdir())
    assert parses() == [os.getpid()]
    assert len(after) == 2 and after != before, "the old entry is pruned"


def test_without_the_cache_nothing_is_written(tmp_path, parses):
    app = _build(_app(tmp_path / "parallel", sv_db_cache=False))
    assert parses() == [os.getpid()]
    assert not (Path(app.doctreedir) / "svdb").exists()
    assert "soc" in app.env.get_doctree("tree").astext()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="parallel reading needs fork")
def test_parallel_build_parses_in_no_worker(tmp_path, parses):
    """D2-TEST-2."""
    serial = _build(_app(tmp_path / "serial"))
    parses()
    clear_index_cache()

    warm = tmp_path / "parallel-warm"
    shutil.copytree(ROOTS / "test-parallel", warm)
    shutil.copytree(Path(serial.doctreedir) / "svdb", warm / "_build" / "doctrees" / "svdb")
    par = _build(_app(warm, parallel=4))
    assert parses() == [], "with a warm cache nobody parses, workers included"
    assert _doctrees(par) == _doctrees(serial)

    clear_index_cache()
    cold = _build(_app(tmp_path / "parallel-cold", parallel=4))
    assert parses() == [os.getpid()], "a cold cache is filled by the main process only"
    assert _doctrees(cold) == _doctrees(serial)
