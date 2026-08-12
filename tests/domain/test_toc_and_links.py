"""TOC entries for documented objects, and linked base classes.

Objects only reach the sidebar if ``_object_hierarchy_parts`` can name them at
the time Sphinx asks, which is *before* the target ids exist -- hence the
``sv_fullname`` stash that these tests pin down.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from sphinx import addnodes

from sphinx_systemverilog.domain import _type_xref, _xref_target
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}


def _toc_anchors(app, docname="index"):
    toc = app.env.tocs[docname]
    return {ref["anchorname"] for ref in toc.findall(nodes.reference)}


def _toc_titles(app, docname="index"):
    return [ref.astext() for ref in app.env.tocs[docname].findall(nodes.reference)]


# -- P5-TEST-5: objects appear in the TOC ------------------------------------


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_objects_appear_in_the_toc(app):
    app.build()
    anchors = _toc_anchors(app)
    assert "#sv-sample_pkg-sample_base" in anchors
    assert "#sv-sample_pkg-sample_txn" in anchors
    # A method, not just the class.
    assert "#sv-sample_pkg-sample_txn-parity" in anchors


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_toc_anchor_matches_the_object_anchor(app):
    """A TOC entry that does not match its target is a broken sidebar link."""
    app.build()
    domain = app.env.get_domain("sv")
    anchors = _toc_anchors(app)
    for _docname, anchor, _kind in domain.objects.values():
        assert "#" + anchor in anchors


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_subroutine_toc_entries_carry_parentheses(app):
    app.build()
    titles = _toc_titles(app)
    assert "sample_txn::parity()" in titles
    assert "sample_txn::drive()" in titles
    # A class is not a subroutine.
    assert "sample_base" in titles


# -- P5-TEST-6: toc_object_entries_show_parents modes -------------------------


@pytest.mark.sphinx(
    "html", testroot="basic",
    confoverrides={**CONF, "toc_object_entries_show_parents": "hide"},
)
def test_toc_show_parents_hide(app):
    app.build()
    titles = _toc_titles(app)
    assert "parity()" in titles
    assert "sample_base" in titles


@pytest.mark.sphinx(
    "html", testroot="basic",
    confoverrides={**CONF, "toc_object_entries_show_parents": "all"},
)
def test_toc_show_parents_all(app):
    app.build()
    titles = _toc_titles(app)
    assert "sample_pkg::sample_txn::parity()" in titles
    assert "sample_pkg::sample_base" in titles


@pytest.mark.sphinx(
    "html", testroot="basic",
    confoverrides={**CONF, "add_function_parentheses": False},
)
def test_toc_respects_add_function_parentheses(app):
    app.build()
    titles = _toc_titles(app)
    assert "sample_txn::parity" in titles
    assert "sample_txn::parity()" not in titles


# -- P5-TEST-9 / C4: extends links --------------------------------------------


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_extends_links_to_the_base_class(app):
    app.build()
    doctree = app.env.get_doctree("index")
    sigs = [
        sig for sig in doctree.findall(addnodes.desc_signature)
        if "sample_txn" in sig.astext() and "extends" in sig.astext()
    ]
    assert sigs, "sample_txn signature not found"
    xrefs = list(sigs[0].findall(addnodes.pending_xref))
    assert [x["reftarget"] for x in xrefs] == ["sample_base"]
    # Inferred, not author-written: resolves silently when it cannot be found.
    assert xrefs[0]["reftype"] == "obj"

    html = (app.outdir / "index.html").read_text()
    assert 'href="#sv-sample_pkg-sample_base"' in html


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_unresolved_extends_is_silent(app, warning):
    """D5: an undocumented base degrades to text without a warning."""
    app.build()
    assert "cannot resolve" not in warning.getvalue()


# -- C1/C2/C5 helper ----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("sample_base", "sample_base"),
        ("sample_pkg::sample_base", "sample_pkg::sample_base"),
        # Packed dimensions are stripped before the lookup (C5)...
        ("logic[7:0]", ""),          # ...and the base is then a builtin (C2)
        ("my_vec[7:0]", "my_vec"),
        # Parameterization is not part of the name.
        ("uvm_object_registry#(T)", "uvm_object_registry"),
        # Builtins never link.
        ("int", ""),
        ("void", ""),
        ("string", ""),
        # Not an identifier at all.
        ("", ""),
        ("bit [7:0] extra", ""),
        ("'{1, 2}", ""),
    ],
)
def test_xref_target(text, expected):
    assert _xref_target(text) == expected


@pytest.mark.unit
def test_type_xref_returns_plain_text_for_builtins():
    class _Env:
        docname = "index"

    assert isinstance(_type_xref("int", _Env()), nodes.Text)
    node = _type_xref("sample_base", _Env())
    assert isinstance(node, addnodes.pending_xref)
    assert node.astext() == "sample_base"
