"""Tests for viewcode [source] links (P3-TEST-4)."""

from __future__ import annotations

import pytest

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="viewcode", confoverrides=CONF)
def test_source_links_present(app):
    app.build()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    links = [a.get("href") for a in soup.select("em.sv-viewcode a")]
    assert links, "no [source] links rendered"
    assert all("_sv_source/" in href and "#svline-" in href for href in links)


@pytest.mark.sphinx("html", testroot="viewcode", confoverrides=CONF)
def test_source_page_generated_with_anchor(app):
    app.build()
    pages = list((app.outdir / "_sv_source").glob("*.html"))
    assert pages, "no source listing page generated"
    text = pages[0].read_text()
    assert 'id="svline-' in text


@pytest.mark.sphinx(
    "html", testroot="viewcode",
    confoverrides={**CONF, "sv_viewcode": False},
    freshenv=True,
)
def test_viewcode_disabled(app):
    app.build()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup((app.outdir / "index.html").read_text(), "html.parser")
    # With viewcode off, no [source] links are emitted into the page.
    assert not soup.select("em.sv-viewcode")
