"""Tests for :inherited-members: (P3-TEST-2)."""

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


@pytest.mark.sphinx("html", testroot="inherited", confoverrides=CONF)
def test_inherited_members_shown(app):
    app.build()
    doctree = app.env.get_doctree("index")
    names = _names(doctree)
    # nd_leaf's own member plus inherited get_name/set_name from nd_base.
    assert "run" in names
    assert "get_name" in names
    assert "set_name" in names


@pytest.mark.sphinx("html", testroot="inherited", confoverrides=CONF)
def test_inherited_rubric_present(app):
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "Inherited from nd_base" in text
