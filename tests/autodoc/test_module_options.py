"""M2-TEST-5: the ``autosvmodule`` structural options.

The second half of this file re-proves the M1 contract one layer up. Each
``:show-*:`` option triggers the instance-hierarchy walk, so the important
assertion is the negative one: with the options absent, documenting a module
must still cost nothing structural. Defaulting any of these to on would quietly
put every user of ``autosvmodule`` back on the eager path M1 removed.
"""

from __future__ import annotations

import pytest
from docutils import nodes

from tests.conftest import DESIGN

pytestmark = pytest.mark.sphinx

CONF = {"sv_source_dirs": [str(DESIGN)]}


def _text(app, docname="index"):
    return app.env.get_doctree(docname).astext()


def _rubrics(app, docname="index"):
    return [
        n.astext() for n in app.env.get_doctree(docname).findall(nodes.rubric)
    ]


@pytest.mark.sphinx("html", testroot="module-options", confoverrides=CONF)
def test_each_option_renders_its_section(app):
    app.build()

    assert _rubrics(app) == [
        "Instance tree", "Instantiated by", "Parameter values used",
    ]


@pytest.mark.sphinx("html", testroot="module-options", confoverrides=CONF)
def test_sections_contain_real_structural_content(app):
    app.build()
    text = _text(app)

    assert "g_lp[*].u_g" in text                      # instance tree
    assert "soc.u_wide.g_wide.u_lane" in text         # instantiated by
    assert "Values observed within the documented sources." in text


@pytest.mark.sphinx(
    "html", testroot="module-options", srcdir="module-options-walk",
    confoverrides=CONF,
)
def test_options_share_a_single_walk(app):
    app.build()

    assert app.env.sv_index.structure_provider.walk_count == 1


@pytest.mark.sphinx("html", testroot="module-plain", confoverrides=CONF)
def test_without_the_options_nothing_is_elaborated(app):
    """⭐ The M1 contract, restated at the directive layer."""
    app.build()

    provider = app.env.sv_index.structure_provider
    assert provider is not None
    assert provider.computed is False, (
        "autosvmodule must not walk the hierarchy unless asked"
    )


@pytest.mark.sphinx("html", testroot="module-plain", confoverrides=CONF)
def test_without_the_options_no_structural_output(app):
    app.build()

    assert _rubrics(app) == []
    assert "Instantiated by" not in _text(app)
