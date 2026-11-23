from __future__ import annotations

import json

import pytest

from sphinx_systemverilog import svdb
from sphinx_systemverilog.svdb.database import Database
from sphinx_systemverilog.svdb.writer import Writer

HEADER = {"r": "header", "format": "svdb", "schema": "1.0", "producer": {"name": "test"}}


def example(name: str) -> list[dict]:
    return [json.loads(line) for line in svdb.example_text(name).splitlines() if line.strip()]


def memory_db(recs, *, strict: bool = True) -> tuple[Database, Writer]:
    w = Writer(":memory:", strict=strict)
    for rec in recs:
        w.add(rec)
    w.finish()
    return Database.from_connection(w.conn), w


def obj(qname: str, kind: str, ns: str = "package", pos: int = 0, **fields) -> dict:
    rec = {"r": "object", "kind": kind, "ns": ns, "qname": qname, "name": qname.rsplit("::", 1)[-1], "pos": pos}
    if "::" in qname and "parent" not in fields:
        rec["parent"] = qname.rsplit("::", 1)[0]
    rec.update(fields)
    return rec


def typeref(name: str, target: str | None = None) -> dict:
    span = {"at": [0, len(name)], "name": name}
    if target is not None:
        span["target"] = target
    return {"text": name, "form": "class", "refs": [span]}


@pytest.fixture
def example_db():
    """Factory: an in-memory Database built from one bundled example."""
    opened = []

    def make(name: str) -> Database:
        db, _ = memory_db(example(name))
        opened.append(db)
        return db

    yield make
    for db in opened:
        db.close()
