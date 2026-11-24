"""Linking a compile against other databases (docs/design/svdb-linking-plan.md
L3 to L5 and L7): a testbench built without its VIP's sources, against the
VIP's database.

The testbench's database must hold none of the VIP's declarations, name the
database it was linked against, and stitch with it into the same UVM tree as
one database built from both sources.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sphinx_systemverilog.frontend import link as link_mod
from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.model.index import clear_index_cache
from sphinx_systemverilog.svdb import Database, exporter
from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit

LINK = Path(__file__).resolve().parents[1] / "fixtures" / "link"


def _options(units: list, links: list = (), include_dirs: list = (), **kw) -> Options:
    return Options.make(build_units=[str(UVM_STUB / "mini_uvm.sv"), *map(str, units)],
                        include_dirs=[str(UVM_STUB), *map(str, include_dirs)],
                        links=[str(p) for p in links], doc_style="native", **kw)


def _build(path: Path, units: list, links: list = (), include_dirs: list = ()) -> Path:
    options = _options(units, links, include_dirs)
    write(parse(options), options, str(path)).conn.close()
    return path


def _records(path: Path) -> list[dict]:
    with Database.open(path) as db:
        return list(exporter.iter_records(db.connection()))


def _summary(tree):
    return ([(n.path, n.type, n.state) for n in tree.nodes],
            sorted((k.source.path, k.source.port, k.target.path, k.target.port, k.state) for k in tree.links))


# -- the stitching fixture: vip.svdb, tb linked against it, and tb from both sources --


@pytest.fixture(scope="module")
def stitch(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("link")
    vip = _build(tmp / "vip.svdb", [UVM_TB / "stitch_vip.sv"])
    tb = _build(tmp / "tb.svdb", [UVM_TB / "stitch_vip_tb.sv"], links=[vip])
    whole = _build(tmp / "whole.svdb", [UVM_TB / "stitch_vip.sv", UVM_TB / "stitch_vip_tb.sv"])
    return vip, tb, whole


def test_linked_database_has_no_vip_objects(stitch):
    _vip, tb, _whole = stitch
    recs = _records(tb)
    assert not [r for r in recs if r["r"] == "object" and r["qname"].split("::")[0] == "vip_pkg"]
    assert not [r for r in recs if "svdb-link:" in json.dumps(r)]
    assert not [r for r in recs if r["r"] == "uvm.type" and r["type"]["target"].startswith("vip_pkg::")]
    assert not [r for r in recs if r["r"] == "diag"]


def test_header_names_the_link(stitch):
    vip, tb, _whole = stitch
    links = _records(tb)[0]["links"]
    assert [(lk["origin"], lk["units"]) for lk in links] == [("vip", ["vip_pkg"])]
    assert links[0]["hash"] == link_mod.database_hash(str(vip))


def test_a_name_the_sources_define_is_not_linked(stitch):
    # mini_uvm_pkg is in vip.svdb too, but the testbench parses its source.
    _vip, tb, _whole = stitch
    assert "mini_uvm_pkg" not in _records(tb)[0]["links"][0]["units"]


def test_references_keep_the_vip_names(stitch):
    _vip, tb, _whole = stitch
    with Database.open(tb) as db:
        drv = db.get("vtb_pkg::fast_vip_driver")
        assert [b.qname if hasattr(b, "qname") else b.name for b in db.bases(drv)] == ["vip_driver"]
    with Database.open([tb, stitch[0]]) as db:
        drv = db.get("vtb_pkg::fast_vip_driver")
        assert [b.qname for b in db.bases(drv)] == ["vip_pkg::vip_driver"]


@pytest.mark.parametrize("order", ["tb_first", "vip_first"])
def test_linked_tree_equals_one_database(stitch, order):
    vip, tb, whole = stitch
    with Database.open(whole) as db:
        one = db.uvm_tree()
    with Database.open([tb, vip] if order == "tb_first" else [vip, tb]) as db:
        two = db.uvm_tree()
    assert _summary(two) == _summary(one)
    assert two.node("uvm_test_top.env.mst.drv").type == "vtb_pkg::fast_vip_driver"


def test_cache_key_follows_the_link_database(stitch, tmp_path):
    vip, _tb, _whole = stitch
    copy = tmp_path / "vip.svdb"
    shutil.copy(vip, copy)
    before = _options([UVM_TB / "stitch_vip_tb.sv"], links=[copy]).key()
    with open(copy, "ab") as f:
        f.write(b"\0")
    assert _options([UVM_TB / "stitch_vip_tb.sv"], links=[copy]).key() != before


# -- the AXI fixture: interface, types package, include file -------------------------


@pytest.fixture(scope="module")
def axi(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("axi")
    db = _build(tmp / "axi.svdb", [LINK / "axi_vip.sv"], include_dirs=[LINK])
    # Away from axi_macros.svh, so only the link database can supply it.
    tb_src = tmp / "tb" / "axi_tb.sv"
    tb_src.parent.mkdir()
    shutil.copy(LINK / "axi_tb.sv", tb_src)
    return db, tb_src


def test_link_supplies_packages_interfaces_and_includes(axi, tmp_path):
    db, tb_src = axi
    clear_index_cache()
    options = _options([tb_src], links=[db])
    index = parse(options)
    assert index.diagnostics == []
    (lk,) = [lk.record() for lk in index.builder.linked]
    assert sorted(lk["units"]) == ["axi_if", "axi_types_pkg", "axi_vip_pkg"]
    assert lk["includes"] == ["axi_macros.svh"]
    out = tmp_path / "tb.svdb"
    write(index, options, str(out)).conn.close()
    recs = _records(out)
    assert {r["qname"] for r in recs if r["r"] == "object" and r["kind"] in ("package", "interface", "module")} \
        == {"mini_uvm_pkg", "axi_tb_pkg", "axi_tb_top"}
    # The instance of the linked interface is kept; its elaboration is not.
    assert any(r["r"] == "object" and r["qname"] == "axi_tb_top::bus" for r in recs)
    assert not [r for r in recs if r["r"] == "elab" and r["def"] == "axi_if"]
    with Database.open([out, db]) as both:
        tree = both.uvm_tree()
    assert tree.node("uvm_test_top.env.agent").type == "axi_vip_pkg::axi_agent"
    assert tree.node("uvm_test_top.env.agent.drv").type == "axi_tb_pkg::fast_axi_driver"
    assert tree.node("uvm_test_top.env.agent.seqr").type == "axi_vip_pkg::axi_sequencer"


def test_without_the_link_the_names_are_unknown(axi):
    _db, tb_src = axi
    clear_index_cache()
    index = parse(_options([tb_src]))
    text = "\n".join(index.diagnostics)
    assert "axi_vip_pkg" in text and "AXI_CHECK" in text


def test_signature_mismatch_is_reported(axi, tmp_path):
    db, _tb = axi
    src = tmp_path / "bad_tb.sv"
    src.write_text('`include "mini_uvm.svh"\n'
                   "package bad_pkg;\n  import axi_vip_pkg::*;\n"
                   "  class bad_driver extends axi_driver;\n"
                   "    function new(string name, mini_uvm_pkg::uvm_component parent = null);\n"
                   "      super.new(name, parent);\n    endfunction\n"
                   "    virtual task drive(int req, output bit ok);\n    endtask\n"
                   "  endclass\nendpackage\n")
    clear_index_cache()
    index = parse(_options([src], links=[db]))
    assert any("bad_tb.sv" in d and "drive" in d for d in index.diagnostics), index.diagnostics


def test_round_limit(axi, monkeypatch):
    db, tb_src = axi
    monkeypatch.setattr(link_mod, "MAX_ROUNDS", 1)
    clear_index_cache()
    index = parse(_options([tb_src], links=[db]))
    assert any(d.startswith("link: gave up after 1 rounds") for d in index.diagnostics)


def test_problems_in_generated_text_are_link_errors(tmp_path):
    # A $unit class is not recorded, so the interface that uses it cannot be
    # linked whole: the error names the database, not a source line.
    vip = tmp_path / "u.sv"
    vip.write_text("class nib_c; endclass\ninterface u_if; nib_c h; endinterface\n")
    db = _build(tmp_path / "u.svdb", [vip])
    tb = tmp_path / "t.sv"
    tb.write_text("module t; u_if i(); endmodule\n")
    clear_index_cache()
    index = parse(_options([tb], links=[db]))
    errors = [d for d in index.diagnostics if d.startswith("link:")]
    assert errors and "u.svdb" in errors[0] and "nib_c" in errors[0]
    assert not [d for d in index.diagnostics if "svdb-link:" in d and not d.startswith("link:")]


# -- readers (L5) -----------------------------------------------------------------------


def test_a_changed_link_database_warns(stitch, tmp_path, caplog):
    _vip, _tb, _whole = stitch
    vip = _build(tmp_path / "vip.svdb", [UVM_TB / "stitch_vip.sv"])
    tb = _build(tmp_path / "tb.svdb", [UVM_TB / "stitch_vip_tb.sv"], links=[vip])
    with Database.open([tb, vip]) as db:
        assert [lk.state for lk in db.links()] == ["ok"]
    # The VIP is rebuilt from changed sources; the testbench is not relinked.
    src = tmp_path / "stitch_vip.sv"
    src.write_text((UVM_TB / "stitch_vip.sv").read_text() + "\npackage vip_extra_pkg; endpackage\n")
    vip.unlink()
    clear_index_cache()
    _build(vip, [src])
    with caplog.at_level("WARNING", logger="sphinx_systemverilog.svdb"):
        with Database.open([tb, vip]) as db:
            assert [lk.state for lk in db.links()] == ["changed"]
    assert "was linked against a different vip" in caplog.text


def test_a_missing_link_database_is_named(stitch):
    _vip, tb, _whole = stitch
    with Database.open(tb) as db:
        (lk,) = db.links()
        assert lk.state == "missing" and lk.units == ("vip_pkg",)
        tree = db.uvm_tree()
    issue = next(i for i in tree.issues if i.code == "unknown_type")
    assert issue.message.startswith("vip_pkg::vip_agent is not in") and "linked from vip" in issue.message


def test_follow_links(stitch):
    vip, tb, whole = stitch
    with Database.open(tb, follow_links=True) as db:
        assert db.paths == [str(tb), str(vip)]
        followed = db.uvm_tree()
    with Database.open(whole) as db:
        assert _summary(followed) == _summary(db.uvm_tree())


def test_a_linked_unit_defined_in_the_file_is_an_error():
    from sphinx_systemverilog.svdb.validate import validate

    from .conftest import HEADER, obj

    head = {**HEADER, "schema": "1.1", "links": [{"origin": "vip", "units": ["vip_pkg"]}]}
    report = validate([head, obj("vip_pkg", kind="package", ns="package")])
    assert "LinkedUnitDefined" in {i.code for i in report.errors}


def test_cli_build_link_and_stats(stitch, tmp_path, capsys):
    from sphinx_systemverilog.svdb.cli import main

    vip, _tb, _whole = stitch
    out = tmp_path / "tb.svdb"
    clear_index_cache()
    assert main(["build", "-o", str(out), "--build-unit", str(UVM_STUB / "mini_uvm.sv"),
                 "--build-unit", str(UVM_TB / "stitch_vip_tb.sv"), "-I", str(UVM_STUB),
                 "--link", str(vip)]) == 0
    assert "parser:" not in capsys.readouterr().err
    assert main(["stats", str(out)]) == 0
    assert f"linked against vip ({vip}): vip_pkg [not open" in capsys.readouterr().out
    assert main(["uvm-tree", "-d", str(out), "--follow-links"]) == 0
    assert "fast_vip_driver" in capsys.readouterr().out
