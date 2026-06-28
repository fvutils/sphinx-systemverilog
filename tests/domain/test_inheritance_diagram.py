"""Tests for inheritance diagrams and ND rendering (P2-TEST-6)."""

from __future__ import annotations

import pytest
from sphinx.ext.graphviz import graphviz

from sphinx_systemverilog.autodoc.diagrams import build_inheritance_dot
from sphinx_systemverilog.model.index import build_index
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)], "sv_doc_style": "naturaldocs"}

pytestmark = pytest.mark.sphinx


def test_dot_contains_hierarchy_edges():
    idx = build_index(source_dirs=[str(FIXTURES)], doc_style="naturaldocs")
    dot = build_inheritance_dot(idx, idx.get("nd_pkg::nd_leaf"))
    assert '"nd_leaf" -> "nd_mid"' in dot
    assert '"nd_mid" -> "nd_base"' in dot


@pytest.mark.sphinx("html", testroot="nd", confoverrides=CONF)
def test_diagram_node_in_doctree(app):
    app.build()
    doctree = app.env.get_doctree("index")
    diagrams = list(doctree.findall(graphviz))
    assert len(diagrams) >= 1
    assert "nd_leaf" in diagrams[0]["code"]


@pytest.mark.sphinx("html", testroot="nd", confoverrides=CONF)
def test_group_rubrics_rendered(app):
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "Identification" in text
    assert "Operation" in text


@pytest.mark.sphinx("html", testroot="nd", confoverrides=CONF)
def test_naturaldocs_prose_rendered(app):
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "root of the nd_pkg hierarchy" in text
    # detached-block association: get_name's prose reached the method.
    assert "Returns the object name" in text


@pytest.mark.sphinx("html", testroot="nd", confoverrides=CONF)
def test_module_ports_rendered(app):
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "WIDTH" in text
    assert "counter width in bits" in text
