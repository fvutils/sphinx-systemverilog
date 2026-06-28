"""'[source]' links to highlighted SystemVerilog source.

When ``sv_viewcode`` is enabled, every documented object with a known source
location gets a ``[source]`` link to a generated, syntax-highlighted listing of
its file, anchored at the declaration line.  Modeled on ``sphinx.ext.viewcode``
but driven by the source locations the model already captures.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import Any

from docutils import nodes
from sphinx import addnodes
from sphinx.util import logging

logger = logging.getLogger(__name__)

#: Page-name prefix for generated source listings.
_PAGE_PREFIX = "_sv_source"


def _norm(file_path: str) -> str:
    """Normalize a (possibly CWD-relative) source path to an absolute path."""
    return os.path.abspath(file_path)


def page_name(file_path: str) -> str:
    """Stable, URL-safe page name for a source file path."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", _norm(file_path)).strip("_")
    return posixpath.join(_PAGE_PREFIX, safe)


def _store(env: Any) -> dict[str, dict[int, str]]:
    if not hasattr(env, "sv_viewcode"):
        env.sv_viewcode = {}
    return env.sv_viewcode


def record(env: Any, file_path: str, line: int, anchor: str) -> None:
    """Record that *anchor* is documented at *file_path*:*line*."""
    _store(env).setdefault(_norm(file_path), {})[line] = anchor


def make_source_node(env: Any, file_path: str, line: int) -> nodes.Node | None:
    """Create the inline ``[source]`` reference node for a signature."""
    if not file_path:
        return None
    inline = nodes.inline("", "[source]", classes=["viewcode-link"])
    ref = nodes.reference("", "", inline, refuri="#", internal=True)
    # Custom attributes consumed by resolve_links (a plain reference is left
    # untouched by the standard domain/xref resolvers).
    ref["sv_viewcode_target"] = file_path
    ref["sv_viewcode_line"] = line
    return nodes.emphasis("", "", ref, classes=["sv-viewcode"])


def purge(app: Any, env: Any, docname: str) -> None:
    store = getattr(env, "sv_viewcode", None)
    if not store:
        return
    # Anchors are keyed by file, not docname; nothing per-doc to purge here.


def resolve_links(app: Any, doctree: nodes.document, fromdocname: str) -> None:
    """Resolve the ``sv-viewcode`` pending references to generated pages."""
    builder = app.builder
    if builder.format != "html":
        return
    for ref in list(doctree.findall(nodes.reference)):
        target = ref.get("sv_viewcode_target")
        if not target:
            continue
        pagename = page_name(target)
        try:
            uri = builder.get_relative_uri(fromdocname, pagename)
            ref["refuri"] = uri + "#svline-%d" % ref["sv_viewcode_line"]
        except Exception:
            # No page (e.g. non-HTML builder): drop the link, keep the text.
            ref.replace_self(ref.children)


def collect_pages(app: Any):
    """Yield a highlighted listing page for each documented source file."""
    env = app.env
    store = getattr(env, "sv_viewcode", None)
    if not store:
        return
    highlighter = app.builder.highlighter
    for file_path, lines in store.items():
        try:
            with open(file_path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError:
            continue
        body = _highlight_with_anchors(highlighter, source, lines)
        pagename = page_name(file_path)
        context = {
            "title": posixpath.basename(file_path),
            "body": f"<h1>{posixpath.basename(file_path)}</h1>\n{body}",
        }
        yield (pagename, context, "page.html")


def _highlight_with_anchors(
    highlighter: Any, source: str, lines: dict[int, str]
) -> str:
    """Highlight *source* and inject per-line anchors for documented lines."""
    try:
        highlighted = highlighter.highlight_block(source, "systemverilog", linenos=False)
    except Exception:
        highlighted = highlighter.highlight_block(source, "verilog", linenos=False)

    out: list[str] = []
    lineno = 1
    for raw in highlighted.splitlines():
        anchor = f'<span id="svline-{lineno}"></span>' if lineno in lines else ""
        out.append(anchor + raw)
        lineno += 1
    return "\n".join(out)
