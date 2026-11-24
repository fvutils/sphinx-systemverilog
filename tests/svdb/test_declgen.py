"""Linking plan L2: declaration-only text generated from a database
(``svdb/declgen.py``).

The generated text must compile alone, and a database built from it must
describe the same API as the database it was generated from."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pyslang = pytest.importorskip("pyslang")

from sphinx_systemverilog.frontend.build import Options, parse, write  # noqa: E402
from sphinx_systemverilog.svdb import declgen  # noqa: E402
from sphinx_systemverilog.svdb.database import Database  # noqa: E402
from tests.conftest import UVM_SRC, requires_uvm  # noqa: E402

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LINK = FIXTURES / "link"
STUB = FIXTURES / "uvm_stub"


def _build(path: Path, units: list[Path], include_dirs: list[Path] = ()) -> Database:
    options = Options.make(build_units=[str(u) for u in units], include_dirs=[str(d) for d in include_dirs],
                           doc_style="native")
    write(parse(options), options, str(path)).conn.close()
    return Database.open(path)


@pytest.fixture(scope="module")
def axi(tmp_path_factory):
    d = tmp_path_factory.mktemp("axi")
    db = _build(d / "axi.svdb", [STUB / "mini_uvm.sv", LINK / "axi_vip.sv"], [LINK, STUB])
    yield db
    db.close()


def _diagnostics(texts: dict[str, str], extra: dict[str, str] | None = None) -> list[str]:
    sm = pyslang.SourceManager()
    for path, text in (extra or {}).items():
        sm.assignText(path, text)
    comp = pyslang.ast.Compilation()
    for name, text in texts.items():
        comp.addSyntaxTree(pyslang.syntax.SyntaxTree.fromText(text, sm, name))
    engine = pyslang.DiagnosticEngine(sm)
    client = pyslang.TextDiagnosticClient()
    engine.addClient(client)
    for diag in comp.getAllDiagnostics():
        engine.issue(diag)
    return [line for line in client.getString().splitlines() if ": error:" in line or ": warning:" in line]


def test_closure_orders_dependencies_first(axi):
    cl = declgen.closure(axi, ["axi_vip_pkg"])
    names = [u.qname for u in cl.units]
    assert names[-1] == "axi_vip_pkg"
    # Imports, and the interface a virtual-interface property names.
    assert {"mini_uvm_pkg", "axi_types_pkg", "axi_if"} <= set(names[:-1])
    assert cl.missing == set() and cl.unit_scope == set()


def test_closure_reports_names_it_does_not_have(axi):
    cl = declgen.closure(axi, ["no_such_pkg"])
    assert cl.units == [] and cl.missing == {"no_such_pkg"}


def test_buffer_names(axi):
    texts = declgen.generate(axi, declgen.closure(axi, ["axi_types_pkg"]).units)
    assert list(texts) == ["svdb-link:axi/axi_types_pkg.sv"]
    assert declgen.is_link_buffer("svdb-link:axi/axi_types_pkg.sv")


def test_generated_text_compiles_alone(axi):
    texts = declgen.generate(axi, declgen.closure(axi, ["axi_vip_pkg", "axi_if"]).units)
    assert _diagnostics(texts) == []


def test_generated_declarations(axi):
    text = declgen.unit_text(axi, declgen.unit(axi, "axi_vip_pkg"))
    assert "typedef class axi_agent;" in text
    assert "virtual class axi_base_driver #(parameter type REQ = axi_item, parameter int DEPTH = 2)" \
           " extends uvm_driver;" in text
    assert "class axi_driver extends axi_base_driver #(axi_item, 4);" in text
    assert "pure virtual task drive(input REQ req, output bit ok);" in text
    assert "randc bit[3:0] id;" in text and "const int limit = 4;" in text
    assert "local function void reset_q();" in text
    # The constructor passes on what the base constructor requires (its
    # ``parent`` has a default).
    assert "super.new(name);" in text
    # Bodies, constraints and the utils macro are not there; its expansion is.
    assert "$sformatf" not in text and "c_len" not in text and "`mini" not in text
    assert 'typedef mini_uvm_pkg::uvm_component_registry #(axi_agent, "axi_agent") type_id;' in text
    types = declgen.unit_text(axi, declgen.unit(axi, "axi_types_pkg"))
    assert "typedef enum logic [1:0] { FIXED = 0, INCR = 1, WRAP = 2 } burst_e;" in types
    assert "typedef struct packed { logic [3:0] id; burst_e burst; } attr_t;" in types
    iface = declgen.unit_text(axi, declgen.unit(axi, "axi_if"))
    assert iface.startswith("interface axi_if #(parameter int AW = 32, parameter int DW = 32)"
                            " (input logic clk, input logic rst_n);")
    assert "modport mst(output addr, data, valid, input ready, clk);" in iface
    assert "clocking cb @(posedge clk);" in iface


def _api(db: Database, units: list[str]) -> dict:
    out = {}
    for name in units:
        for o in declgen._walk(db, declgen.unit(db, name)):
            if o.kind in ("constraint",):
                continue
            detail = {k: v for k, v in o.detail.items() if k != "prototype_only"}
            out[(o.qname, o.ns)] = (o.kind, sorted(o.quals), json.dumps(detail, sort_keys=True))
    return out


def test_round_trip_api(axi, tmp_path):
    units = declgen.closure(axi, ["axi_vip_pkg", "axi_if"]).units
    files = []
    for name, text in declgen.generate(axi, units).items():
        f = tmp_path / name.rsplit("/", 1)[1]
        f.write_text(text)
        files.append(f)
    gen = _build(tmp_path / "gen.svdb", files)
    try:
        names = [u.qname for u in units]
        assert _api(gen, names) == _api(axi, names)
    finally:
        gen.close()


def test_include_text(axi):
    path = next(p for p in declgen.include_files(axi) if p.endswith("axi_macros.svh"))
    text = declgen.include_text(axi, path)
    assert "`define AXI_ADDR_W 32" in text
    assert "`define AXI_CHECK(cond, msg) if (!(cond)) $error(msg);" in text
    use = ('`include "axi_macros.svh"\n`include "axi_macros.svh"\n'
           "module m; logic [`AXI_ADDR_W-1:0] a; initial `AXI_CHECK(a == 0, \"x\") endmodule\n")
    assert _diagnostics({"use.sv": use}, {"axi_macros.svh": text}) == []


@requires_uvm
def test_uvm_pkg_generates_text_that_compiles(tmp_path):
    """The hardest package a VIP pulls in: macro-generated members,
    parameterized classes, DPI, ``extern`` methods, constructors with
    required arguments, declarations spread over included files."""
    db = _build(tmp_path / "uvm.svdb", [UVM_SRC / "uvm_pkg.sv"], [UVM_SRC])
    try:
        cl = declgen.closure(db, ["uvm_pkg"])
        assert [u.qname for u in cl.units] == ["uvm_pkg"] and not cl.missing
        diags = _diagnostics(declgen.generate(db, cl.units))
        assert [d for d in diags if ": error:" in d] == []
    finally:
        db.close()
