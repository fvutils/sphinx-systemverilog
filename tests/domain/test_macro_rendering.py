"""How a ``\\`define`` is named and rendered.

A macro's signature is ``\\`define NAME(args) body``, so the generic
"first token is the name" rule made every macro in a project resolve to the name
``\\`define``.  They then shared one anchor and one inventory entry, and a page
built with ``:kinds: macro`` published one of them.
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_systemverilog.domain import _macro_tail, _signature_name
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,expected",
    [
        ("`define SAMPLE_WIDTH 32", "SAMPLE_WIDTH"),
        ("`define SAMPLE_MK(T, name) T name = new()", "SAMPLE_MK"),
        # No body.
        ("`define GUARD", "GUARD"),
        # No space between the name and its formals.
        ("`define DEBUG(x) $display x", "DEBUG"),
        # Degenerate input must not raise.
        ("`define", "`define"),
        ("", ""),
    ],
)
def test_macro_name_is_the_defined_name(sig, expected):
    assert _signature_name(sig, "macro") == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,name,expected",
    [
        ("`define SAMPLE_WIDTH 32", "SAMPLE_WIDTH", " 32"),
        ("`define SAMPLE_MK(T, name) T x", "SAMPLE_MK", "(T, name) T x"),
        ("`define GUARD", "GUARD", ""),
    ],
)
def test_macro_tail_is_everything_after_the_name(sig, name, expected):
    assert _macro_tail(sig, name) == expected


@pytest.mark.sphinx("html", testroot="macros", confoverrides=CONF)
def test_each_macro_gets_its_own_target(app):
    """Distinct names mean distinct anchors -- the collision this guards."""
    app.build()
    doctree = app.env.get_doctree("index")
    ids = [
        sig["ids"][0]
        for sig in doctree.findall(addnodes.desc_signature)
        if sig["ids"]
    ]
    assert "sv-SAMPLE_WIDTH" in ids, ids
    assert "sv-SAMPLE_MK" in ids, ids
    assert len(set(ids)) == len(ids), ids


@pytest.mark.sphinx("html", testroot="macros", confoverrides=CONF)
def test_macro_signature_shows_formals_and_body(app):
    app.build()
    doctree = app.env.get_doctree("index")
    rendered = {
        sig.astext().split("[source]")[0].strip()
        for sig in doctree.findall(addnodes.desc_signature)
    }
    assert any(s.startswith("macro SAMPLE_MK(T, name)") for s in rendered), rendered
    # The `define keyword is dropped: the kind label already carries it.
    assert not any("`define" in s for s in rendered), rendered
