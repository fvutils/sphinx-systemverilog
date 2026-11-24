"""The neutral Diagram model, its ELK JSON, and the elkjs layout engines."""
import os
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
    edges = {e["id"]: e for e in g["edges"]}
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
