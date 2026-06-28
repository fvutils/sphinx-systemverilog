"""Tests for structural instance diagrams (P4-TEST-1)."""

from __future__ import annotations

import pytest
from sphinx.ext.graphviz import graphviz

from sphinx_systemverilog.autodoc.diagrams import build_instance_dot
from sphinx_systemverilog.model.index import build_index
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


def test_instance_edges_captured():
    idx = build_index(source_dirs=[str(FIXTURES)], use_cache=False)
    edges = idx.instance_edges
    assert ("u_mid0", "rtl_mid") in edges["rtl_top"]
    assert ("u_solo", "rtl_leaf") in edges["rtl_top"]
    assert ("u_leaf", "rtl_leaf") in edges["rtl_mid"]


def test_instance_dot_hierarchy():
    idx = build_index(source_dirs=[str(FIXTURES)], use_cache=False)
    dot = build_instance_dot(idx.instance_edges, "rtl_top")
    assert '"rtl_top" -> "rtl_mid"' in dot
    assert '"rtl_mid" -> "rtl_leaf"' in dot
    assert 'label="u_mid0"' in dot


@pytest.mark.sphinx("html", testroot="rtl", confoverrides=CONF)
def test_instance_diagram_node_in_doctree(app):
    app.build()
    doctree = app.env.get_doctree("index")
    diagrams = list(doctree.findall(graphviz))
    assert any("instances" in d["code"] for d in diagrams)
