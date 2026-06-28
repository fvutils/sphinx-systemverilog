"""Tests for the objects inventory / intersphinx export (P3-TEST-5)."""

from __future__ import annotations

import pytest

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_objects_inv_contains_sv_entries(app):
    app.build()
    from sphinx.util.inventory import InventoryFile

    inv_path = app.outdir / "objects.inv"
    assert inv_path.exists()
    with open(inv_path, "rb") as fh:
        inv = InventoryFile.load(fh, "http://example.test", lambda a, b: a + "/" + b)

    sv_domains = {k for k in inv if k.startswith("sv:")}
    assert "sv:class" in sv_domains
    assert "sample_pkg::sample_txn" in inv["sv:class"]


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_inventory_entry_points_at_anchor(app):
    app.build()
    from sphinx.util.inventory import InventoryFile

    with open(app.outdir / "objects.inv", "rb") as fh:
        inv = InventoryFile.load(fh, "http://example.test", lambda a, b: a + "/" + b)
    _proj, _ver, uri, _disp = inv["sv:class"]["sample_pkg::sample_txn"]
    assert "sv-sample_pkg-sample_txn" in uri
