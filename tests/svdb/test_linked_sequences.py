"""Sequences from a linked database (run-phase plan, phase 3c).

A testbench linked against a VIP's database starts the VIP's sequences.  Their
bodies are not in the generated declarations the compile sees, only in the
VIP database's records: the catalog reads them from there, names the VIP as
their origin, and the testbench's own database does not copy them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.model.db import DbIndex
from sphinx_systemverilog.model.index import clear_index_cache
from sphinx_systemverilog.svdb import Database, exporter
from tests.conftest import UVM_STUB

pytestmark = pytest.mark.unit

LINK = Path(__file__).resolve().parents[1] / "fixtures" / "link"


def _options(units, links=()):
    return Options.make(build_units=[str(UVM_STUB / "mini_uvm.sv"), *map(str, units)],
                        include_dirs=[str(UVM_STUB)], links=[str(p) for p in links],
                        doc_style="native")


@pytest.fixture(scope="module")
def linked(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("seqlink")
    vip = tmp / "seq_vip.svdb"
    options = _options([LINK / "seq_vip.sv"])
    write(parse(options), options, str(vip)).conn.close()
    clear_index_cache()
    tb = tmp / "tb.svdb"
    options = _options([LINK / "seq_vip_tb.sv"], [vip])
    index = parse(options)
    write(index, options, str(tb)).conn.close()
    clear_index_cache()
    return index.uvm_provider, DbIndex([str(tb), str(vip)]).uvm_provider, tb


@pytest.mark.parametrize("mode", ["live", "db"])
def test_a_linked_sequence_is_read_from_its_database(linked, mode):
    provider = linked[0] if mode == "live" else linked[1]
    catalog = provider.catalog("vip_test")
    assert [(e.type_name, e.depth, e.origin) for e in catalog.entries] == [
        ("tb_smoke_seq", 1, ""), ("vip_burst_seq", 1, "seq_vip"), ("vip_write_seq", 2, "seq_vip")]
    burst = catalog.entry("vip_burst_seq")
    assert burst.found and burst.defines_body
    write = catalog.entry("vip_write_seq")
    assert write.items == ("vip_item",)
    assert sorted(write.started_by) == ["tb_smoke_seq", "vip_burst_seq"]


@pytest.mark.parametrize("mode", ["live", "db"])
def test_the_tree_crosses_the_link(linked, mode):
    provider = linked[0] if mode == "live" else linked[1]
    tree = provider.tree("vip_test")
    assert [(n.type_name, n.origin, [c.type_name for c in n.children]) for n in tree.children] == [
        ("tb_smoke_seq", "", ["vip_write_seq"]), ("vip_burst_seq", "seq_vip", ["vip_write_seq"])]
    assert tree.children[1].children[0].repeated


@pytest.mark.parametrize("mode", ["live", "db"])
def test_users_span_the_link(linked, mode):
    provider = linked[0] if mode == "live" else linked[1]
    users = provider.users("vip_write_seq")
    assert [(u.root, u.depth) for u in users.users] == [
        ("vip_test", 2), ("tb_smoke_seq", 1), ("vip_burst_seq", 1)]


def test_the_testbench_database_holds_no_linked_task(linked):
    with Database.open(linked[2]) as db:
        names = {r["type"]["name"] for r in exporter.iter_records(db.connection())
                 if r["r"] == "uvm.sequence"}
    assert names == {"tb_smoke_seq", "vip_test"}


def test_the_command_follows_links(linked, capsys):
    import json

    from sphinx_systemverilog.svdb.cli import main

    assert main(["uvm-sequences", "-d", str(linked[2]), "--follow-links", "vip_test"]) == 0
    entries = json.loads(capsys.readouterr().out)["entries"]
    assert [(e["type_name"], e.get("origin", "")) for e in entries] == [
        ("tb_smoke_seq", ""), ("vip_burst_seq", "seq_vip"), ("vip_write_seq", "seq_vip")]
