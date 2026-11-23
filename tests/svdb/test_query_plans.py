"""D1-TEST-4: no read-API query scans a large table.

Every statement in ``database.QUERIES`` is planned against a real (ANALYZEd)
database; a ``SCAN`` of any table but the tiny ones fails the test.  The
second test proves the guard has teeth: dropping an index makes it fire.
"""

from __future__ import annotations

import re

import pytest

from sphinx_systemverilog.svdb import database
from sphinx_systemverilog.svdb.writer import Writer

from .conftest import example

pytestmark = pytest.mark.unit

#: Tables small enough (one row per file, unit, origin, top) to scan, and
#: ``diag``, which is only ever read whole.
SMALL = {"unit", "u", "file", "f", "origin", "g", "top", "diag"}

#: Representative parameters, by query.
PARAMS = {"find": ("tb_top::*", 10), "find_kind": ("tb_top::*", "instance", 10), "by_name": ("clk", 100),
          "by_qname": ("tb_top",), "refs_to_qname": ("leaf",), "derived_qname": ("leaf",),
          "inst_used_by_name": ("leaf",)}


def _scans(conn, sql, params):
    plan = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    out = []
    for row in plan:
        m = re.match(r"SCAN (\w+)", row[-1])
        if m and m.group(1) not in SMALL:
            out.append(row[-1])
    return out


@pytest.fixture(scope="module")
def conn():
    w = Writer(":memory:")
    for rec in example("structure.ndjson"):
        w.add(rec)
    w.finish()
    yield w.conn
    w.conn.close()


@pytest.mark.parametrize("name", sorted(database.QUERIES))
def test_query_uses_indexes(conn, name):
    sql = database.QUERIES[name]
    params = PARAMS.get(name, (1,) * sql.count("?"))
    assert _scans(conn, sql, params) == []


def test_guard_fires_without_the_index(conn):
    conn.execute("DROP INDEX object_parent")
    try:
        # A fresh statement text: the sqlite3 module's statement cache would
        # otherwise hand back the plan made while the index existed.
        assert _scans(conn, database.QUERIES["members"] + " -- no index", (1,)) != []
    finally:
        conn.execute("CREATE INDEX object_parent ON object(parent_id, pos)")
