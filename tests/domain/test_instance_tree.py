"""M2-TEST-1/2: ``sv:instance-tree``.

The tree is the primary structural view, and it is text rather than Graphviz on
purpose: it stays readable at depth, needs no ``dot``, is searchable, and every
type name can be a cross-reference.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from sphinx import addnodes

from tests.conftest import COLLAPSE, DESIGN

pytestmark = pytest.mark.sphinx

CONF = {"sv_source_dirs": [str(DESIGN)]}
COLLAPSE_CONF = {"sv_source_dirs": [str(COLLAPSE)]}


def _trees(app, docname="index"):
    doctree = app.env.get_doctree(docname)
    return [
        n for n in doctree.findall(nodes.literal_block)
        if "sv-instance-tree" in n.get("classes", [])
    ]


def _notes(app, docname="index"):
    doctree = app.env.get_doctree(docname)
    return [
        n.astext() for n in doctree.findall(nodes.paragraph)
        if "sv-structure-note" in n.get("classes", [])
    ]


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_tree_shows_the_whole_hierarchy(app):
    app.build()
    text = _trees(app)[0].astext()

    assert text.splitlines()[0] == "soc"
    assert "u_narrow : cluster #(W=8, WIDE=1'b0)" in text
    # Reachable only through a generate block and an instance array.
    assert "g_lp[*].u_g" in text
    assert "u_l[3:0]" in text
    assert "└──" in text and "├──" in text


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_tree_respects_each_elaboration(app):
    """``cluster`` has two elaborations with genuinely different bodies.

    Showing the union under both would describe a design that does not exist.
    """
    app.build()
    lines = _trees(app)[0].astext().splitlines()

    # Names are padded for column alignment, so match on the name alone.
    narrow = next(i for i, ln in enumerate(lines) if "u_narrow" in ln)
    wide = next(i for i, ln in enumerate(lines) if "u_wide" in ln)

    # Only the taken branch appears beneath each.
    assert "g_narrow.u_leaf" in lines[narrow + 1]
    assert "g_wide.u_lane" in lines[wide + 1]
    assert not any("g_wide" in ln for ln in lines[narrow + 1:wide])


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_array_and_generate_multiplicity_is_shown(app):
    app.build()
    text = _trees(app)[0].astext()

    assert "(×4)" in text


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_type_names_are_cross_references(app):
    app.build()
    refs = list(_trees(app)[0].findall(addnodes.pending_xref))

    targets = {r["reftarget"] for r in refs}
    assert {"soc", "cluster", "lane", "leaf"} <= targets
    # ``obj`` degrades to text when unresolved: a tree routinely names types
    # that no page documents, and that is not an authoring error.
    assert all(r["reftype"] == "obj" for r in refs)
    assert all(r["refwarn"] is False for r in refs)


@pytest.mark.sphinx("html", testroot="tree-links", confoverrides=CONF)
def test_cross_references_survive_into_the_html(app):
    """⭐ The doctree having xrefs is not enough --- they must reach the page.

    Sphinx's ``apply_source_workaround`` fills an empty ``rawsource`` with
    ``astext()``, after which the HTML writer treats the block as a code block,
    syntax-highlights it and **throws the child nodes away**.  Every link in the
    tree disappeared while the doctree-level test above still passed, so this
    asserts on the rendered output instead.
    """
    app.build()
    html = (app.outdir / "index.html").read_text()

    start = html.index("sv-instance-tree")
    tree_html = html[start:html.index("</pre>", start)]

    assert "<a" in tree_html, "the instance tree rendered with no links at all"
    for module in ("soc", "cluster", "lane", "leaf"):
        assert f'title="{module}"' in tree_html, f"{module} is not linked"
    # The tell-tale of the broken path: Pygments markup instead of children.
    assert "highlight-default" not in tree_html


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_depth_limit_elides_explicitly(app):
    """A truncated tree must say so, with a count. Silence reads as completeness."""
    app.build()
    shallow = _trees(app)[1].astext()

    assert "u_narrow" in shallow
    assert "g_narrow.u_leaf" not in shallow

    elision = [n for n in _notes(app) if "not shown" in n]
    assert elision
    assert "2 deeper level(s)" in elision[0]
    assert "10 instance(s)" in elision[0]
    assert ":depth:" in elision[0]


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_module_with_no_children_says_so(app):
    app.build()

    assert "Instantiates nothing within the documented sources." in _notes(app)


@pytest.mark.sphinx("html", testroot="collapse", confoverrides=COLLAPSE_CONF)
def test_collapse_folds_identical_siblings(app):
    app.build()
    full, collapsed = _trees(app)[0].astext(), _trees(app)[1].astext()

    # Uncollapsed: every sibling on its own line, both subtrees expanded.
    assert full.count("u_a") == 2
    assert "u_m2" in full

    # Collapsed: folded siblings are named, not merely counted.
    assert "u_m1, u_m2 : cl_mid" in collapsed
    assert "u_a, u_b, u_c : cl_leaf" in collapsed
    assert "(×2)" in collapsed and "(×3)" in collapsed
    # A sibling that differs by parameter is not folded in with the rest.
    assert "u_wide" in collapsed
    assert "#(W=64)" in collapsed


@pytest.mark.sphinx("html", testroot="collapse", confoverrides=COLLAPSE_CONF)
def test_sibling_columns_are_aligned(app):
    app.build()
    lines = _trees(app)[0].astext().splitlines()

    siblings = [ln for ln in lines if "cl_leaf" in ln]
    columns = {ln.index(" : ") for ln in siblings}
    assert len(columns) == 1, "sibling type columns should line up"
