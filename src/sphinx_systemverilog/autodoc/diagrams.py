"""Class inheritance diagrams, rendered via ``sphinx.ext.graphviz``.

Edges come from the resolved ``extends`` relationships captured in the
:class:`~sphinx_systemverilog.model.index.SvIndex`.  If Graphviz's ``dot`` is not
installed the graphviz extension degrades gracefully (it emits a warning and
skips the image); the directive itself always produces a valid node.
"""

from __future__ import annotations

from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx.ext.graphviz import graphviz
from sphinx.util import logging

logger = logging.getLogger(__name__)


class SvInheritanceDiagram(Directive):
    """``.. sv:inheritance-diagram:: pkg::class`` -> a class hierarchy graph."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        target = self.arguments[0].strip()
        index = getattr(env, "sv_index", None)
        if index is None:
            return []
        obj = index.get(target)
        if obj is None or obj.kind != "class":
            logger.warning(
                "sphinx-systemverilog: inheritance-diagram target %r is not a "
                "documented class", target, type="systemverilog",
                location=(env.docname, self.lineno),
            )
            return []

        dot = build_inheritance_dot(index, obj)
        node = graphviz()
        node["code"] = dot
        node["options"] = {"docname": env.docname}
        node["alt"] = f"Inheritance diagram of {obj.name}"
        return [node]


def build_inheritance_dot(index: Any, target: Any) -> str:
    """Return Graphviz ``dot`` source for *target*'s local class hierarchy."""
    classes = _class_by_name(index)
    nodes_in: set[str] = set()
    edges: set[tuple[str, str]] = set()

    # Ancestors: walk the extends chain upward.
    cur = target
    seen = set()
    while cur is not None and cur.name not in seen:
        seen.add(cur.name)
        nodes_in.add(cur.name)
        base = cur.extends
        if base:
            nodes_in.add(base)
            edges.add((cur.name, base))
        cur = classes.get(base) if base else None

    # Descendants: any class whose extends chain reaches the target.
    for cls in classes.values():
        chain = []
        walk = cls
        guard = set()
        while walk is not None and walk.name not in guard:
            guard.add(walk.name)
            chain.append(walk.name)
            if walk.extends == target.name:
                for child_name in chain:
                    nodes_in.add(child_name)
                edges.add((cls.name, cls.extends))
                # add intermediate edges along the chain
                break
            walk = classes.get(walk.extends) if walk.extends else None

    lines = ["digraph inheritance {", "  rankdir=BT;",
             '  node [shape=box, fontsize=10, height=0.25];',
             '  edge [arrowsize=0.7];']
    for name in sorted(nodes_in):
        attrs = ' style=filled fillcolor="#e8e8e8"' if name == target.name else ""
        lines.append(f'  "{name}" [label="{name}"{attrs}];')
    for derived, base in sorted(edges):
        lines.append(f'  "{derived}" -> "{base}";')
    lines.append("}")
    return "\n".join(lines)


def _class_by_name(index: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for root in index.roots:
        for obj in root.walk():
            if obj.kind == "class":
                out.setdefault(obj.name, obj)
    return out


class SvInstanceDiagram(Directive):
    """``.. sv:instance-diagram:: top`` -> a module instantiation hierarchy."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        top = self.arguments[0].strip().split("::")[-1]
        index = getattr(env, "sv_index", None)
        if index is None:
            return []
        edges = getattr(index, "instance_edges", {})
        if top not in edges:
            logger.warning(
                "sphinx-systemverilog: no instantiation hierarchy for module %r "
                "(is it a top-level design module?)", top, type="systemverilog",
                location=(env.docname, self.lineno),
            )
            return []
        node = graphviz()
        node["code"] = build_instance_dot(edges, top)
        node["options"] = {"docname": env.docname}
        node["alt"] = f"Instance diagram of {top}"
        return [node]


def build_instance_dot(edges: dict, top: str) -> str:
    """Graphviz ``dot`` for the structural composition reachable from *top*."""
    lines = ["digraph instances {", "  rankdir=TB;",
             '  node [shape=box, fontsize=10, height=0.25];',
             '  edge [arrowsize=0.7, fontsize=8];']
    nodes_in: set[str] = set()
    drawn: set[tuple[str, str, str]] = set()
    queue = [top]
    visited: set[str] = set()
    while queue:
        mod = queue.pop()
        if mod in visited:
            continue
        visited.add(mod)
        nodes_in.add(mod)
        for inst_name, child_type in edges.get(mod, []):
            nodes_in.add(child_type)
            key = (mod, child_type, inst_name)
            if key not in drawn:
                drawn.add(key)
                lines.append(
                    f'  "{mod}" -> "{child_type}" [label="{inst_name}"];'
                )
            queue.append(child_type)
    for name in sorted(nodes_in):
        attrs = ' style=filled fillcolor="#e8e8e8"' if name == top else ""
        lines.append(f'  "{name}" [label="{name}"{attrs}];')
    lines.append("}")
    return "\n".join(lines)
