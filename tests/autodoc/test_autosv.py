"""Integration tests for the auto* directives (P1-TEST-7)."""

from __future__ import annotations

import pytest
from sphinx import addnodes

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}

pytestmark = pytest.mark.sphinx


def _names(doctree):
    return {
        "".join(n.astext() for n in s.findall(addnodes.desc_name))
        for s in doctree.findall(addnodes.desc_signature)
    }


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_class_and_members_documented(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    # Class + its documented members.
    assert {"sample_txn", "addr", "data", "parity", "drive"} <= names


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_class_docstring_rendered(app):
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "Models a single read or write transfer" in text


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_param_fields_rendered(app):
    app.build()
    html = (app.outdir / "index.html").read_text()
    assert "bits to include in the parity calculation" in html
    assert "the computed parity bit" in html


@pytest.mark.sphinx("html", testroot="exclude", confoverrides=CONF)
def test_exclude_members(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    assert "parity" in names
    assert "drive" not in names


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_documented_inline_member_shown(app):
    app.build()
    # m_count is documented via an inline trailing comment, so it shows.
    names = _names(app.env.get_doctree("index"))
    assert "m_count" in names
