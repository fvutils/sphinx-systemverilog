"""Goldens for the ``uvm.*`` records (plan §5.3, D4-IMPL-1 / D4-TEST-2).

Each case is the mini-UVM stub plus one testbench of ``tests/fixtures/uvm_tb``;
the golden holds only the ``uvm.*`` records (the objects are the LRM goldens'
business).  ``SVDB_REGEN=1`` rewrites ``<tb>.expected.ndjson`` beside this file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.svdb import exporter
from sphinx_systemverilog.svdb.validate import validate
from tests.conftest import UVM_STUB, UVM_TB

HERE = Path(__file__).parent
CASES = ["basic_tb", "tlm_tb", "config_tb", "override_tb", "bridge_tb", "seq_tb", "stitch_tb", "seq_dep_tb",
         "seq_call_tb"]


def _records(tb: str) -> list[dict]:
    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / f"{tb}.sv")])
    w = write(parse(options), options, ":memory:")
    try:
        return list(exporter.iter_records(w.conn))
    finally:
        w.conn.close()


@pytest.mark.parametrize("tb", CASES)
def test_golden(tb):
    recs = _records(tb)
    assert not validate(recs).issues
    sections = recs[0]["sections"]
    assert all(sections[s] == "complete" for s in
               ("uvm.tree", "uvm.config", "uvm.overrides", "uvm.bindings", "uvm.sequences"))
    got = [r for r in recs if r["r"].startswith("uvm.")]
    path = HERE / f"{tb}.expected.ndjson"
    if os.environ.get("SVDB_REGEN"):
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in got))
    expected = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert got == expected


def test_bindings_name_config_records():
    """``uvm.binding`` points at ``uvm.config`` records by ``id``: ``set`` at a
    ``set``, every consumer at a ``get``."""
    recs = _records("bridge_tb")
    action = {r["id"]: r["action"] for r in recs if r["r"] == "uvm.config"}
    bindings = [r for r in recs if r["r"] == "uvm.binding"]
    assert bindings
    for b in bindings:
        assert action[b["set"]] == "set"
        assert all(action[c] == "get" for c in b.get("consumers", ()))
    assert any(b.get("consumers") for b in bindings)


#: Every testbench and option set the UVM tests (tests/model/test_uvm_*,
#: tests/domain/test_uvm_*) build, beyond :data:`CASES` (D4-TEST-1).
MORE_CASES = [
    ((), {}),
    (("basic_tb",), {"uvm_root": "my_env"}),
    (("bridge_tb", "config_tb"), {}),
    (("bridge_typedef_tb",), {}),
    (("missing_dep_tb",), {}),
    (("blackbox_tb",), {}),
    (("blackbox_tb",), {"uvm_blackbox_bases": ["uvm_reg_block"]}),
    (("blackbox_tb",), {"uvm_blackbox": ["acme_vip_*"]}),
    (("blackbox_tb",), {"uvm_blackbox": [], "uvm_blackbox_bases": []}),
    (("config_tb",), {"doc_style": "native"}),
    (("dup_names_tb",), {}),
    (("stitch_tb",), {"uvm_root": "helper_test"}),
    (("stitch_tb",), {"uvm_root": "inherit_test"}),
    (("basic_tb",), {"uvm_max_components": 3}),
]


@pytest.mark.parametrize("tb", CASES)
def test_views_round_trip(tb):
    """The views read back from the database equal the live provider's (D4-IMPL-2)."""
    _assert_round_trip((tb,))


@pytest.mark.parametrize("tbs,kw", MORE_CASES, ids=lambda v: "-".join(v) if isinstance(v, tuple)
                         else ",".join(f"{k}={v[k]}" for k in v))
def test_views_round_trip_more(tbs, kw):
    """As :func:`test_views_round_trip`, over the rest of what the UVM tests build."""
    _assert_round_trip(tbs, **kw)


def _assert_round_trip(tbs, **kw):
    from sphinx_systemverilog.frontend import uvm
    from sphinx_systemverilog.svdb import Database

    units = [str(UVM_STUB / "mini_uvm.sv")] + [str(UVM_TB / f"{tb}.sv") for tb in tbs]
    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=units, **kw)
    index = parse(options)
    live = uvm.views(index.uvm_provider)
    w = write(index, options, ":memory:")
    try:
        got = uvm.read(Database.from_connection(w.conn))
    finally:
        w.conn.close()
    assert got.structure == live.structure
    assert got.classes == live.classes
    assert got.config == live.config
    assert got.overrides == live.overrides
    assert got.bridge == live.bridge
    assert got.sequences == live.sequences


def test_db_index_answers_without_sources(tmp_path):
    """A ``DbIndex`` with no sources to parse answers the UVM views from the
    database's ``uvm.*`` records alone (D4-IMPL-2)."""
    from sphinx_systemverilog.frontend import uvm
    from sphinx_systemverilog.model.db import DbIndex

    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "seq_tb.sv")])
    index = parse(options)
    live = uvm.views(index.uvm_provider)
    path = str(tmp_path / "tb.svdb")
    write(index, options, path).conn.close()
    provider = DbIndex([path]).uvm_provider
    assert provider.get() == live.structure
    assert provider.config() == live.config
    assert provider.overrides() == live.overrides
    assert provider.bridge() == live.bridge
    assert live.sequences
    for q in live.sequences:
        assert provider.activity(q.name, q.method) == q
        assert provider.activity(q.name) == q
        assert provider.knows(q.name)
    # A component's task phase is stored beside the sequences, not as one.
    assert provider.sequence("seq_test") is None
    assert provider.activity("seq_test").method == "run_phase"
    assert not provider.knows("no_such_class")
    assert provider.sequence("no_such_class") is None


def test_db_index_answers_an_inherited_task_phase(tmp_path):
    """Only task phases user code writes are stored; any other task phase of a
    component is still answered, as empty, without parsing the sources."""
    from sphinx_systemverilog.model.db import DbIndex

    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "seq_tb.sv")])
    path = str(tmp_path / "tb.svdb")
    write(parse(options), options, path).conn.close()
    provider = DbIndex([path]).uvm_provider
    env = provider.activity("seq_env")
    assert env.method == "run_phase" and not env.overridden and env.empty
    assert provider.activity("seq_test", "main_phase").method == "main_phase"
    assert provider.activity("seq_test", "build_phase") is None
    assert provider.activity("seq_item", "run_phase") is None


@pytest.mark.parametrize("tb", ["seq_tb", "seq_dep_tb", "seq_call_tb"])
def test_db_index_catalogs_and_users_equal_live(tmp_path, tb):
    """Catalogs and users from the stored tasks equal the live provider's ---
    member handles, factory overrides and all."""
    from sphinx_systemverilog.model.db import DbIndex

    options = Options.make(source_dirs=[str(UVM_STUB)], include_dirs=[str(UVM_STUB)],
                           build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / f"{tb}.sv")])
    index = parse(options)
    live = index.uvm_provider
    path = str(tmp_path / "tb.svdb")
    write(index, options, path).conn.close()
    stored = DbIndex([path]).uvm_provider
    tasks = live.tasks()
    assert sorted((q.name, q.method) for q in stored.tasks()) == sorted((q.name, q.method) for q in tasks)
    for q in tasks:
        assert stored.catalog(q.name, q.method) == live.catalog(q.name, q.method)
        assert stored.tree(q.name, q.method) == live.tree(q.name, q.method)
        if q.method == "body":
            assert stored.users(q.name) == live.users(q.name)
