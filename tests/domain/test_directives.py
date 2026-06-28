"""Integration tests for the sv domain directives (P1-TEST-6)."""

from __future__ import annotations

import pytest
from sphinx import addnodes

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_manual_directive_creates_object(app):
    app.build()
    domain = app.env.get_domain("sv")
    assert "manual_pkg::manual_class" in domain.objects
    docname, anchor, kind = domain.objects["manual_pkg::manual_class"]
    assert kind == "class"
    assert anchor == "sv-manual_pkg-manual_class"


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_signature_nodes(app):
    app.build()
    doctree = app.env.get_doctree("index")
    sigs = list(doctree.findall(addnodes.desc_signature))
    names = {
        "".join(n.astext() for n in s.findall(addnodes.desc_name))
        for s in sigs
    }
    assert "manual_class" in names
    assert "sample_txn" in names


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_index_entries_present(app):
    app.build()
    doctree = app.env.get_doctree("index")
    index_nodes = list(doctree.findall(addnodes.index))
    entries = [e for node in index_nodes for e in node["entries"]]
    assert any("manual_class" in e[1] for e in entries)


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_permalink_anchor_in_html(app):
    app.build()
    html = (app.outdir / "index.html").read_text()
    assert 'id="sv-manual_pkg-manual_class"' in html
    assert 'id="sv-sample_pkg-sample_txn"' in html


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_no_build_warnings(app, warning):
    app.build()
    warnings = warning.getvalue()
    assert "WARNING" not in warnings, warnings
