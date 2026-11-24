"""The neutral Diagram model, its ELK JSON, and the elkjs layout engines."""
import os
import re
import shutil

import pytest

from sphinx_systemverilog.diagram import (
    Box, Bundle, Diagram, Edge, LayoutError, Port, get_engine, layout, to_elk,
)
from sphinx_systemverilog.diagram import engine as engine_mod
from sphinx_systemverilog.diagram.elk import ROOT_ID

pytestmark = pytest.mark.unit


def _env() -> Diagram:
    """A monitor fanning out to a scoreboard and a coverage collector."""
    root = Box("env", "env", "my_env", children=[
        Box("mon", "mon", "my_mon", ports=[Port("mon.ap", "ap", "EAST", "analysis")]),
        Box("sb", "sb", "my_sb", ports=[Port("sb.exp", "exp", "WEST"),
                                        Port("sb.act", "act", "WEST")]),
        Box("cov", "cov", "my_cov", ports=[Port("cov.i", "i", "WEST")]),
    ])
    return Diagram(root,
                   edges=[Edge("mon.ap", ["sb.act", "cov.i"], "analysis", label="txn")],
                   bundles=[Bundle("mon.ap", ["sb.exp"], label="2 sig",
                                   members=[Edge("mon.ap", ["sb.exp"], label="a"),
                                            Edge("mon.ap", ["sb.exp"], label="b")])])


def _all(node, key):
    yield from node.get(key, [])
    for c in node.get("children", []):
        yield from _all(c, key)


# --------------------------------------------------------------------------- model

@pytest.mark.parametrize("mutate, msg", [
    (lambda d: d.root.children.append(Box("mon", "dup")), "duplicate id 'mon'"),
    (lambda d: d.root.children[0].ports.append(Port("sb.act")), "duplicate id 'sb.act'"),
    (lambda d: setattr(d.root.children[0].ports[0], "side", "LEFT"), "side 'LEFT'"),
    (lambda d: d.edges.append(Edge("mon.ap", ["nowhere"])), "'nowhere' is not a box or port"),
    (lambda d: d.edges.append(Edge("mon.ap", [])), "has no targets"),
])
def test_validate_rejects(mutate, msg):
    d = _env()
    mutate(d)
    with pytest.raises(ValueError, match=msg):
        d.validate()


# ------------------------------------------------------------------------ ELK JSON

def test_root_is_wrapped():
    g = to_elk(_env())
    assert g["id"] == ROOT_ID
    assert [c["id"] for c in g["children"]] == ["env"]
    assert g["layoutOptions"]["elk.direction"] == "RIGHT"
    assert "elk.layered.cycleBreaking.strategy" not in g["layoutOptions"]


def test_hyperedge_splits_per_target_and_bundle_keeps_members():
    g = to_elk(_env())
    # one level: the edges are laid out inside the root box
    assert not g["edges"]
    edges = {e["id"]: e for e in g["children"][0]["edges"]}
    assert set(edges) == {"e0.0", "e0.1", "b0"}
    assert edges["e0.0"]["targets"] == ["sb.act"] and edges["e0.1"]["targets"] == ["cov.i"]
    # the label is drawn once, on the first branch
    assert edges["e0.0"]["labels"][0]["text"] == "txn" and "labels" not in edges["e0.1"]
    assert [m["label"] for m in edges["b0"]["members"]] == ["a", "b"]


def test_model_order_and_option_override():
    d = _env()
    d.model_order = True
    g = to_elk(d, {"elk.spacing.nodeNode": "40"})
    assert g["layoutOptions"]["elk.layered.cycleBreaking.strategy"] == "MODEL_ORDER"
    assert g["layoutOptions"]["elk.spacing.nodeNode"] == "40"


def test_leaf_sizing():
    d = _env()
    d.root.children.append(Box("v", "v", ports=[Port("v.h", "h", "NORTH")]))
    nodes = {n["id"]: n for n in _all(to_elk(d), "children")}
    sb = nodes["sb"]
    # west/east-only leaves are sized here, with their ports pinned in rows
    assert sb["layoutOptions"]["elk.portConstraints"] == "FIXED_POS"
    assert [p["y"] for p in sb["ports"]][1] - sb["ports"][0]["y"] == 18
    assert sb["height"] == 34 + 2 * 18 + 6
    # a north port leaves sizing to ELK
    assert nodes["v"]["layoutOptions"]["elk.portConstraints"] == "FIXED_ORDER"
    assert "width" not in nodes["v"]
    # containers are always sized by ELK
    assert "width" not in nodes["env"]


# -------------------------------------------------------------------------- layout

def test_elkjs_is_shipped():
    """elkjs must be present; without it every diagram falls back to Graphviz."""
    assert engine_mod.elk_source() is not None, engine_mod.unavailable_reason() or \
        "elk.bundled.js missing: run `ivpm update` or scripts/fetch_elkjs.py"
    assert engine_mod.elk_version() == "0.12.1"


def test_layout_positions_everything():
    laid = layout(to_elk(_env()))
    nodes = {n["id"]: n for n in _all(laid, "children")}
    assert set(nodes) == {"env", "mon", "sb", "cov"}
    assert all({"x", "y", "width", "height"} <= set(n) for n in nodes.values())
    # data flows left to right
    assert nodes["mon"]["x"] < nodes["sb"]["x"]
    for e in laid["edges"]:
        assert e["sections"], e["id"]
    # custom properties survive for the renderer
    assert nodes["mon"]["ports"][0]["kind"] == "analysis"
    assert "$H" not in repr(laid)


def test_layout_is_deterministic():
    assert layout(to_elk(_env())) == layout(to_elk(_env()))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_node_engine_matches_mini_racer():
    g = to_elk(_env())
    node = get_engine("node")
    assert node is not None and node.name == "node"
    assert engine_mod.strip_ids(node.layout(g)) == layout(g)


def test_bad_graph_raises_layout_error():
    with pytest.raises(LayoutError):
        layout({"id": "r", "children": [],
                "edges": [{"id": "e", "sources": ["nope"], "targets": ["q"]}]})


def test_cache_reuses_layouts(tmp_path):
    class Counting:
        name = "counting"

        def __init__(self):
            self.calls = 0

        def layout(self, graph):
            self.calls += 1
            return get_engine().layout(graph)

    eng = Counting()
    g = to_elk(_env())
    first = layout(g, eng, str(tmp_path))
    second = layout(g, eng, str(tmp_path))
    assert first == second and eng.calls == 1
    assert len(os.listdir(tmp_path)) == 1
    # a different graph is a different entry
    d = _env()
    d.direction = "DOWN"
    layout(to_elk(d), eng, str(tmp_path))
    assert eng.calls == 2


def test_missing_elkjs_names_the_fix(monkeypatch):
    monkeypatch.setattr(engine_mod, "elk_source", lambda: None)
    assert get_engine("mini-racer") is None
    assert "ivpm update" in engine_mod.unavailable_reason()


def test_layer_hint_reaches_elk():
    d = _env()
    d.root.children[0].layer = "FIRST"
    nodes = {n["id"]: n for n in _all(to_elk(d), "children")}
    assert nodes["mon"]["layoutOptions"]["elk.layered.layering.layerConstraint"] == "FIRST"
    d.root.children[0].layer = "LEFT"
    with pytest.raises(ValueError, match="layer 'LEFT'"):
        d.validate()


# -------------------------------------------------------------------------- render

def _svg(engine=None):
    d = _env()
    d.root.children[0].href = "mon.html"
    d.root.children[1].cls = "leaf cond"
    laid = layout(to_elk(d))
    return (engine or get_engine()).render(laid, {"idPrefix": "p1", "label": "env <x>"})


def test_render_draws_every_element():
    svg = _svg()
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" class="svd"')
    assert 'aria-label="env &lt;x&gt;"' in svg
    assert svg.count('class="box ') == 4
    assert '<a href="mon.html">' in svg and 'class="box leaf cond"' in svg
    # one arrowhead per kind with an arrow, ids prefixed per diagram
    assert 'id="p1-ah-analysis"' in svg and 'marker-end="url(#p1-ah-analysis)"' in svg
    assert 'marker-end="url(#p1-ah-bundle)"' in svg, "a bundle is directed too"
    assert ">txn</text>" in svg and 'class="t-port"' in svg


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_node_renders_the_same_svg():
    assert _svg(get_engine("node")) == _svg()


def test_render_links_the_box_face():
    svg = _svg()
    link = re.search(r'<a href="mon.html">(.*?)</a>', svg).group(1)
    assert link.startswith("<rect") and ">mon</text>" in link and ">my_mon</text>" in link
    assert 'class="port' not in link, "ports stay outside the link"


def _on(pt, d):
    pts = [tuple(map(float, p.split(","))) for p in d.split(" L")]
    x, y = pt
    return any(min(a[0], b[0]) <= x <= max(a[0], b[0]) and
               min(a[1], b[1]) <= y <= max(a[1], b[1]) for a, b in zip(pts, pts[1:]))


def test_render_marks_where_a_fan_out_splits():
    svg = _svg()
    edges = "".join(re.findall(r'<g class="e .*?</g>', svg))
    paths = re.findall(r'<path d="M([^"]+)"', edges)
    dots = [tuple(map(float, d)) for d in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)]
    fan = "".join(re.findall(r'<g class="e k-analysis">.*?</g>', svg))
    assert 'class="j"' in fan, "the fan-out has a dot"
    assert len(dots) == len(set(dots)), "one dot per point, not one per branch"
    for dot in dots:
        assert sum(_on(dot, d) for d in paths) >= 2, f"{dot} is where paths meet"


def test_container_port_labels_sit_just_above_the_port():
    root = Box("env", "env", ports=[Port("env.in", "in", "WEST", "analysis")],
               children=[Box("sb", "sb", ports=[Port("sb.i", "i", "WEST")])])
    d = Diagram(root, edges=[Edge("env.in", ["sb.i"], "analysis")])
    svg = get_engine().render(layout(to_elk(d)), {})
    port = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="8" height="8" class="port', svg)
    label = re.search(r'<text x="([\d.]+)" y="([\d.]+)" text-anchor="start" class="t-port">in<', svg)
    px, py = float(port.group(1)), float(port.group(2))
    lx, ly = float(label.group(1)), float(label.group(2))
    assert lx == px + 2
    assert ly == py - 1, "just above the port, clear of the wire inside"


def test_svref_links_resolve_through_the_domain_or_drop():
    from sphinx_systemverilog.diagram.sphinx import _resolve_links

    class Domain:
        objects = {"p::agt": ("api/agt", "sv-p-agt", "class"),
                   "uvm_pkg::uvm_reg_cbs::decode": ("uvm", "sv-decode", "function")}

        def candidates(self, target):
            return [fn for fn in self.objects if fn.rsplit("::", 1)[-1] == target]

    class Builder:
        current_docname = "guide/env"
        env = type("Env", (), {"get_domain": lambda self, name: Domain()})()

        def get_relative_uri(self, here, there):
            return "../" + there + ".html"

    svg = ('<g><a href="svref:agt #(item)"><rect/></a></g>'
           '<g><a href="svref:uvm_driver"><rect/><text>d</text></a></g>'
           '<g><a href="svref:decode"><rect/></a></g>')
    assert _resolve_links(Builder(), svg) == (
        '<g><a href="../api/agt.html#sv-p-agt"><rect/></a></g>'
        '<g><rect/><text>d</text></g>'
        '<g><rect/></g>'), "a box links to a type, never to a method of that name"


def test_one_level_diagram_is_laid_out_as_the_root_box_graph():
    flat = to_elk(_env(), )
    mod = flat["children"][0]
    assert flat["layoutOptions"]["elk.hierarchyHandling"] == "SEPARATE_CHILDREN"
    assert mod["layoutOptions"]["elk.direction"] == "RIGHT"
    assert "elk.json.edgeCoords" not in mod["layoutOptions"]

    nested = _env()
    nested.root.children[0].children.append(Box("inner", "inner"))
    g = to_elk(nested)
    assert g["layoutOptions"]["elk.hierarchyHandling"] == "INCLUDE_CHILDREN"
    assert g["edges"] and not g["children"][0].get("edges")


def test_order_reaches_cycle_breaking_in_a_one_level_diagram():
    # a -> b -> c -> a: only the model order says where to break the cycle
    def ring(order):
        boxes = {n: Box(n, n, ports=[Port(f"{n}.i", "i", "WEST"), Port(f"{n}.o", "o", "EAST")])
                 for n in "abc"}
        d = Diagram(Box("top", "top", children=[boxes[n] for n in order]),
                    edges=[Edge("a.o", ["b.i"]), Edge("b.o", ["c.i"]), Edge("c.o", ["a.i"])],
                    model_order=True)
        laid = layout(to_elk(d))
        return [c["id"] for c in sorted(laid["children"][0]["children"], key=lambda c: c["x"])]

    assert ring("abc") == ["a", "b", "c"]
    assert ring("cab") == ["c", "a", "b"]
