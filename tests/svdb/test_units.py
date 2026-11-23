"""``unit`` records: one per compilation unit, with the build's predefines."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sphinx_systemverilog.frontend.build import Options, parse, records, write
from sphinx_systemverilog.svdb import exporter

UNIT_SV = str(Path(__file__).parent / "lrm" / "other" / "unit.sv")


def _units(recs):
    return [r for r in recs if r.get("r") == "unit"]


def test_one_unit_per_file_with_predefines(tmp_path):
    other = tmp_path / "plain.sv"
    other.write_text("module plain; endmodule\n")
    o = Options.make(build_units=[UNIT_SV, str(other)], defines={"WIDTH": "8"})
    units = _units(records(parse(o), o))
    assert [u["id"] for u in units] == ["cu0", "cu1"]
    assert units[0]["default_nettype"] == "none" and units[0]["timescale"] == "1ns/1ps"
    assert units[1]["default_nettype"] == "wire" and "timescale" not in units[1]
    assert all(u["defines"] == {"WIDTH": "8"} for u in units)


def test_units_survive_the_database(tmp_path):
    o = Options.make(build_units=[UNIT_SV], defines={"WIDTH": "8"})
    write(parse(o), o, str(tmp_path / "a.svdb"))
    (unit,) = _units(exporter.iter_records(sqlite3.connect(tmp_path / "a.svdb")))
    assert unit == {"r": "unit", "id": "cu0", "files": ["f1"], "defines": {"WIDTH": "8"},
                    "default_nettype": "none", "timescale": "1ns/1ps"}
