"""``sv:uvm-tree`` follows inherited phases and helpers (stitching plan A4).

A component that writes no ``build_phase`` builds what its base's builds; one
that creates its agents in a ``build_agents()`` helper builds them all the
same.  Both used to render as leaves.
"""

from __future__ import annotations

import re

import pytest

from tests.conftest import UVM_STUB, UVM_TB

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "stitch_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

pytestmark = pytest.mark.sphinx


def _section(page: str, title: str) -> str:
    """The text of the section titled *title*, tags stripped."""
    start = page.index(title)
    end = page.find("<h2", start)
    return re.sub(r"<[^>]+>", "", page[start:end if end > 0 else None])


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


@pytest.mark.sphinx("html", testroot="uvm-tree-inherit", srcdir="uvm-tree-inherit", confoverrides=CONF)
def test_an_inherited_build_phase_builds_the_base_children(page):
    text = _section(page, "Inherited phases")
    # inh_env writes no build_phase; base_env's creates agt_a and scb
    assert re.search(r"inh\s+: inh_env\n.*agt_a : st_agent.*scb\s+: st_scb.*nosup", text, re.S)


@pytest.mark.sphinx("html", testroot="uvm-tree-inherit", srcdir="uvm-tree-inherit", confoverrides=CONF)
def test_super_build_phase_runs_first(page):
    text = _section(page, "Inherited phases")
    sup = text[re.search(r"sup\s+: sup_env", text).start():]
    assert re.search(r"agt_a : st_agent.*scb\s+: st_scb.*agt_b : st_agent", sup, re.S)


@pytest.mark.sphinx("html", testroot="uvm-tree-inherit", srcdir="uvm-tree-inherit", confoverrides=CONF)
def test_a_build_phase_without_super_drops_the_base_children(page):
    text = _section(page, "Inherited phases")
    nosup = text[re.search(r"nosup : nosup_env", text).start():re.search(r"sup\s+: sup_env", text).start()]
    assert "agt_b : st_agent" in nosup and "agt_a : st_agent" not in nosup


@pytest.mark.sphinx("html", testroot="uvm-tree-inherit", srcdir="uvm-tree-inherit", confoverrides=CONF)
def test_helper_creates_are_children(page):
    text = _section(page, "Helpers")
    assert re.search(r"agts : st_agent\s+\(×N\)", text)
    assert re.search(r"scb\s+: st_scb\s+\[conditional\]", text)
    assert re.search(r"rec\s+: rec_comp", text)


@pytest.mark.sphinx("html", testroot="uvm-tree-inherit", srcdir="uvm-tree-inherit", confoverrides=CONF)
def test_the_build_is_warning_free(app, warning):
    app.build()
    assert "WARNING" not in warning.getvalue()
