"""The instance diagram, now fed by the lazy structure walk (M1-IMPL-11).

The diagram is the one user-visible thing M1 changes: it renders the same shape
as before, but on a design containing generate blocks or instance arrays it now
renders the *whole* design rather than silently omitting most of it.
"""

from __future__ import annotations

import pytest
from sphinx.ext.graphviz import graphviz

from sphinx_systemverilog.autodoc.diagrams import build_instance_dot
from sphinx_systemverilog.model.index import build_index
from tests.conftest import DESIGN

CONF = {"sv_source_dirs": [str(DESIGN)]}


@pytest.mark.unit
def test_dot_includes_generate_and_array_children():
    structure = build_index(source_dirs=[str(DESIGN)], use_cache=False).structure

    dot = build_instance_dot(structure.edges, "soc")

    assert '"soc" -> "cluster"' in dot
    # Both of these are reachable only through a generate block.
    assert '"cluster" -> "lane"' in dot
    assert '"lane" -> "leaf"' in dot
    assert 'label="g_lp[*].u_g"' in dot
    # The instance array reports its multiplicity rather than vanishing.
    assert 'label="u_l[3:0] (×4)"' in dot


@pytest.mark.unit
def test_dot_still_accepts_the_legacy_tuple_shape():
    edges = {"a": [("u_b", "b")], "b": [("u_c", "c")]}

    dot = build_instance_dot(edges, "a")

    assert '"a" -> "b" [label="u_b"]' in dot
    assert '"b" -> "c"' in dot


@pytest.mark.sphinx
@pytest.mark.sphinx("html", testroot="design", confoverrides=CONF)
def test_diagram_renders_in_a_real_build(app, warning):
    app.build()

    doctree = app.env.get_doctree("index")
    diagrams = [d for d in doctree.findall(graphviz) if "instances" in d["code"]]

    assert diagrams
    assert '"cluster" -> "lane"' in diagrams[0]["code"]
    assert "no instantiation hierarchy" not in warning.getvalue()


@pytest.mark.sphinx
@pytest.mark.sphinx("html", testroot="design", confoverrides=CONF)
def test_module_docs_are_unaffected(app):
    """M1 changes structure only; the module page renders as it always did."""
    app.build()

    text = (app.outdir / "index.html").read_text()
    assert "soc" in text
