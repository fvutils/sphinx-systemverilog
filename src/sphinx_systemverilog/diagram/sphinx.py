"""Block diagrams in Sphinx: an inline-SVG node with a Graphviz fallback.

A directive draws a :class:`~sphinx_systemverilog.diagram.Diagram` with
:func:`draw_node`.  The result is an :class:`sv_diagram` node holding the
SVG, with the Graphviz rendering of the same diagram as its child:

* HTML builders write the SVG inline and skip the child;
* every other builder (LaTeX, text, man, ...) ignores the SVG and renders the
  child, so PDF output keeps today's Graphviz diagrams.

When no layout engine can run (``sv_diagram_layout = "graphviz"``, or elkjs
missing from a source checkout) the directive gets only the Graphviz node.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
from typing import Any

from docutils import nodes
from sphinx.util import logging
from sphinx.util.fileutil import copy_asset_file

from .elk import to_elk
from .engine import LayoutError, get_engine, layout, static_file, unavailable_reason
from .model import Diagram

logger = logging.getLogger(__name__)

CSS = "sv-diagram.css"

#: ``href`` prefix for a box that links to a documented SystemVerilog object:
#: ``svref:my_pkg::my_agent``.  Resolved through the ``sv`` domain when the
#: page is written; a box whose target isn't documented loses its link.
XREF = "svref:"

_XREF_RE = re.compile(r'<a href="svref:([^"]*)">(.*?)</a>', re.S)

_warned_unavailable = False


class sv_diagram(nodes.General, nodes.Element):
    """An ELK-laid-out diagram: ``svg`` for HTML, children for everything else."""


def _visit_html(self: Any, node: sv_diagram) -> None:
    alt = node.get("alt", "")
    self.body.append(f'<div class="sv-diagram" title="{self.attval(alt)}">'
                     if alt else '<div class="sv-diagram">')
    self.body.append(_resolve_links(self.builder, node["svg"]))
    self.body.append("</div>\n")
    raise nodes.SkipNode


def _resolve_links(builder: Any, svg: str) -> str:
    """Replace ``svref:`` hrefs with relative URLs, or drop the link."""
    if XREF not in svg:
        return svg
    domain = builder.env.get_domain("sv")
    here = builder.current_docname

    def sub(m: re.Match) -> str:
        target = html.unescape(m.group(1)).split("#", 1)[0].strip()
        found = _find_type(domain, target) if target else None
        if found is None:
            return m.group(2)
        docname, anchor, _kind = found
        uri = builder.get_relative_uri(here, docname) + "#" + anchor
        return f'<a href="{html.escape(uri)}">{m.group(2)}</a>'

    return _XREF_RE.sub(sub, svg)


#: What a box can link to: a box is always an instance of one of these.
_BOX_KINDS = ("class", "module", "interface", "program")


def _find_type(domain: Any, target: str) -> tuple | None:
    """``(docname, anchor, kind)`` of the type *target* names, or None.

    Like the domain's own lookup (exact name, then a unique ``::`` suffix),
    but only over types: a module ``decode`` must not resolve to a method
    ``uvm_reg_cbs::decode``.
    """
    hit = domain.objects.get(target)
    if hit is not None and hit[2] in _BOX_KINDS:
        return hit
    hits = [fn for fn in domain.candidates(target)
            if (fn == target or fn.endswith("::" + target))
            and domain.objects[fn][2] in _BOX_KINDS]
    return domain.objects[hits[0]] if len(hits) == 1 else None


def _visit_other(self: Any, node: sv_diagram) -> None:
    pass


def _depart_other(self: Any, node: sv_diagram) -> None:
    pass


def draw_node(env: Any, diagram: Diagram, fallback: list[nodes.Node],
              alt: str, location: Any, *, graphviz: bool = True,
              ) -> tuple[list[nodes.Node], str]:
    """Lay out and render *diagram*; return ``(nodes, why_not)``.

    On success the nodes are one :class:`sv_diagram` wrapping *fallback* and
    *why_not* is empty.  Otherwise the nodes are *fallback* itself and
    *why_not* says why ELK wasn't used, for a note under the diagram.

    ``graphviz=False`` is for a diagram with no Graphviz drawing (the RTL
    block diagram): *fallback* is then only a placeholder, so
    ``sv_diagram_layout = "graphviz"`` doesn't apply to it.
    """
    global _warned_unavailable
    if graphviz and env.config.sv_diagram_layout == "graphviz":
        return fallback, ""
    engine = get_engine()
    if engine is None:
        why = unavailable_reason()
        if not _warned_unavailable:
            _warned_unavailable = True
            logger.warning("sphinx-systemverilog: block diagrams fall back to "
                           "Graphviz: %s", why, type="systemverilog",
                           subtype="diagram", location=location)
        return fallback, why
    try:
        graph = to_elk(diagram)
        laid = layout(graph, engine, os.path.join(env.doctreedir, "sv-diagram-cache"))
        prefix = "svd" + hashlib.sha256(
            f"{env.docname}\0{alt}\0{location}".encode()).hexdigest()[:10]
        svg = engine.render(laid, {"idPrefix": prefix, "label": alt})
    except (LayoutError, ValueError) as e:
        logger.warning("sphinx-systemverilog: %s: ELK layout failed, drawn with "
                       "Graphviz instead: %s", alt, e, type="systemverilog",
                       subtype="diagram", location=location)
        return fallback, f"the ELK layout failed ({e})"
    node = sv_diagram(svg=svg, alt=alt)
    node.extend(fallback)
    return [node], ""


def _copy_css(app: Any, exc: Exception | None) -> None:
    if exc is None and app.builder.format == "html":
        with _as_path(CSS) as src:
            copy_asset_file(src, os.path.join(app.outdir, "_static"))


def _as_path(name: str) -> Any:
    from importlib import resources
    return resources.as_file(static_file(name))


def setup(app: Any) -> None:
    """Register the node and the stylesheet (the config value is in config.py)."""
    pair = (_visit_other, _depart_other)
    app.add_node(sv_diagram, html=(_visit_html, None), latex=pair, text=pair,
                 man=pair, texinfo=pair)
    app.add_css_file(CSS)
    app.connect("build-finished", _copy_css)
