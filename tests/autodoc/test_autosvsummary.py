"""Tests for the autosvsummary whole-tree directive (P3-TEST-3)."""

from __future__ import annotations

import pytest
from sphinx import addnodes

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)], "sv_doc_style": "auto"}

pytestmark = pytest.mark.sphinx


def _names(doctree):
    return [
        "".join(n.astext() for n in s.findall(addnodes.desc_name))
        for s in doctree.findall(addnodes.desc_signature)
    ]


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_documents_classes_in_scope(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    # :kinds: class :packages: nd_pkg -> the three nd_pkg classes, with members.
    assert {"nd_base", "nd_mid", "nd_leaf"} <= set(names)
    assert "get_name" in names  # members included by default


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_scope_excludes_other_packages(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    # sample_pkg / dox_pkg classes are out of the nd_pkg scope.
    assert "sample_txn" not in names
    assert "dox_txn" not in names
