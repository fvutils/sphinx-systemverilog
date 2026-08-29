"""UML activity diagrams for UVM sequences.

The counterpart to :mod:`uvm_diagram`, and deliberately the opposite of it in
the one place they could have shared code.

The schematic's whole problem is that Graphviz treats an edge as a ranking
constraint, and a TLM connection is *not* an ordering; every edge there carries
``constraint=false`` so containment can decide the layout.  Here the edges
**are** the ordering --- a sequence is a control-flow object, and "this step
happens after that one" is exactly what a rank expresses --- so the default
behaviour is right and nothing is switched off.

The one exception is the loop back-edge, which is a genuine cycle and would
otherwise pull the end of a loop body above its beginning.  It is drawn with
``constraint=false`` for the same reason the schematic draws everything that
way, which is the only piece of the §7.3 lesson that carries over.

Shapes follow UML activity notation, so the picture is readable without a
legend:

* a filled circle starts, a ringed circle ends;
* a rounded box is a step, a plain box a transaction;
* a diamond is a decision, and every arm is labelled with the branch it takes;
* a solid bar is a fork or a join, and the join bar carries the join semantics
  read from ``StatementBlockKind`` rather than guessed;
* a dashed cluster is a loop, labelled with its controlling expression as
  written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..model.uvm import (
    ACT_ACTION,
    ACT_BRANCH,
    ACT_DECISION,
    ACT_DELAY,
    ACT_FORK,
    ACT_ITEM,
    ACT_LOOP,
    ACT_SEQUENCE,
    JOIN_ALL,
    JOIN_ANY,
    JOIN_NONE,
    UvmActivity,
    UvmSequence,
)

#: How each join flavour is written on the join bar.  `join_none` never gets a
#: bar at all --- the branches genuinely do not rejoin, and drawing one would
#: assert a synchronisation the source refuses.
_JOIN_LABELS = {JOIN_ALL: "join", JOIN_ANY: "join_any", JOIN_NONE: "join_none"}

#: Node styling by activity kind.  Kept as data so the shape vocabulary is
#: readable in one place rather than spread through the emitter.
_STYLES = {
    ACT_ACTION: 'shape=box, style="rounded,filled", fillcolor="#f4f5f7"',
    ACT_ITEM: 'shape=box, style="filled", fillcolor="#fef3c7", color="#b45309"',
    ACT_SEQUENCE: 'shape=box, style="rounded,filled", fillcolor="#dbeafe", '
                  'color="#2563eb"',
    ACT_DELAY: 'shape=box, style="rounded,filled", fillcolor="#ede9fe", '
               'color="#7c3aed"',
}

_DECISION = 'shape=diamond, style=filled, fillcolor="#fef9c3", color="#a16207"'
_MERGE = 'shape=diamond, style=filled, fillcolor="#e5e7eb", color="#9ca3af", ' \
         'width=0.25, height=0.25, label=""'
_BAR = 'shape=box, style=filled, fillcolor="#374151", color="#374151", ' \
       'width=1.4, height=0.06, fixedsize=true, label=""'
_TERMINAL = 'shape=circle, style=filled, fillcolor="#111827", color="#111827", ' \
            'width=0.22, fixedsize=true, label=""'
_FINAL = 'shape=doublecircle, style=filled, fillcolor="#111827", ' \
         'color="#111827", width=0.20, fixedsize=true, label=""'

#: Labels longer than this are wrapped rather than allowed to stretch a rank.
_WRAP = 28


@dataclass
class ActivityDiagram:
    """The rendering plan for one sequence, and what it left out."""

    #: The sequence at the root.
    sequence: UvmSequence | None = None
    #: Sub-sequence type names drawn as their own clusters, in first-seen order.
    expanded: list[str] = field(default_factory=list)
    #: Sub-sequence type names present as nodes but not expanded.
    unexpanded: list[str] = field(default_factory=list)
    #: Sub-sequence type names that could not be resolved to a sequence.
    unresolved: list[str] = field(default_factory=list)


def escape(text: str) -> str:
    """Quote a string for a DOT label.

    Newlines become DOT's ``\\n`` *after* the backslash doubling, not before:
    doing it the other way round escapes the escape and puts a literal
    ``\\n`` in the picture, which is exactly what the first version did.
    """
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return escaped.replace("\n", "\\n")


def wrap(text: str, width: int = _WRAP) -> str:
    """Break a long label across lines, on spaces where there are any."""
    if len(text) <= width:
        return text
    words, lines, current = text.split(" "), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)


class _Canvas:
    """A DOT body under construction, with nested cluster sinks.

    Node declarations must appear *inside* the subgraph that owns them, while
    edges may be written anywhere; keeping one sink stack for declarations and a
    flat list for edges is what lets the recursive walk emit both in one pass.
    """

    def __init__(self) -> None:
        self._stack: list[list[str]] = [[]]
        self._edges: list[str] = []
        self._counter = 0

    def node(self, attrs: str, label: str | None = None) -> str:
        self._counter += 1
        name = f"n{self._counter}"
        parts = [attrs]
        if label is not None:
            parts.append(f'label="{escape(wrap(label))}"')
        self._stack[-1].append(f'{name} [{", ".join(parts)}];')
        return name

    def edge(self, tail: str, head: str, attrs: str = "") -> None:
        suffix = f" [{attrs}]" if attrs else ""
        self._edges.append(f"{tail} -> {head}{suffix};")

    def open_cluster(self, index: int, label: str, style: str) -> None:
        self._stack[-1].append(f"subgraph cluster_{index} {{")
        self._stack[-1].append(f"  {style}")
        self._stack[-1].append(f'  label="{escape(wrap(label))}";')
        self._stack.append([])

    def close_cluster(self) -> None:
        inner = self._stack.pop()
        self._stack[-1].extend(f"  {line}" for line in inner)
        self._stack[-1].append("}")

    def render(self) -> list[str]:
        return [*self._stack[0], *self._edges]


class _Builder:
    def __init__(
        self, canvas: _Canvas, subsequences: dict[str, UvmSequence],
        diagram: ActivityDiagram, depth: int,
    ) -> None:
        self.canvas = canvas
        self.subsequences = subsequences
        self.diagram = diagram
        self.depth = depth
        self.clusters = 0

    # -- sequencing -----------------------------------------------------------

    def chain(
        self, activities: Iterable[UvmActivity], level: int
    ) -> tuple[str, str] | None:
        r"""Render a run of activities in order; return its entry and exit.

        *level* counts **sub-sequence** nesting, not statement nesting: a
        sub-sequence started three ``if``\ s deep is still one level down, and
        counting braces instead would make ``:depth:`` mean something no reader
        could predict.
        """
        entry = exit_node = None
        for activity in activities:
            span = self.node_for(activity, level)
            if span is None:
                continue
            head, tail = span
            if entry is None:
                entry = head
            else:
                self.canvas.edge(exit_node, head)
            exit_node = tail
        return (entry, exit_node) if entry is not None else None

    def node_for(
        self, activity: UvmActivity, level: int
    ) -> tuple[str, str] | None:
        kind = activity.kind
        if kind == ACT_DECISION:
            return self.decision(activity, level)
        if kind == ACT_FORK:
            return self.fork(activity, level)
        if kind == ACT_LOOP:
            return self.loop(activity, level)
        if kind == ACT_SEQUENCE:
            return self.subsequence(activity, level)

        label = activity.label or kind
        if kind == ACT_ITEM:
            label = f"{activity.label}: {activity.type_name}" \
                if activity.type_name else activity.label
        if activity.macro:
            label = f"{label}\n`{activity.macro}"
        name = self.canvas.node(_STYLES.get(kind, _STYLES[ACT_ACTION]), label)
        return name, name

    # -- constructs -----------------------------------------------------------

    def decision(self, activity: UvmActivity, level: int) -> tuple[str, str]:
        head = self.canvas.node(_DECISION, activity.label or "?")
        merge = self.canvas.node(_MERGE)
        branches = list(activity.children) or [
            UvmActivity(kind=ACT_BRANCH, label="yes")
        ]
        if len(branches) == 1 and branches[0].label == "yes":
            # An `if` with no `else` still has two outcomes.  Drawing only the
            # one that was written would say the branch always runs.
            branches.append(UvmActivity(kind=ACT_BRANCH, label="no"))
        for branch in branches:
            span = self.chain(branch.children, level)
            if span is None:
                # An arm that does nothing still has to be drawn, or the
                # diagram claims the decision has only one outcome.
                self.canvas.edge(head, merge, f'label="{escape(branch.label)}"')
                continue
            self.canvas.edge(head, span[0], f'label="{escape(branch.label)}"')
            self.canvas.edge(span[1], merge)
        return head, merge

    def fork(self, activity: UvmActivity, level: int) -> tuple[str, str]:
        bar = self.canvas.node(_BAR)
        detached = activity.join == JOIN_NONE
        # The join semantics ride on the bar as an `xlabel`, which Graphviz
        # places beside a node without giving it width.  A `label` would be
        # inside a bar 0.06 high, and an edge label would attach the word to
        # one branch when it describes all of them.
        join = None if detached else self.canvas.node(
            _BAR + f', xlabel="{escape(_JOIN_LABELS.get(activity.join, ""))}"'
        )
        tails: list[str] = []
        for branch in activity.children:
            span = self.chain(branch.children, level)
            label = f'label="{escape(branch.label)}"'
            if span is None:
                if join is not None:
                    self.canvas.edge(bar, join, label)
                continue
            self.canvas.edge(bar, span[0], label)
            tails.append(span[1])
        if join is None:
            # `join_none`: the branches run on, and the flow continues from the
            # fork bar itself.  Nothing rejoins, so nothing is drawn rejoining.
            return bar, bar
        for tail in tails:
            self.canvas.edge(tail, join)
        if not tails:
            # Every branch was empty.  The bars still have to be connected, or
            # the fork floats away from the flow it belongs to.
            self.canvas.edge(bar, join, "style=invis")
        return bar, join

    def loop(self, activity: UvmActivity, level: int) -> tuple[str, str] | None:
        self.clusters += 1
        index = self.clusters
        self.canvas.open_cluster(
            index, activity.label or "loop",
            'style="dashed,rounded"; color="#6b7280"; fontsize=10; '
            'fontcolor="#374151";',
        )
        span = self.chain(activity.children, level)
        self.canvas.close_cluster()
        if span is None:
            return None
        entry, exit_node = span
        # The one edge in this diagram that must not rank: a back-edge is a real
        # cycle, and left as a constraint it drags the end of the body above its
        # start.  Drawn even when the body is a single step, which renders as a
        # self-loop: a reader should not have to work out why one loop has an
        # arrow and the next one does not.
        self.canvas.edge(
            exit_node, entry,
            'constraint=false, style=dashed, color="#6b7280"',
        )
        return entry, exit_node

    def subsequence(self, activity: UvmActivity, level: int) -> tuple[str, str]:
        label = activity.type_name or activity.label
        target = self.subsequences.get(activity.type_name)
        expandable = (
            level < self.depth
            and target is not None
            and target.overridden
            and target.body
        )
        if activity.type_name:
            if target is None:
                _remember(self.diagram.unresolved, activity.type_name)
            elif expandable:
                _remember(self.diagram.expanded, activity.type_name)
            else:
                _remember(self.diagram.unexpanded, activity.type_name)

        if not expandable:
            text = f"{activity.label}: {label}" if activity.label else label
            if activity.macro:
                text = f"{text}\n`{activity.macro}"
            name = self.canvas.node(_STYLES[ACT_SEQUENCE], text)
            return name, name

        self.clusters += 1
        index = self.clusters
        self.canvas.open_cluster(
            index, f"{activity.label}: {label}" if activity.label else label,
            'style="rounded,filled"; fillcolor="#eff6ff"; color="#2563eb"; '
            'fontsize=10; fontcolor="#1e3a8a";',
        )
        span = self.chain(target.body, level + 1)
        self.canvas.close_cluster()
        if span is None:
            name = self.canvas.node(_STYLES[ACT_SEQUENCE], label)
            return name, name
        return span


def _remember(store: list[str], value: str) -> None:
    if value not in store:
        store.append(value)


def build_activity_dot(
    sequence: UvmSequence,
    subsequences: dict[str, UvmSequence] | None = None,
    depth: int = 1,
) -> tuple[str, ActivityDiagram]:
    """Render *sequence* as UML activity DOT, with what was left out.

    *depth* counts levels of sub-sequence expansion: 1 draws sub-sequences as
    single boxes, 2 opens each of them, and so on.
    """
    diagram = ActivityDiagram(sequence=sequence)
    canvas = _Canvas()
    builder = _Builder(canvas, subsequences or {}, diagram, depth)

    start = canvas.node(_TERMINAL)
    span = builder.chain(sequence.body, 1)
    end = canvas.node(_FINAL)
    if span is None:
        canvas.edge(start, end)
    else:
        canvas.edge(start, span[0])
        canvas.edge(span[1], end)

    lines = [
        "digraph uvm_activity {",
        "  rankdir=TB;",
        "  compound=true;",
        '  bgcolor="transparent";',
        '  node [fontname="Helvetica,Arial,sans-serif", fontsize=10];',
        '  edge [fontname="Helvetica,Arial,sans-serif", fontsize=9, '
        'color="#4b5563"];',
        "  nodesep=0.35;",
        "  ranksep=0.35;",
    ]
    lines += [f"  {line}" for line in canvas.render()]
    lines.append("}")
    return "\n".join(lines), diagram
