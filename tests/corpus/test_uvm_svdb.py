"""D2-TEST-4: UVM through the front end into a database, out as NDJSON and
back in; the counts by kind are the same at every step, and the objects Sphinx
renders are exactly the in-memory index's."""

from __future__ import annotations

import collections
import os

import pytest

from sphinx_systemverilog.frontend import emit
from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.model.db import rendered
from sphinx_systemverilog.svdb import Database, exporter, importer
from tests.conftest import UVM_SRC, requires_uvm

pytestmark = pytest.mark.corpus


def _by_kind(db: Database) -> dict[str, int]:
    return dict(db.sql("SELECT kind, count(*) FROM object GROUP BY kind"))


def _rendered_by_kind(db: Database) -> dict[str, int]:
    out: collections.Counter = collections.Counter()
    stack = db.roots()
    while stack:
        o = stack.pop()
        if rendered(o):
            out[o.kind] += 1
            stack.extend(db.members(o))
    return dict(out)


@requires_uvm
def test_uvm_round_trips_through_the_database(tmp_path):
    options = Options.make(source_dirs=[str(UVM_SRC)], build_units=[str(UVM_SRC / "uvm_pkg.sv")],
                           include_dirs=[str(UVM_SRC)], doc_style="naturaldocs")
    index = parse(options)
    expected = collections.Counter(emit.KIND_TO_SCHEMA.get(o.kind, o.kind)
                                   for r in index.roots for o in r.walk())

    first = os.fspath(tmp_path / "uvm.svdb")
    write(index, options, first).conn.close()
    exporter.export_file(first, tmp_path / "uvm.ndjson")
    second = os.fspath(tmp_path / "again.svdb")
    assert [i for i in importer.import_file(tmp_path / "uvm.ndjson", second) if i.severity == "error"] == []
    exporter.export_file(second, tmp_path / "again.ndjson")

    with Database.open(first) as a, Database.open(second) as b:
        assert _rendered_by_kind(a) == dict(expected)
        assert _by_kind(a) == _by_kind(b)
        assert len(a) >= len(index)
        assert sorted(o.qname for o in a.derived(a.get("uvm_component"))) == \
               sorted(o.qname for o in b.derived(b.get("uvm_component")))
        assert a.get("uvm_pkg::uvm_component").qname in {
            x.qname for x in a.bases(a.get("uvm_pkg::uvm_env")) if hasattr(x, "qname")}
    assert (tmp_path / "uvm.ndjson").read_bytes() == (tmp_path / "again.ndjson").read_bytes()
