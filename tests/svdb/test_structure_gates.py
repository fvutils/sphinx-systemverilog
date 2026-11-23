"""D3c-IMPL-3: gate instances (``of_kind: gate``) are opt-in behind
``structure_gates``/``structure.gates``, because a gate-level netlist can be
huge.  This fixture lives outside ``tests/svdb/lrm/`` so the default-options
D3 golden harness (``test_lrm_goldens.py``) never picks it up and runs it
with the flag off."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.svdb import exporter
from sphinx_systemverilog.svdb.validate import validate

SV = Path(__file__).parent / "structure_gates" / "gates.sv"


def _records(sv: Path, **opts) -> list[dict]:
    options = Options.make(build_units=[str(sv)], doc_style="native", **opts)
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


def test_gates_golden():
    got = _records(SV, structure_gates=True)
    path = SV.with_suffix(".expected.ndjson")
    if os.environ.get("SVDB_REGEN"):
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in got))
    expected = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert got == expected


def test_gates_golden_is_valid():
    expected = [json.loads(line) for line in SV.with_suffix(".expected.ndjson").read_text().splitlines()
                if line.strip()]
    head = {"r": "header", "format": "svdb", "schema": "1.0", "producer": {"name": "golden"},
            "sections": {"files": "complete", "objects": "complete", "structure.gates": "complete"}}
    report = validate([head, *expected])
    assert [str(e) for e in report.errors] == []


def test_gates_off_by_default():
    """The same sources, parsed with ``structure_gates`` unset, produce no
    gate instances at all -- and no ``structure.gates`` header section."""
    options = Options.make(build_units=[str(SV)], doc_style="native")
    w = write(parse(options), options, ":memory:")
    recs = list(exporter.iter_records(w.conn))
    w.conn.close()
    gates = [r for r in recs if r["r"] == "object" and r["kind"] == "instance"
              and r.get("detail", {}).get("of_kind") == "gate"]
    assert gates == []
    header = next(r for r in recs if r["r"] == "header")
    assert "structure.gates" not in header["sections"]
    report = validate(recs)
    assert [str(e) for e in report.errors] == []
