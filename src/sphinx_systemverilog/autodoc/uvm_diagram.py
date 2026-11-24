"""The UVM schematic: a single-level wiring diagram of one component.

This is the one view in the extension where the *layout* is the feature.  A
naive graph --- containment edges plus TLM edges, no constraints --- reproduces
a documented failure: because Graphviz treats every edge as a ranking
constraint, an analysis connection from a monitor up to a scoreboard drags the
scoreboard *below* the agents, and the result is a picture no verification
engineer recognizes.  Four techniques fix it, and all four are here:

1. **``newrank=true``.** Graphviz's default ranking documents that a node
   cannot be both inside a cluster and constrained by ``rank=same`` with a node
   outside it.  Agents want to be exactly that --- clusters *and* pinned to the
   bottom tier --- so the default algorithm cannot express this layout at all.
2. **Structure ranks, connectivity decorates.** Every TLM edge carries
   ``constraint=false``, so it draws without fighting the ranking.  This single
   attribute is what separates a readable diagram from the naive one.
3. **Tier pinning** via ``{rank=same; …}`` plus one invisible edge per tier
   boundary.  Tiers come from UVM's own base-class taxonomy, so the default
   needs no authoring; ``:tier:`` is the override, not the mechanism.
4. **Sibling ordering** via invisible ``weight=10`` chains, which is what
   removes the remaining crossings.

Knobs 1 and 3 need Graphviz 2.30+.  When the available ``dot`` is older or
absent, they are dropped and the rest is emitted unchanged: a degraded layout
is a real cost, and emitting DOT the local ``dot`` cannot lay out is a broken
build.

Scope is deliberately **single-level** (decision D3).  Depth is already served
by ``sv:uvm-tree``, which handles it as text and handles it well; a schematic
that nests two envs runs the four knobs above into each other.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Iterable

from ..model.uvm import (
    LINK_ANALYSIS,
    LINK_HANDLE,
    LINK_SEQ_ITEM,
    STATE_OK,
)

if TYPE_CHECKING:
    from ..diagram import Box, Diagram

#: The tier a component is drawn in, from the §7.4 taxonomy.  The point of
#: deriving this from the base class is that a good diagram costs *nothing* to
#: author --- a feature people configure once and then abandon is not a feature.
TIER_TOP = "top"
TIER_MIDDLE = "middle"
TIER_BOTTOM = "bottom"
TIERS = (TIER_TOP, TIER_MIDDLE, TIER_BOTTOM)

#: Model tier (``UvmType.tier``) -> schematic tier.  Anything the taxonomy does
#: not place lands in the middle, which is the tier that constrains least.
_TIER_BY_ROLE = {
    "sequencer": TIER_TOP,
    "analysis": TIER_MIDDLE,
    "env": TIER_MIDDLE,
    "test": TIER_MIDDLE,
    "agent": TIER_BOTTOM,
    "driver": TIER_BOTTOM,
    "monitor": TIER_BOTTOM,
}

#: Components rendered as a cluster rather than a box, when they have children.
#: An agent is the one UVM component whose *contents* are what a reader wants:
#: "is this agent active?" is answered by whether it holds a driver.
_CLUSTER_ROLES = ("agent",)

#: Preferred left-to-right order inside an agent cluster.  Mirrored on
#: alternate agents so monitors face the centre of the diagram, which is knob 4
#: doing the thing it exists for --- it is what removes the crossings when two
#: agents both feed one scoreboard.
_CLUSTER_ORDER = ("sequencer", "driver", "monitor")

#: Edge styling by link kind.  Colour carries the distinction rather than a
#: label, because §7.5 is explicit that edge labels are the weak point.
#: ``(colour, line style)`` per link kind.  Kept as two fields rather than one
#: attribute string so a conditional edge can override the style without
#: emitting a contradictory pair of ``style=`` attributes.
_EDGE_STYLE = {
    LINK_ANALYSIS: ("#2563eb", "solid"),
    LINK_SEQ_ITEM: ("#b45309", "solid"),
    LINK_HANDLE: ("#7c3aed", "dashed"),
}
_EDGE_DEFAULT = ("#5a6070", "solid")

#: Graphviz release that introduced ``newrank``.
_NEWRANK_SINCE = (2, 30)

_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


@dataclass
class _Node:
    """One drawn box, addressed by its instance path from the diagram root."""

    path: tuple[str, ...]
    handle: str
    type_name: str
    role: str = ""
    tier: str = TIER_MIDDLE
    ports: tuple = ()
    conditional: bool = False
    state: str = STATE_OK
    #: Instance path of the cluster this sits in, or ``()`` for a top-level box.
    parent: tuple[str, ...] = ()

    @property
    def dot_id(self) -> str:
        return "n_" + "__".join(_ID_SAFE.sub("_", part) for part in self.path)


@dataclass
class _Cluster:
    """An agent, drawn as a labelled box holding its own components."""

    path: tuple[str, ...]
    handle: str
    type_name: str
    conditional: bool = False
    members: list[_Node] = field(default_factory=list)
    #: The agent's own ports.  Only filled in *containers* mode, where a
    #: connection can end on them; Graphviz clusters can't carry ports.
    ports: tuple = ()

    @property
    def dot_id(self) -> str:
        return "cluster_" + "__".join(_ID_SAFE.sub("_", p) for p in self.path)


@dataclass
class Schematic:
    """A resolved single-level schematic, ready to emit as DOT.

    Kept separate from the emitter so the tests that matter --- which endpoint
    resolved to which box --- can be written against structure rather than
    against text, while the DOT assertions stay about layout.
    """

    root: str = ""
    nodes: list[_Node] = field(default_factory=list)
    clusters: list[_Cluster] = field(default_factory=list)
    edges: list[tuple] = field(default_factory=list)
    #: Connections whose endpoints could not be placed in this view, and why.
    #: Reported under the diagram: an edge that silently vanished would make an
    #: incomplete picture look complete, which is the one thing this extension
    #: does not do.
    dropped: list[str] = field(default_factory=list)
    #: Top-level boxes in the order ``:order:`` asked for, or ``None`` when no
    #: ordering was requested and source order stands.
    ordered: list[_Node] | None = None
    #: Inherited library ports left off the boxes because nothing connects to
    #: them.  Counted rather than merely dropped --- see :func:`_prune_library_ports`.
    hidden_ports: int = 0
    #: ``:order:`` as given, for front ends that order by name rather than
    #: through :attr:`ordered`.
    order: list[str] = field(default_factory=list)
    #: True when agents and the root can be connection endpoints themselves
    #: (see :func:`build_schematic`).
    containers: bool = False
    #: The root's own ports, in *containers* mode.
    root_ports: tuple = ()

    def node(self, path: tuple[str, ...]) -> _Node | None:
        return next((n for n in self.nodes if n.path == path), None)


def build_schematic(
    structure: Any, root: str, tiers: dict[str, str] | None = None,
    order: Iterable[str] = (), containers: bool = False,
) -> Schematic:
    """Resolve *root*'s children, their ports, and the connections between them.

    *tiers* overrides the derived tier, keyed on an instance handle or on a type
    name --- handle first, because that is the more specific request and the one
    a reader writing an override usually means.

    *containers* lets a connection end on an agent's own port or on the
    root's, as in ``mon.ap.connect(ap)`` inside an agent.  Graphviz can't draw
    those (a cluster has no ports), so the DOT path leaves it off and reports
    them as dropped; the ELK path turns it on.
    """
    overrides = tiers or {}
    schematic = Schematic(root=root, containers=containers)
    if containers:
        schematic.root_ports = tuple(getattr(structure.type_of(root), "ports", ()) or ())

    for child in structure.children_of(root):
        info = structure.type_of(child.type_name)
        role = getattr(info, "tier", "") or ""
        path = (_handle_of(child),)
        grandchildren = structure.children_of(child.type_name)

        if role in _CLUSTER_ROLES and grandchildren and child.state == STATE_OK:
            cluster = _Cluster(
                path=path,
                handle=path[0],
                type_name=child.type_name,
                conditional=child.conditional,
            )
            if containers:
                cluster.ports = tuple(getattr(info, "ports", ()) or ())
            for inner in grandchildren:
                inner_info = structure.type_of(inner.type_name)
                node = _Node(
                    path=path + (_handle_of(inner),),
                    handle=_handle_of(inner),
                    type_name=inner.type_name,
                    role=getattr(inner_info, "tier", "") or "",
                    # A node inside a cluster takes the cluster's tier, always.
                    # Its own role would put an agent's sequencer on the top
                    # tier and tear the cluster in half.
                    tier=TIER_BOTTOM,
                    ports=getattr(inner_info, "ports", ()),
                    conditional=inner.conditional,
                    state=inner.state,
                    parent=path,
                )
                cluster.members.append(node)
                schematic.nodes.append(node)
            schematic.clusters.append(cluster)
            continue

        schematic.nodes.append(
            _Node(
                path=path,
                handle=path[0],
                type_name=child.type_name,
                role=role,
                tier=_TIER_BY_ROLE.get(role, TIER_MIDDLE),
                ports=getattr(info, "ports", ()),
                conditional=child.conditional,
                state=child.state,
            )
        )

    _apply_tier_overrides(schematic, overrides)
    _collect_edges(structure, root, schematic)
    _prune_library_ports(schematic)
    schematic.order = list(order)
    _apply_order(schematic, schematic.order)
    # Mirroring is by final position, so it has to follow any reordering ---
    # otherwise ``:order:`` could put two same-facing agents side by side and
    # reintroduce exactly the crossings knob 4 exists to remove.
    for index, cluster in enumerate(schematic.clusters):
        _order_cluster(cluster, index)
    return schematic


def _handle_of(child) -> str:
    return child.handle or child.inst_name or "?"


def _apply_tier_overrides(schematic: Schematic, overrides: dict[str, str]) -> None:
    for node in schematic.nodes:
        if node.parent:
            # Cluster members follow their cluster; overriding one individually
            # would ask Graphviz for a layout it cannot draw.
            continue
        tier = overrides.get(node.handle) or overrides.get(node.type_name)
        if tier in TIERS:
            node.tier = tier


def _order_cluster(cluster: _Cluster, index: int) -> None:
    """Sort a cluster's members, mirroring alternate agents.

    Two agents both feeding one scoreboard cross unless their monitors face
    each other; mirroring is what makes them.  Purely visual, and the ordering
    chain that implements it is invisible.
    """
    def key(node: _Node) -> int:
        try:
            return _CLUSTER_ORDER.index(node.role)
        except ValueError:
            return len(_CLUSTER_ORDER)

    cluster.members.sort(key=key, reverse=bool(index % 2))


def _collect_edges(structure: Any, root: str, schematic: Schematic) -> None:
    """Place every connection reachable in this single-level view.

    Two sources: connections written in the root's own ``connect_phase``, and
    connections written *inside* each cluster.  The second is why an agent's
    ``drv.seq_item_port.connect(seqr.seq_item_export)`` appears at all --- and
    why it appears once per agent instance, since the source describes the type
    and each instance really does make that connection.
    """
    drawn = {node.path for node in schematic.nodes}
    if schematic.containers:
        drawn |= {cluster.path for cluster in schematic.clusters}

    scopes = [((), root)]
    scopes += [(cluster.path, cluster.type_name) for cluster in schematic.clusters]

    for prefix, owner_type in scopes:
        for connection in structure.connections_of(owner_type):
            source = _place(structure, owner_type, prefix, connection.source, drawn,
                            schematic.containers)
            target = _place(structure, owner_type, prefix, connection.target, drawn,
                            schematic.containers)
            if source is None or target is None:
                schematic.dropped.append(
                    f"{connection.source.text} → {connection.target.text} "
                    f"(in {owner_type})"
                )
                continue
            if source[0] == target[0] and source[1] == target[1]:
                continue
            schematic.edges.append(
                (source, target, connection.kind, connection.conditional)
            )


def _place(
    structure: Any, owner_type: str, prefix: tuple[str, ...], endpoint,
    drawn: set[tuple[str, ...]], containers: bool = False,
) -> tuple[tuple[str, ...], str] | None:
    """``(instance path, port)`` for an endpoint, or ``None`` if not in view.

    Walks the endpoint's handle chain through the component tree and clamps to
    the deepest box this view actually draws.  Two things need the clamp, and
    both are ordinary:

    * a virtual sequencer's ``vseqr.seqr_a`` names a *handle* one level below a
      component that has no children, so the edge belongs on ``vseqr``;
    * a connection reaching three levels down is real, and a single-level view
      draws it arriving at the box it can see.

    With *containers*, an endpoint that is a port of the root itself
    (``ap`` in the root's ``connect_phase``) places at path ``()``.
    """
    path = list(prefix)
    type_name = owner_type
    for handle in endpoint.path:
        child = next(
            (c for c in structure.children_of(type_name) if _handle_of(c) == handle),
            None,
        )
        if child is None:
            break
        path.append(handle)
        type_name = child.type_name

    # Clamp to the deepest drawn ancestor.
    while path and tuple(path) not in drawn:
        path.pop()
    if not path:
        if containers and not endpoint.path and endpoint.port:
            return (), endpoint.port
        return None
    return tuple(path), endpoint.port


def _prune_library_ports(schematic: Schematic) -> None:
    """Hide inherited library ports that nothing connects to.

    Found by the corpus gate, not by design: real ``uvm_driver`` gives every
    driver ``seq_item_port``, ``seq_item_prod_if`` **and** ``rsp_port``, of
    which one is the port anybody has ever drawn.  The stub's driver declares
    none, so against the stub this rule has nothing to do and the box looked
    right for the wrong reason.

    The line drawn is between what the reader wrote and what UVM gave them: a
    port declared in the user's own class is always shown, and an inherited
    library port is shown when something actually connects to it.  Whatever is
    hidden is counted, and the directive says so under the diagram --- the same
    obligation the tree's ``[opaque]`` nodes carry.
    """
    connected: set[tuple[tuple[str, ...], str]] = set()
    for source, target, _kind, _conditional in schematic.edges:
        connected.add(source)
        connected.add(target)

    def prune(path: tuple[str, ...], ports: tuple) -> tuple:
        kept = tuple(
            port for port in ports
            if not port.library or (path, port.name) in connected
        )
        schematic.hidden_ports += len(ports) - len(kept)
        return kept

    for node in schematic.nodes:
        node.ports = prune(node.path, node.ports)
    for cluster in schematic.clusters:
        cluster.ports = prune(cluster.path, cluster.ports)
    schematic.root_ports = prune((), schematic.root_ports)


def _apply_order(schematic: Schematic, order: list[str]) -> None:
    """Reorder top-level boxes *and* clusters, per ``:order:``.

    Clusters matter as much as boxes here --- ``:order: agent_a, agent_b`` is
    the documented example, and agents are the things drawn as clusters --- but
    they are ordered differently: a cluster's position comes from the order it
    is emitted in, while a box's comes from the invisible chain in its rank
    group.  Both are honoured from the one list.

    Names not mentioned keep their source order, after the ones that are: a
    partial ordering ("put the scoreboard first") is the common request, and
    refusing it because the list is incomplete would be pedantry.
    """
    if not order:
        return
    ranking = {name: position for position, name in enumerate(order)}

    def rank(handle: str, tiebreak: int) -> tuple[int, int]:
        return (ranking.get(handle, len(order)), tiebreak)

    top_level = [n for n in schematic.nodes if not n.parent]
    schematic.ordered = sorted(
        top_level, key=lambda n: rank(n.handle, top_level.index(n))
    )
    original = list(schematic.clusters)
    schematic.clusters.sort(key=lambda c: rank(c.handle, original.index(c)))


# -- DOT emission -------------------------------------------------------------


def build_schematic_dot(schematic: Schematic, newrank: bool = True) -> str:
    """Graphviz ``dot`` source for a resolved schematic.

    *newrank* off is the degraded mode: tier pinning goes with it, because
    ``rank=same`` across a cluster boundary is precisely what the old ranking
    algorithm refuses to do.  Everything else --- the clusters, the ports, the
    unconstrained TLM edges --- is emitted unchanged.
    """
    lines = [f"digraph {_ident(schematic.root)} {{"]
    if newrank:
        lines.append("  newrank=true;")
    lines += [
        "  rankdir=TB; compound=true;",
        '  graph [fontname="Helvetica", fontsize=11, ranksep=0.6, nodesep=0.4,',
        '         style=filled, fillcolor="#fbfbfd", color="#c8ccd8"];',
        '  node  [fontname="Helvetica", fontsize=10, shape=plaintext];',
        '  edge  [fontname="Helvetica", fontsize=8, arrowsize=0.7, '
        f'color="{_EDGE_DEFAULT[0]}"];',
    ]

    for node in schematic.nodes:
        if not node.parent:
            lines.append(f"  {node.dot_id} [label={_label(node, '#eef2ff')}];")

    for cluster in schematic.clusters:
        lines.append(f"  subgraph {cluster.dot_id} {{")
        label = f"<B>{_escape(cluster.handle)}</B> : {_escape(cluster.type_name)}"
        if cluster.conditional:
            label += " [conditional]"
        lines.append(f'    label=<{label}>; labelloc="t"; fontsize=10;')
        for node in cluster.members:
            lines.append(f"    {node.dot_id} [label={_label(node, '#fff7ed')}];")
        # Knob 4, inside the cluster: fix the left-to-right order of an agent's
        # components so the same agent never draws two different ways.
        if len(cluster.members) > 1:
            chain = " -> ".join(node.dot_id for node in cluster.members)
            lines.append(f"    {chain} [style=invis, weight=10];")
        lines.append("  }")

    if newrank:
        lines += _tier_lines(schematic)

    for (source, target, kind, conditional) in schematic.edges:
        lines.append(_edge_line(schematic, source, target, kind, conditional))

    lines.append("}")
    return "\n".join(lines)


def _tier_lines(schematic: Schematic) -> list[str]:
    """Knobs 3: the rank groups, and one invisible edge per tier boundary."""
    ordered = schematic.ordered
    top_level = ordered if ordered is not None else [
        n for n in schematic.nodes if not n.parent
    ]

    groups: list[list[_Node]] = []
    for tier in TIERS:
        members = [n for n in top_level if n.tier == tier]
        if tier == TIER_BOTTOM:
            # Cluster members are pinned with the agents they belong to, which
            # is what `newrank` exists to permit.  Taken in cluster order so the
            # rank group reads the way the diagram does.
            members += [
                node for cluster in schematic.clusters for node in cluster.members
            ]
        if members:
            groups.append(members)

    lines: list[str] = []
    for members in groups:
        ids = " ".join(f"{node.dot_id};" for node in members)
        lines.append(f"  {{ rank=same; {ids} }}")
    for above, below in zip(groups, groups[1:]):
        lines.append(f"  {above[0].dot_id} -> {below[0].dot_id} [style=invis];")

    # Knob 4 at the top level: hold the requested left-to-right order.
    if ordered is not None:
        for members in groups:
            if len(members) > 1:
                chain = " -> ".join(node.dot_id for node in members)
                lines.append(f"  {chain} [style=invis, weight=10];")
    return lines


def _edge_line(
    schematic: Schematic, source: tuple, target: tuple, kind: str, conditional: bool
) -> str:
    """One TLM edge --- and every one of them carries ``constraint=false``.

    Knob 2, and the single most important attribute in this module: without it
    an analysis connection ranks the scoreboard below the monitor that feeds
    it, which is the documented failure this layout was designed against.

    Deliberately unlabelled.  §7.5 identified edge labels as the weak point of
    the DVCon diagram, and there is nothing for one to say here that the boxes
    do not: an edge already leaves from a named port anchor and arrives at
    another.  A conditional connection is drawn dotted and explained once in a
    note, rather than repeating the word on every edge.
    """
    colour, style = _EDGE_STYLE.get(kind, _EDGE_DEFAULT)
    attrs = [
        f'color="{colour}"',
        f"style={'dotted' if conditional else style}",
        "constraint=false",
    ]
    return f"  {_port_ref(schematic, source)} -> {_port_ref(schematic, target)} " \
           f"[{', '.join(attrs)}];"


def _port_ref(schematic: Schematic, endpoint: tuple) -> str:
    path, port = endpoint
    node = schematic.node(path)
    if node is None:
        return _ident(".".join(path))
    if port and any(p.name == port for p in node.ports):
        return f"{node.dot_id}:{_ID_SAFE.sub('_', port)}"
    return node.dot_id


def _label(node: _Node, fill: str) -> str:
    """An HTML-like label: one row per port, then the component itself.

    Ports go above the name because analysis data flows *upward* in this
    layout, so an edge leaving a monitor leaves from the top of its box.
    """
    rows = [
        f'<TR><TD PORT="{_ID_SAFE.sub("_", port.name)}">'
        f'<FONT POINT-SIZE="8">{_escape(port.name)}</FONT></TD></TR>'
        for port in node.ports
    ]
    caption = f"<B>{_escape(node.handle)}</B>"
    caption += f'<BR/><FONT POINT-SIZE="8">{_escape(node.type_name)}</FONT>'
    if node.conditional:
        caption += '<BR/><FONT POINT-SIZE="7">[conditional]</FONT>'
    if node.state != STATE_OK:
        caption += f'<BR/><FONT POINT-SIZE="7">[{_escape(node.state)}]</FONT>'
    rows.append(f"<TR><TD>{caption}</TD></TR>")
    return (
        '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4" '
        f'BGCOLOR="{fill}">{"".join(rows)}</TABLE>>'
    )


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _ident(text: str) -> str:
    return _ID_SAFE.sub("_", str(text)) or "schematic"


# -- Diagram (ELK) ------------------------------------------------------------
#
# The ELK layout is left to right, so data flows the way it reads: a port
# (which sends) goes on a box's east side and an export or imp (which
# receives) on its west.  seq_item is the exception, because the driver pulls:
# ``drv.seq_item_port.connect(seqr.seq_item_export)`` is drawn from the
# sequencer's east side to the driver's west, the way the items go.
#
# :tier: still means something here, but less: ``top`` pins a component to
# the first column and ``bottom`` to the last.  The derived tiers aren't
# used, since ELK places by connectivity, which is what they approximated.

#: :tier: value -> ELK layer constraint.
_LAYER_BY_TIER = {TIER_TOP: "FIRST", TIER_BOTTOM: "LAST"}


def _port_side(port) -> str:
    receives = port.role in ("export", "imp")
    if port.link == LINK_SEQ_ITEM:
        receives = not receives
    return "WEST" if receives else "EAST"


def _box_id(path: tuple[str, ...]) -> str:
    return "/".join(path) or "@root"


def build_schematic_diagram(
    schematic: Schematic, tiers: dict[str, str] | None = None,
) -> "Diagram":
    """The schematic as a :class:`~sphinx_systemverilog.diagram.Diagram`.

    Best built from a schematic made with ``containers=True``, so connections
    at an agent's or the root's own ports are drawn.  *tiers* is the
    directive's ``:tier:`` (not the derived tiers).
    """
    from ..diagram import Box, Diagram, Edge, Port
    from ..diagram.sphinx import XREF

    overrides = tiers or {}
    ports_of: dict[str, set[str]] = {}

    def ports(path: tuple[str, ...], declared: tuple) -> list:
        bid = _box_id(path)
        ports_of[bid] = {p.name for p in declared}
        return [
            Port(f"{bid}:{p.name}", p.name, _port_side(p), p.link,
                 title=f"{p.name} : {p.type_name}" if p.type_name else p.name)
            for p in declared
        ]

    def flags(conditional: bool, state: str = STATE_OK) -> tuple[str, str]:
        tags = (["conditional"] if conditional else []) + \
            ([state] if state != STATE_OK else [])
        return "".join(f" [{t}]" for t in tags), "".join(
            " cond" if t == "conditional" else " opaque" for t in tags)

    def layer(handle: str, type_name: str) -> str:
        return _LAYER_BY_TIER.get(overrides.get(handle) or overrides.get(type_name), "")

    def leaf(node: _Node) -> "Box":
        tag, cls = flags(node.conditional, node.state)
        return Box(_box_id(node.path), node.handle, node.type_name + tag,
                   ports=ports(node.path, node.ports), cls="leaf" + cls,
                   href=XREF + node.type_name,
                   title=f"{node.handle} : {node.type_name}{tag}",
                   layer="" if node.parent else layer(node.handle, node.type_name))

    def cluster_box(cluster: _Cluster) -> "Box":
        tag, cls = flags(cluster.conditional)
        return Box(_box_id(cluster.path), cluster.handle, cluster.type_name + tag,
                   ports=ports(cluster.path, cluster.ports),
                   children=[leaf(n) for n in cluster.members], cls="cont" + cls,
                   href=XREF + cluster.type_name,
                   title=f"{cluster.handle} : {cluster.type_name}{tag}",
                   layer=layer(cluster.handle, cluster.type_name))

    # Top level in source order: a cluster stands where its first member was.
    items: list[tuple[str, Box]] = []
    clusters = {c.path: c for c in schematic.clusters}
    for node in schematic.nodes:
        if not node.parent:
            items.append((node.handle, leaf(node)))
        elif node.parent in clusters:
            c = clusters.pop(node.parent)
            items.append((c.handle, cluster_box(c)))
    if schematic.order:
        rank = {name: i for i, name in enumerate(schematic.order)}
        items = [it for _, it in sorted(
            enumerate(items), key=lambda x: (rank.get(x[1][0], len(rank)), x[0]))]

    root = Box(_box_id(()), schematic.root, cls="cont",
               ports=ports((), schematic.root_ports), children=[b for _, b in items])

    def end(endpoint: tuple) -> str:
        path, port = endpoint
        bid = _box_id(path)
        return f"{bid}:{port}" if port in ports_of.get(bid, ()) else bid

    # One hyperedge per (source, kind, conditional), so a fan-out is drawn as
    # one trunk with a junction dot.
    merged: dict[tuple, Edge] = {}
    for source, target, kind, conditional in schematic.edges:
        if kind == LINK_SEQ_ITEM:
            source, target = target, source
        a, b = end(source), end(target)
        if a == b:
            continue
        key = (a, kind, conditional)
        edge = merged.setdefault(key, Edge(a, [], kind, conditional=conditional))
        if b not in edge.targets:
            edge.targets.append(b)

    return Diagram(root, edges=list(merged.values()), model_order=bool(schematic.order))


# -- Graphviz capability ------------------------------------------------------


@lru_cache(maxsize=8)
def supports_newrank(dot_binary: str = "dot") -> bool:
    """Whether the available ``dot`` understands ``newrank``.

    Probed rather than assumed.  ``newrank`` has been in Graphviz since 2.30
    (2013), so this is very nearly always true --- but "very nearly always" is
    not a thing to hardcode into emitted source, because when it is false the
    result is not a worse diagram, it is a build that fails to lay out.

    A missing ``dot`` also answers ``False``.  That case produces no image
    either way (``sphinx.ext.graphviz`` warns and skips), and emitting the
    plainer graph keeps the DOT that *is* written into the build directory
    usable by hand.
    """
    try:
        result = subprocess.run(
            [dot_binary, "-V"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    text = f"{result.stdout} {result.stderr}"
    match = re.search(r"version\s+(\d+)\.(\d+)", text)
    if not match:
        return False
    return (int(match.group(1)), int(match.group(2))) >= _NEWRANK_SINCE
