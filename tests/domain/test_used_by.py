"""M2-TEST-3/4: ``sv:used-by`` and ``sv:parameter-matrix``.

These are the two views a file-at-a-time tool cannot produce at all. Both make a
claim about scope --- "within the documented sources" --- and both must state it,
because "not instantiated" is otherwise easy to read as "unused", which for a
reusable IP block would be wrong.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from sphinx import addnodes

from tests.conftest import COLLAPSE, DESIGN

pytestmark = pytest.mark.sphinx

CONF = {"sv_source_dirs": [str(DESIGN)]}
COLLAPSE_CONF = {"sv_source_dirs": [str(COLLAPSE)]}


def _lists(app, docname="index"):
    doctree = app.env.get_doctree(docname)
    return [
        n for n in doctree.findall(nodes.bullet_list)
        if "sv-used-by" in n.get("classes", [])
    ]


def _notes(app, docname="index"):
    doctree = app.env.get_doctree(docname)
    return [
        n.astext() for n in doctree.findall(nodes.paragraph)
        if "sv-structure-note" in n.get("classes", [])
    ]


def _tables(app, docname="index"):
    doctree = app.env.get_doctree(docname)
    return [
        n for n in doctree.findall(nodes.table)
        if "sv-parameter-matrix" in n.get("classes", [])
    ]


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_every_instantiation_site_is_listed(app):
    app.build()
    text = _lists(app)[0].astext()

    # One from the if-generate branch, four generate iterations, one array.
    assert "soc.u_narrow.g_narrow.u_leaf" in text
    assert "soc.u_wide.g_wide.u_lane.g_lp[0].u_g" in text
    assert "soc.u_wide.g_wide.u_lane.g_lp[3].u_g" in text
    assert "soc.u_wide.g_wide.u_lane.u_l[3:0]" in text


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_sites_show_parameters_and_parent_links(app):
    app.build()
    used_by = _lists(app)[0]

    assert "#(W=8)" in used_by.astext()
    assert "#(W=32)" in used_by.astext()
    targets = {r["reftarget"] for r in used_by.findall(addnodes.pending_xref)}
    assert {"cluster", "lane"} <= targets


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_array_multiplicity_is_not_double_counted(app):
    """Generate iterations are listed individually, so only arrays carry a count."""
    app.build()
    lines = [ln for ln in _lists(app)[0].astext().splitlines() if ln.strip()]

    iterations = [ln for ln in lines if "g_lp[" in ln]
    arrays = [ln for ln in lines if "u_l[3:0]" in ln]

    assert len(iterations) == 4
    assert all("×" not in ln for ln in iterations)
    assert len(arrays) == 1
    assert "×4" in arrays[0]


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_site_count_and_scope_are_stated(app):
    app.build()

    assert "6 instantiation site(s) within the documented sources." in _notes(app)


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_uninstantiated_module_says_so_rather_than_nothing(app):
    app.build()

    assert "Not instantiated within the documented sources." in _notes(app)


@pytest.mark.sphinx("html", testroot="collapse", confoverrides=COLLAPSE_CONF)
def test_limit_reports_what_it_hid(app):
    app.build()

    listed = [ln for ln in _lists(app)[0].astext().splitlines() if ln.strip()]
    assert len(listed) == 3

    elision = [n for n in _notes(app) if "not shown" in n]
    assert elision
    assert "5 further instantiation site(s)" in elision[0]
    assert "of 8 total" in elision[0]


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_parameter_matrix_groups_values(app):
    app.build()
    table = _tables(app)[0]
    text = table.astext()

    assert "Parameter" in text and "Instances" in text
    # leaf is elaborated at two widths: five sites at 32, one at 8.
    assert "32" in text and "8" in text
    rows = list(table.findall(nodes.row))
    # header + one row per distinct value
    assert len(rows) == 3


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_parameter_matrix_states_its_scope(app):
    app.build()

    assert "Values observed within the documented sources." in _notes(app)
