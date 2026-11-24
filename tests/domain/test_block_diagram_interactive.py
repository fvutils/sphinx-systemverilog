"""The browser layer: sv-diagram.js expands a bundle and lays the diagram out again.

The DOM half (highlight, pan, zoom) needs a browser; what is checked here is
everything it stands on: the data attributes render.js writes, the graph the
page embeds, and the pure expansion and sizing functions, run in mini-racer
exactly as the browser would run them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sphinx_systemverilog.autodoc.rtl_diagram import build_block_diagram, collect
from sphinx_systemverilog.diagram import get_engine, layout, to_elk
from sphinx_systemverilog.diagram.engine import static_file

RTL_BLOCK = Path(__file__).parent.parent / "fixtures" / "rtl_block"
CONF = {"sv_source_dirs": [str(RTL_BLOCK)]}


@pytest.fixture(scope="module")
def db():
    from sphinx_systemverilog.frontend.build import Options, open_index

    return open_index(Options.make(source_dirs=[str(RTL_BLOCK)]), cache_dir=None).database


@pytest.fixture(scope="module")
def js():
    """A bare V8 with render.js and sv-diagram.js loaded, as on a page."""
    from py_mini_racer import MiniRacer

    ctx = MiniRacer()
    for name in ("render.js", "sv-diagram.js"):
        ctx.eval(static_file(name).read_text(encoding="utf-8"))
    yield lambda fn, *args: json.loads(ctx.eval(
        f"JSON.stringify({fn}({', '.join(json.dumps(a) for a in args)}))"))
    ctx.close()


@pytest.fixture
def bundled(db):
    return to_elk(build_block_diagram(collect(db, db.get("pipe_top")), "bundled"))


def _nodes(g):
    yield g
    for c in g.get("children", []):
        yield from _nodes(c)


def _edges(g):
    return [e for n in _nodes(g) for e in n.get("edges", [])]


def _ports(g):
    return {p["id"]: n["id"] for n in _nodes(g) for p in n.get("ports", [])}


@pytest.mark.unit
def test_js_sizes_a_leaf_exactly_as_python_does(bundled, js):
    leaves = [n for n in _nodes(bundled)
              if n.get("layoutOptions", {}).get("elk.portConstraints") == "FIXED_POS"]
    assert len(leaves) >= 4
    for n in leaves:
        blank = json.loads(json.dumps(n))
        for k in ("width", "height"):
            blank.pop(k)
        for p in blank["ports"]:
            p.pop("x"), p.pop("y")
        assert js("svDiagramSizeLeaf", blank) == n, n["id"]


@pytest.mark.unit
def test_expanding_a_bundle_draws_its_nets_between_their_own_ports(bundled, js):
    bid = next(e["bundle"] for e in _edges(bundled)
               if e.get("bundle") and e["sources"] == ["u_fetch:@out"]
               and e["targets"] == ["u_decode:@from:u_fetch"])
    out = js("svDiagramExpand", bundled, [bid])
    assert "expand" not in out

    edges = _edges(out)
    assert not any(e.get("bundle") == bid for e in edges)
    members = [(e["sources"][0], e["targets"][0]) for e in edges if e.get("member") == bid]
    assert members == [("u_fetch:instr", "u_decode:instr"),
                       ("u_fetch:instr_valid", "u_decode:instr_valid"),
                       ("u_fetch:pc", "u_decode:pc")]

    ports = _ports(out)
    for p in ("u_fetch:instr", "u_fetch:pc", "u_decode:instr", "u_decode:pc"):
        assert p in ports
    # the bundle's two ports carried nothing else, so they go; u_decode's
    # own @out still drives other blocks and stays
    assert "u_decode:@from:u_fetch" not in ports
    assert "u_fetch:@out" not in ports
    assert "u_decode:@out" in ports

    # the added ports take the bundle port's place, in member order, and the
    # box is sized again around them
    dec = next(n for n in _nodes(out) if n["id"] == "u_decode")
    west = [p["id"] for p in dec["ports"]
            if p["layoutOptions"]["elk.port.side"] == "WEST"]
    i = west.index("u_decode:instr")
    assert west[i:i + 3] == ["u_decode:instr", "u_decode:instr_valid", "u_decode:pc"]
    assert [p["layoutOptions"]["elk.port.index"] for p in dec["ports"]] == \
        [str(i) for i in range(len(dec["ports"]))]
    assert js("svDiagramSizeLeaf", dec) == dec
    assert not any("added" in p for p in dec["ports"])

    svg = get_engine().render(layout(out), {})
    assert svg.count(f'data-member="{bid}"') == 3


@pytest.mark.unit
def test_expanding_every_bundle_lays_out(bundled, js):
    bids = sorted({e["bundle"] for e in _edges(bundled) if e.get("bundle")})
    assert len(bids) >= 2
    out = js("svDiagramExpand", bundled, bids)
    assert not any(e.get("bundle") for e in _edges(out))
    ports = _ports(out)
    for e in _edges(out):
        for end in e["sources"] + e["targets"]:
            assert end in ports, f"{e['id']} ends on {end}, which isn't drawn"
    assert get_engine().render(layout(out), {}).startswith("<svg")


@pytest.mark.unit
def test_expanding_nothing_is_the_graph_itself(bundled, js):
    out = js("svDiagramExpand", bundled, [])
    bundled.pop("expand")
    assert out == bundled


@pytest.mark.unit
def test_render_writes_what_the_browser_needs(bundled):
    svg = get_engine().render(layout(bundled), {})
    assert 'data-box="u_fetch"' in svg
    assert 'data-port="u_fetch:@out"' in svg
    g = re.search(r'<g class="e k-bundle"[^>]*>', svg).group(0)
    assert re.search(r'data-bundle="b\d+"', g)
    assert 'data-ends="u_fetch:@out u_decode:@from:u_fetch"' in svg


@pytest.mark.unit
def test_a_fan_out_is_one_net():
    from sphinx_systemverilog.diagram import Box, Diagram, Edge, Port

    root = Box("env", "env", children=[
        Box("m", "m", ports=[Port("m.o", "o", "EAST")]),
        Box("a", "a", ports=[Port("a.i", "i", "WEST")]),
        Box("b", "b", ports=[Port("b.i", "i", "WEST")])])
    svg = get_engine().render(layout(to_elk(Diagram(root, [Edge("m.o", ["a.i", "b.i"])]))), {})
    assert re.findall(r'data-net="([^"]+)"', svg) == ["e0", "e0"]


@pytest.mark.sphinx
@pytest.mark.sphinx("html", testroot="block-diagram", confoverrides=CONF)
def test_the_page_loads_the_scripts_and_embeds_bundled_graphs(app):
    app.build()
    page = (app.outdir / "index.html").read_text()
    static = app.outdir / "_static"
    for name in ("sv-diagram.js", "sv-diagram-render.js", "sv-diagram-elk.js",
                 "sv-diagram.css"):
        assert (static / name).is_file(), name
    assert re.search(r'<script defer="defer" src="_static/sv-diagram.js[^"]*">', page)
    assert re.search(r'<script defer="defer" src="_static/sv-diagram-render.js[^"]*">', page)

    # only the bundled diagram has anything to expand
    blobs = re.findall(r'<script type="application/json" class="svd-graph">(.*?)</script>',
                       page, re.S)
    assert len(blobs) == 1
    g = json.loads(blobs[0])
    assert g["expand"]
    assert "svref:" not in blobs[0], "links are resolved (here: dropped) like the SVG's"
    assert len(re.findall(r'<div class="sv-diagram" data-prefix="svd[0-9a-f]+"', page)) == 4
