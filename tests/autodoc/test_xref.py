"""Cross-reference resolution tests (P1-TEST-8)."""

from __future__ import annotations

import pytest

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_qualified_and_bare_refs_resolve(app):
    app.build()
    html = (app.outdir / "index.html").read_text()
    # Both the qualified and bare references should become internal links.
    assert 'href="#sv-sample_pkg-sample_base"' in html
    assert 'href="#sv-sample_pkg-sample_txn"' in html


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_method_ref_resolves(app):
    app.build()
    html = (app.outdir / "index.html").read_text()
    assert 'href="#sv-sample_pkg-sample_txn-parity"' in html


@pytest.mark.sphinx("html", testroot="unknown", confoverrides=CONF)
def test_unknown_ref_warns(app, warning):
    app.build()
    assert "nonexistent_thing" in warning.getvalue()
