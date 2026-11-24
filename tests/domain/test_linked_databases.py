"""Linking plan L6/L7: a Sphinx project whose sources link against a VIP's
database (``sv_databases``, linking by default) instead of parsing the VIP.

The VIP is listed as ``role: external``: its pages are elsewhere, but it is
linked, so the testbench compiles without unknown names, and the stitcher
reads it, so ``:resolved:`` still expands the VIP's agent.
"""

from __future__ import annotations

import re
import shutil

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.model.index import clear_index_cache
from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.sphinx


@pytest.fixture
def vip_db(tmp_path):
    options = Options.make(build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "stitch_vip.sv")],
                           include_dirs=[str(UVM_STUB)], doc_style="native")
    out = tmp_path / "vip.svdb"
    write(parse(options), options, str(out)).conn.close()
    clear_index_cache()
    return out


def _app(make_app, rootdir, tmp_path, entry):
    src = tmp_path / "linked"
    shutil.copytree(rootdir / "test-linked", src)
    app = make_app("html", srcdir=src, confoverrides={
        "sv_build_units": [str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "stitch_vip_tb.sv")],
        "sv_include_dirs": [str(UVM_STUB)],
        "sv_databases": [entry],
    })
    app.build()
    return app


def _resolved(app) -> str:
    page = (app.outdir / "index.html").read_text()
    start = page.index("Resolved")
    return re.sub(r"<[^>]+>", "", page[start:]).replace("&gt;", ">")


def test_external_vip_is_linked_and_stitched(make_app, rootdir, tmp_path, vip_db):
    app = _app(make_app, rootdir, tmp_path, {"path": str(vip_db), "role": "external"})
    assert app._warning.getvalue().strip() == ""
    text = _resolved(app)
    assert re.search(r"mst\s+: vip_agent", text)
    assert re.search(r"drv\s+: vip_driver → fast_vip_driver", text)
    assert re.search(r"seqr\s+: vip_sequencer", text)
    # Its pages are not here: role external documents nothing locally.
    assert "vip_agent" not in app.env.sv_index


def test_opting_out_of_the_link_leaves_the_names_unknown(make_app, rootdir, tmp_path, vip_db):
    app = _app(make_app, rootdir, tmp_path, {"path": str(vip_db), "role": "external", "link": False})
    assert "vip_pkg" in app._warning.getvalue()


# -- sequences from a linked VIP (run-phase plan, phase 3c) ----------------------------


@pytest.mark.parametrize("role", ["external", "local"])
def test_the_catalog_names_the_vip_a_sequence_comes_from(make_app, rootdir, tmp_path, role):
    from tests.svdb.test_linked_sequences import LINK

    options = Options.make(build_units=[str(UVM_STUB / "mini_uvm.sv"), str(LINK / "seq_vip.sv")],
                           include_dirs=[str(UVM_STUB)], doc_style="native")
    vip = tmp_path / "seq_vip.svdb"
    write(parse(options), options, str(vip)).conn.close()
    clear_index_cache()

    src = tmp_path / "linked-seqs"
    shutil.copytree(rootdir / "test-linked-sequences", src)
    app = make_app("html", srcdir=src, confoverrides={
        "sv_build_units": [str(UVM_STUB / "mini_uvm.sv"), str(LINK / "seq_vip_tb.sv")],
        "sv_include_dirs": [str(UVM_STUB)],
        "sv_databases": [{"path": str(vip), "role": role}],
    })
    app.build()
    assert app._warning.getvalue().strip() == ""
    page = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", (app.outdir / "index.html").read_text()))
    assert "run_phase() depends on 3 sequence(s)" in page
    assert page.count("seq_vip") >= 2, "the Origin of both VIP sequences"
    assert "no body" not in page
    assert "UVM activity diagram of vip_burst_seq" in (app.outdir / "index.html").read_text()
