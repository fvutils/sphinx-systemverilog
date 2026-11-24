"""The neutral block-diagram model.

The UVM and RTL front ends each build a :class:`Diagram`; neither knows about
the layout engine.  :func:`~sphinx_systemverilog.diagram.elk.to_elk` turns a
diagram into ELK JSON, and the engine adapter lays it out.

Ids are global across one diagram: a port and a box may not share an id, and
an edge names its ends by id.  An edge may end on a box rather than a port
(for example a handle reference to an agent's sequencer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

SIDES = ("WEST", "EAST", "NORTH", "SOUTH")


@dataclass
class Port:
    """A connection point on a box's border.

    *kind* is free-form and only selects styling, for example ``analysis``,
    ``seq``, ``input``, ``output`` or ``bundle``.
    """

    id: str
    label: str = ""
    side: str = "EAST"
    kind: str = ""
    href: str = ""
    title: str = ""     # hover text


@dataclass
class Box:
    """A block: a component, an instance, or the diagram's root container.

    *sub* is the second line under the label, usually the type.  A box with
    children is drawn as a container around them.
    """

    id: str
    label: str
    sub: str = ""
    ports: list[Port] = field(default_factory=list)
    children: list["Box"] = field(default_factory=list)
    cls: str = ""
    href: str = ""
    title: str = ""

    def walk(self) -> Iterator["Box"]:
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Edge:
    """A connection from one source to one or more targets (a hyperedge).

    *priority* asks the layout to keep the edge short and straight; the RTL
    front end raises it for wide buses.
    """

    source: str
    targets: list[str]
    kind: str = ""
    label: str = ""
    conditional: bool = False
    priority: int = 0
    title: str = ""


@dataclass
class Bundle:
    """Several parallel connections drawn as one edge with a label.

    It is drawn from *source* to *targets*, usually bundle ports added for the
    purpose.  *members* keeps the connections it stands for, so a reader can
    expand or highlight them; they are not drawn.
    """

    source: str
    targets: list[str]
    members: list[Edge] = field(default_factory=list)
    label: str = ""
    kind: str = "bundle"
    priority: int = 0
    title: str = ""


@dataclass
class Diagram:
    """A root box, the edges between ports inside it, and layout hints.

    *model_order* makes the layout follow the order boxes and edges were
    added when it has to break a cycle, which is how a directive's
    ``:order:`` reaches the engine.
    """

    root: Box
    edges: list[Edge] = field(default_factory=list)
    bundles: list[Bundle] = field(default_factory=list)
    direction: str = "RIGHT"
    model_order: bool = False

    def boxes(self) -> Iterator[Box]:
        return self.root.walk()

    def validate(self) -> None:
        """Raise :class:`ValueError` on duplicate ids, bad sides or dangling edges."""
        ids: set[str] = set()

        def claim(i: str, what: str) -> None:
            if not i:
                raise ValueError(f"{what} has an empty id")
            if i in ids:
                raise ValueError(f"duplicate id {i!r}")
            ids.add(i)

        for b in self.boxes():
            claim(b.id, "box")
            for p in b.ports:
                claim(p.id, f"port of {b.id!r}")
                if p.side not in SIDES:
                    raise ValueError(f"port {p.id!r}: side {p.side!r} is not one of {SIDES}")
        for e in [*self.edges, *self.bundles]:
            if not e.targets:
                raise ValueError(f"edge from {e.source!r} has no targets")
            for end in (e.source, *e.targets):
                if end not in ids:
                    raise ValueError(f"edge end {end!r} is not a box or port in the diagram")
