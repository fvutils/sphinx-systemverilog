"""Convert a :class:`~sphinx_systemverilog.diagram.model.Diagram` to ELK JSON.

The options follow d3-hwschematic's working configuration, tuned in the
block-diagram spike (``docs/design/block-diagram-layout.md``).  Properties ELK
doesn't know (``cls``, ``href``, ``kind``, a label's ``style``) pass through
the layout untouched and tell the renderer how to draw each element.

Leaves whose ports are all on the west and east sides are sized here, not by
ELK, with the title on top and the two port columns sharing rows; their ports
get fixed positions.  ELK's own sizing stacks the label rows of the two sides
and leaves the boxes much taller than they need to be.
"""
from __future__ import annotations

from typing import Any

from .model import Box, Diagram, Port

#: Root id wrapped around the diagram's root box.  ELK can't attach edges to
#: the graph root's own ports, so the diagram root is never the ELK root.
ROOT_ID = "__root__"

# Rough advance width, px per character, for each text style.  The renderer's
# fonts must stay close to these or labels overflow their boxes.
CHAR_W = {"name": 7.4, "sub": 6.0, "port": 6.0, "edge": 6.0}
LINE_H = {"name": 14, "sub": 12, "port": 11, "edge": 11}

ROW = 18          # port row pitch in a sized leaf
MIN_W, MIN_H = 70, 36

BASE_OPTIONS = {
    "elk.algorithm": "layered",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.layered.mergeEdges": "true",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.layered.spacing.nodeNodeBetweenLayers": "40",
    "elk.spacing.nodeNode": "24",
    "elk.spacing.edgeEdge": "8",
    "elk.layered.spacing.edgeNodeBetweenLayers": "14",
    "elk.json.shapeCoords": "ROOT",
    "elk.json.edgeCoords": "ROOT",
}


def text_width(text: str, style: str) -> float:
    return len(text) * CHAR_W[style]


def _label(text: str, style: str) -> dict:
    return {"text": text, "width": max(1.0, text_width(text, style)),
            "height": LINE_H[style], "style": style}


def _head(b: Box) -> int:
    """Height of the title block at the top of a box."""
    return 34 if b.sub else 22


def _node(b: Box) -> dict:
    n: dict[str, Any] = {
        "id": b.id, "cls": b.cls or ("cont" if b.children else "leaf"),
        "href": b.href, "title": b.title,
        "labels": [_label(b.label, "name")] + ([_label(b.sub, "sub")] if b.sub else []),
        "ports": [], "children": [],
    }
    n["ports"] = [_port(p, i) for i, p in enumerate(b.ports)]
    opts = {
        "elk.portConstraints": "FIXED_ORDER",
        "elk.nodeSize.constraints": "[PORTS, PORT_LABELS, NODE_LABELS, MINIMUM_SIZE]",
        "elk.nodeSize.minimum": f"({MIN_W}, {MIN_H})",
        "elk.nodeLabels.placement": "[H_CENTER, V_TOP, INSIDE]",
        "elk.portLabels.placement": "[INSIDE]",
        "elk.spacing.labelPortHorizontal": "4",
        "elk.spacing.portPort": "10",
        # keep ports clear of the title block
        "elk.spacing.portsSurrounding": f"[top={_head(b)},left=0,bottom=6,right=0]",
    }
    n["layoutOptions"] = opts
    if b.layer:
        opts["elk.layered.layering.layerConstraint"] = b.layer
    if b.children:
        opts["elk.padding"] = "[top=36,left=16,bottom=14,right=16]"
        n["children"] = [_node(c) for c in b.children]
    else:
        opts["elk.padding"] = "[top=34,left=6,bottom=6,right=6]"
        if all(p.side in ("WEST", "EAST") for p in b.ports):
            _size_leaf(b, n)
    return n


def _port(p: Port, i: int) -> dict:
    return {
        "id": p.id, "width": 8, "height": 8, "kind": p.kind,
        "href": p.href, "title": p.title,
        "labels": [_label(p.label, "port")] if p.label else [],
        "layoutOptions": {"elk.port.side": p.side, "elk.port.index": str(i),
                          "elk.port.borderOffset": "-4"},
    }


def _size_leaf(b: Box, n: dict) -> None:
    head = _head(b)
    west = [p for p in b.ports if p.side == "WEST"]
    east = [p for p in b.ports if p.side == "EAST"]
    lw = max([text_width(p.label, "port") for p in west] or [0])
    rw = max([text_width(p.label, "port") for p in east] or [0])
    tw = max(text_width(b.label, "name"), text_width(b.sub, "sub"))
    n["width"] = max(MIN_W, tw + 16, lw + rw + 34)
    n["height"] = max(MIN_H, head + max(len(west), len(east), 1) * ROW + 6)
    n["layoutOptions"]["elk.nodeSize.constraints"] = "[]"
    n["layoutOptions"]["elk.portConstraints"] = "FIXED_POS"
    row = {"WEST": 0, "EAST": 0}
    for ep, p in zip(n["ports"], b.ports):
        ep["x"] = -4 if p.side == "WEST" else n["width"] - 4
        ep["y"] = head + 5 + row[p.side] * ROW
        row[p.side] += 1
        if ep["labels"]:
            w = ep["labels"][0]["width"]
            ep["labels"][0].update({"x": 12 if p.side == "WEST" else -w - 4, "y": -2})


def to_elk(d: Diagram, options: dict[str, str] | None = None) -> dict:
    """Return the ELK JSON graph for *d*.  *options* override the root's layout options.

    A hyperedge becomes one ELK edge per target (``e3.0``, ``e3.1``, ...);
    ``mergeEdges`` draws them as one trunk that fans out, and ``group``
    tells the renderer which edges to put junction dots on.  A bundle's edges
    carry ``bundle`` (its id, ``b3``), and the graph root carries, under
    ``expand``, what expanding each bundle adds: the ports its members end
    on and their edges, tagged ``member``.  ELK ignores both; the browser
    script (``sv-diagram.js``) uses them to expand a bundle and lay out again.
    """
    d.validate()
    root = {"id": ROOT_ID, "labels": [], "children": [_node(d.root)], "edges": []}
    opts = dict(BASE_OPTIONS)
    opts["elk.direction"] = d.direction
    if d.model_order:
        opts["elk.layered.cycleBreaking.strategy"] = "MODEL_ORDER"
    opts.update(options or {})
    root["layoutOptions"] = opts

    def add(eid: str, e: Any, extra: dict, into: list | None = None) -> None:
        into = root["edges"] if into is None else into
        for k, t in enumerate(e.targets):
            ed: dict[str, Any] = {
                "id": f"{eid}.{k}" if len(e.targets) > 1 else eid,
                "sources": [e.source], "targets": [t],
                "kind": e.kind, "title": e.title, **extra,
            }
            if len(e.targets) > 1:
                ed["group"] = eid
            if e.label and k == 0:
                ed["labels"] = [_label(e.label, "edge")]
            if e.priority:
                ed["layoutOptions"] = {
                    "elk.layered.priority.direction": str(e.priority),
                    "elk.layered.priority.straightness": str(e.priority)}
            into.append(ed)

    for i, e in enumerate(d.edges):
        add(f"e{i}", e, {"conditional": e.conditional})
    expand = {}
    for i, b in enumerate(d.bundles):
        bid = f"b{i}"
        add(bid, b, {"bundle": bid})
        members: list = []
        for j, m in enumerate(b.members):
            add(f"{bid}m{j}", m, {"member": bid, "conditional": m.conditional}, members)
        expand[bid] = {
            "ports": [{"box": owner, "port": _port(p, 0)} for owner, p in b.ports],
            "edges": members,
        }
    if expand:
        root["expand"] = expand

    # A one-level diagram (no box inside the root has children) is laid out
    # as the root box's own graph.  Under INCLUDE_CHILDREN, model-order cycle
    # breaking has no effect, and the CVA6 pipeline only reads left to right
    # with it (see "RTL: CVA6" in docs/design/block-diagram-layout.md).
    if not any(c.children for c in d.root.children):
        mod = root["children"][0]
        mod["edges"], root["edges"] = root["edges"], []
        opts["elk.hierarchyHandling"] = "SEPARATE_CHILDREN"
        mod.setdefault("layoutOptions", {}).update(
            {k: v for k, v in opts.items() if k not in _OUTER_ONLY})
    return root


#: Options that stay on the outer graph when the root box is laid out as its
#: own graph; everything else is copied onto the root box.
_OUTER_ONLY = {"elk.hierarchyHandling", "elk.json.shapeCoords", "elk.json.edgeCoords"}
