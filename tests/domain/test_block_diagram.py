"""``sv:block-diagram``: an RTL module's instances and the nets between them."""
from __future__ import annotations

from pathlib import Path

import pytest

from sphinx_systemverilog.autodoc.rtl_diagram import (
    ROOT, build_block_diagram, collect, type_width,
)

RTL_BLOCK = Path(__file__).parent.parent / "fixtures" / "rtl_block"
CONF = {"sv_source_dirs": [str(RTL_BLOCK)]}


@pytest.fixture(scope="module")
def db():
    from sphinx_systemverilog.frontend.build import Options, open_index

    return open_index(Options.make(source_dirs=[str(RTL_BLOCK)]), cache_dir=None).database


@pytest.fixture
def model(db):
    return collect(db, db.get("pipe_top"))


def _edges(diagram):
    return {(e.source, tuple(e.targets)) for e in diagram.edges}


def _box(diagram, box_id):
    return next(b for b in diagram.boxes() if b.id == box_id)


@pytest.mark.unit
@pytest.mark.parametrize("text, width", [
    ("logic", 1), ("logic [31:0]", 32), ("logic signed [7:0]", 8),
    ("logic [3:0][7:0]", 32), ("bit [W-1:0]", None), ("int", 32),
    ("my_pkg::req_t", None), (None, 1), ("logic [2*4-1:0]", 8),
])
def test_type_width(text, width):
    assert type_width(text) == width


@pytest.mark.unit
def test_collect_finds_every_connection_style(model):
    assert [i.name for i in model.instances] == [
        "u_fetch", "u_decode", "u_exec", "u_ctrl", "u_trace"], "source order"
    # clocks and resets hidden, including rst_n, whose direction svdb leaves
    # off (``input logic clk, rst_n``)
    assert model.hidden == ["clk", "rst_n"]
    assert [p.port for p in model.ports] == ["boot_pc", "cfg", "result"]
    nets = {n.name: n for n in model.nets.values()}
    # implicit ``.*`` on u_ctrl
    assert [(e.owner, e.port) for e in nets["stall"].drivers] == [("u_ctrl", "stall")]
    assert [(e.owner, e.port) for e in nets["flush"].loads] == [("u_decode", "flush")]
    # a module output read from inside
    assert {(e.owner, e.port) for e in nets["result"].loads} == {
        (ROOT, "result"), ("u_trace", "result")}
    assert nets["imm"].width == 32 and nets["rs1"].width == 5
    assert nets["cfg"].intf == "pipe_cfg_if.dev"
    # the assign isn't in the database, so pc_in has readers and no driver
    assert model.undriven == ["pc_in"]
    # ``.dbg()`` is unconnected: no net
    assert "dbg" not in nets


@pytest.mark.unit
def test_nets_mode_draws_one_edge_per_net(model):
    d = build_block_diagram(model, "nets")
    d.validate()
    edges = _edges(d)
    assert ("u_fetch:instr", ("u_decode:instr",)) in edges
    assert ("u_exec:result", ("@root:result", "u_trace:result")) in edges, "a fan-out"
    assert ("@root:cfg", ("u_exec:cfg",)) in edges
    kinds = {e.source: e.kind for e in d.edges}
    assert kinds["u_fetch:instr"] == "bus" and kinds["u_ctrl:stall"] == "net"
    assert kinds["@root:cfg"] == "intf"
    fetch = _box(d, "u_fetch")
    sides = {p.label: p.side for p in fetch.ports}
    assert sides == {"pc_in": "WEST", "stall": "WEST", "instr": "EAST",
                     "instr_valid": "EAST", "pc": "EAST"}
    assert fetch.href == "svref:fetch" and fetch.sub == "fetch"
    root_sides = {p.label: p.side for p in d.root.ports}
    assert root_sides == {"boot_pc": "WEST", "cfg": "WEST", "result": "EAST"}
    assert not d.bundles


@pytest.mark.unit
def test_bundled_mode_merges_the_nets_between_two_blocks(model):
    d = build_block_diagram(model, "bundled")
    d.validate()
    by_src = {(b.source, tuple(b.targets)): b for b in d.bundles}
    b = by_src[("u_fetch:@out", ("u_decode:@from:u_fetch",))]
    assert [m.title for m in b.members] == ["instr [32]", "instr_valid", "pc [32]"]
    # each member runs between the nets' own ports, which expanding adds
    assert [(m.source, m.targets) for m in b.members] == [
        ("u_fetch:instr", ["u_decode:instr"]),
        ("u_fetch:instr_valid", ["u_decode:instr_valid"]),
        ("u_fetch:pc", ["u_decode:pc"])]
    assert {(o, p.id, p.side) for o, p in b.ports} == {
        ("u_fetch", "u_fetch:instr", "EAST"), ("u_fetch", "u_fetch:instr_valid", "EAST"),
        ("u_fetch", "u_fetch:pc", "EAST"), ("u_decode", "u_decode:instr", "WEST"),
        ("u_decode", "u_decode:instr_valid", "WEST"), ("u_decode", "u_decode:pc", "WEST")}
    labels = {p.id: p.label for p in _box(d, "u_decode").ports}
    assert labels["u_decode:@from:u_fetch"] == "u_fetch (3, 65b)"
    # one net is an ordinary edge, labelled with the net
    assert ("u_ctrl:@out", ("u_fetch:@from:u_ctrl",)) in _edges(d)
    assert labels["u_decode:@from:u_ctrl"] == "flush"
    # the module is one more block: its inputs leave by one port, its
    # outputs arrive at one port per source
    assert ("u_exec:@out", ("@root:@from:u_exec",)) in _edges(d)
    root = {p.id: (p.label, p.side) for p in d.root.ports}
    assert root == {"@root:cfg": ("cfg", "WEST"), "@root:@from:u_exec": ("result", "EAST")}
    # boot_pc only feeds the assign, so nothing inside reads it: no @in port
    # the undriven input is shown, unconnected
    assert {p.label for p in _box(d, "u_fetch").ports} >= {"(logic)"}


@pytest.mark.unit
def test_auto_picks_nets_for_a_small_module(model):
    assert not build_block_diagram(model, "auto").bundles


@pytest.mark.unit
def test_order_sets_child_order_and_model_order(model):
    d = build_block_diagram(model, "nets", order=["u_ctrl", "u_fetch"])
    assert [b.id for b in d.root.children][:3] == ["u_ctrl", "u_fetch", "u_decode"]
    assert d.model_order


@pytest.mark.unit
def test_nothing_hidden_with_an_empty_pattern(db):
    m = collect(db, db.get("pipe_top"), hide=None)
    assert not m.hidden and any(n.name == "clk" for n in m.nets.values())


@pytest.mark.unit
def test_every_mode_lays_out(model):
    from sphinx_systemverilog.diagram import get_engine, layout, to_elk

    for mode in ("nets", "bundled"):
        svg = get_engine().render(layout(to_elk(build_block_diagram(model, mode))), {})
        assert svg.startswith("<svg") and ">u_exec</text>" in svg


@pytest.mark.sphinx
@pytest.mark.sphinx("html", testroot="block-diagram", confoverrides=CONF)
def test_the_directive_draws_inline_svg(app, warning):
    from sphinx_systemverilog.diagram.sphinx import sv_diagram

    app.build()
    doctree = app.env.get_doctree("index")
    drawn = list(doctree.findall(sv_diagram))
    assert len(drawn) == 4
    page = (app.outdir / "index.html").read_text()
    assert page.count('<div class="sv-diagram"') == 4
    assert "Not drawn: clk, rst_n" in page
    assert "driven by logic inside pipe_top" in page and "pc_in" in page
    # the module types aren't documented here, so the boxes don't link
    assert "svref:" not in page
    text = warning.getvalue()
    assert "no module named 'no_such_module'" in text
    assert "trace instantiates nothing" in text
    assert ":order: names no instance u_nowhere" in text


@pytest.mark.sphinx
@pytest.mark.sphinx("text", testroot="block-diagram", confoverrides=CONF)
def test_other_builders_get_a_placeholder(app):
    app.build()
    assert (app.outdir / "index.txt").read_text().count("[Block diagram of pipe_top]") == 4


@pytest.mark.sphinx
@pytest.mark.sphinx(
    "html", testroot="block-diagram", srcdir="block-diagram-graphviz",
    confoverrides={**CONF, "sv_diagram_layout": "graphviz"},
)
def test_the_graphviz_setting_does_not_apply(app):
    from sphinx_systemverilog.diagram.sphinx import sv_diagram

    app.build()
    assert len(list(app.env.get_doctree("index").findall(sv_diagram))) == 4
