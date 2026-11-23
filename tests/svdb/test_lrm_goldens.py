"""D3 golden tests: each ``tests/svdb/lrm/<group>/<name>.sv`` through the
front end, compared with ``<name>.expected.ndjson``.

The comparison is on the exported records, in the exporter's canonical
order, without what varies between machines and runs: the header, file
paths (reduced to the base name) and content hashes.

``SVDB_REGEN=1`` rewrites the expected files instead.  Read the diff before
keeping it: a golden is only as good as its review.

D3-TEST-0 is here too: every object kind in the schema must appear in some
golden.  The kinds no group emits yet are listed, so the test fails both when
a kind goes missing and when a new group lands without crossing its kinds off.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.svdb import exporter, records
from sphinx_systemverilog.svdb.validate import validate

LRM = Path(__file__).parent / "lrm"
CASES = sorted(LRM.glob("*/*.sv"))

#: Kinds no D3 group emits yet; each group removes its own.
NOT_YET: set[str] = set()


def _records(sv: Path) -> list[dict]:
    options = Options.make(build_units=[str(sv)], doc_style="native")
    w = write(parse(options), options, ":memory:")
    out = []
    for rec in exporter.iter_records(w.conn):
        if rec["r"] == "header":
            continue
        rec.pop("hash", None)
        if rec["r"] == "file":
            rec["path"] = os.path.basename(rec["path"])
            rec.pop("sha256", None)
            rec.pop("size", None)
        if rec["r"] == "diag":
            rec["message"] = re.sub(r"\S*" + re.escape(os.sep + sv.name), sv.name, rec["message"])
        out.append(rec)
    w.conn.close()
    return out


def _expected_path(sv: Path) -> Path:
    return sv.with_suffix(".expected.ndjson")


@pytest.mark.parametrize("sv", CASES, ids=[f"{p.parent.name}/{p.stem}" for p in CASES])
def test_golden(sv):
    got = _records(sv)
    path = _expected_path(sv)
    if os.environ.get("SVDB_REGEN"):
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in got))
    expected = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert got == expected


@pytest.mark.parametrize("sv", CASES, ids=[f"{p.parent.name}/{p.stem}" for p in CASES])
def test_golden_sources_are_clean(sv):
    """A fixture that does not compile tests error recovery, not the kinds.

    ``unknown_module.sv`` is the one deliberate exception (D3c): it exists to
    show an instance of something not in this compilation, which is itself
    what makes slang report ``unknown module``."""
    errors = [r["message"] for r in _records(sv) if r["r"] == "diag" and r["severity"] == "error"
              and "unknown module" not in r["message"]]
    assert errors == []


@pytest.mark.parametrize("sv", CASES, ids=[f"{p.parent.name}/{p.stem}" for p in CASES])
def test_golden_is_valid(sv):
    """Each golden conforms to the schema (its detail fields included)."""
    head = {"r": "header", "format": "svdb", "schema": "1.0", "producer": {"name": "golden"},
            "sections": {"files": "complete", "objects": "complete"}}
    recs = [json.loads(line) for line in _expected_path(sv).read_text().splitlines() if line.strip()]
    report = validate([head, *recs])
    assert [str(e) for e in report.errors] == []


def test_every_kind_has_a_golden():
    """D3-TEST-0."""
    seen = set()
    for sv in CASES:
        for line in _expected_path(sv).read_text().splitlines():
            rec = json.loads(line)
            if rec["r"] == "object":
                seen.add(rec["kind"])
    kinds = set(records.kinds())
    assert sorted(kinds - seen) == sorted(NOT_YET)


@pytest.mark.parametrize("sv", CASES, ids=[f"{p.parent.name}/{p.stem}" for p in CASES])
def test_golden_references_resolve(sv):
    """Every name a golden's types and expressions mention is an object of it
    (through imports and across name spaces: ``virtual bus_if`` in a package).

    Two deliberate exceptions: an instance's ``of`` when ``state:
    unresolved`` (D3c), since the definition is not in this compilation; and
    a ``let``'s, ``sequence``'s or ``property``'s own formal argument names
    in its ``expr``/``body`` (D3d) -- they are bound by the declaration
    itself, not references to another object, and
    nothing else is emitted to resolve them to."""
    options = Options.make(build_units=[str(sv)])
    w = write(parse(options), options, ":memory:")
    unresolved = w.conn.execute(
        "SELECT o.qname, r.role, r.name FROM ref r JOIN object o ON o.id = r.src_id"
        " WHERE r.src = 0 AND r.target_id IS NULL"
        " AND NOT (o.kind = 'instance' AND r.role = 'of' AND json_extract(o.detail, '$.state') != 'ok')"
        " AND NOT (o.kind IN ('let', 'sequence', 'sva_property') AND r.role IN ('expr', 'body') AND r.name IN ("
        "   SELECT json_extract(a.value, '$.name') FROM json_each(json_extract(o.detail, '$.args')) a))"
    ).fetchall()
    w.conn.close()
    assert unresolved == []
