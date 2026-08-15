"""M1-TEST-4: elaboration is paid for only when something asks for it.

This is the contract test for the whole structure feature, not a nicety.
Walking the instance hierarchy is the single most expensive thing this extension
can do (~0.7s per 5000 instances, against ~0ms for parse and ``getRoot()``), and
before this milestone it happened on *every* build whether or not any page
rendered a structural directive.

Two properties are asserted, and both matter:

* a project with no structural directive never walks the hierarchy at all;
* a project with one --- or ten, across several pages --- walks it exactly once.

Anything that reintroduces an eager walk breaks this test rather than quietly
costing every user a few seconds per build.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.index import build_index
from tests.conftest import DESIGN

CONF = {"sv_source_dirs": [str(DESIGN)]}


@pytest.mark.unit
def test_build_index_does_not_elaborate():
    """Building the index attaches a provider but never calls it."""
    index = build_index(source_dirs=[str(DESIGN)], use_cache=False)

    provider = index.structure_provider
    assert provider is not None, "the provider must be attached during build"
    assert provider.computed is False
    assert provider.walk_count == 0


@pytest.mark.unit
def test_walk_happens_once_and_is_memoized():
    index = build_index(source_dirs=[str(DESIGN)], use_cache=False)
    provider = index.structure_provider

    first = index.structure
    assert provider.computed is True
    assert provider.walk_count == 1

    second = index.structure
    assert second is first, "the second call must reuse the memoized result"
    assert provider.walk_count == 1

    # The deprecated accessor routes through the same memoized walk.
    index.instance_edges
    assert provider.walk_count == 1


@pytest.mark.sphinx(
    "html", testroot="nostructure", srcdir="lazy-none", confoverrides=CONF
)
def test_no_structural_directive_no_walk(app):
    """A full build of module docs with no structural directive walks nothing."""
    app.build()

    provider = app.env.sv_index.structure_provider
    assert provider is not None
    assert provider.computed is False, (
        "documenting modules must not trigger a hierarchy walk"
    )


@pytest.mark.sphinx("html", testroot="design", srcdir="lazy-one", confoverrides=CONF)
def test_one_structural_directive_walks_once(app):
    app.build()

    provider = app.env.sv_index.structure_provider
    assert provider.computed is True
    assert provider.walk_count == 1


@pytest.mark.sphinx(
    "html", testroot="design-many", srcdir="lazy-many", confoverrides=CONF
)
def test_many_structural_directives_still_walk_once(app):
    """Three diagrams across two pages share a single walk."""
    app.build()

    provider = app.env.sv_index.structure_provider
    assert provider.computed is True
    assert provider.walk_count == 1


@pytest.mark.sphinx(
    "html", testroot="design", srcdir="lazy-incremental", confoverrides=CONF
)
def test_unchanged_rebuild_does_not_re_elaborate(app):
    """An incremental rebuild of unchanged pages costs nothing structural.

    Sphinx reuses the cached doctree, so the directive never re-runs --- which
    is exactly what should happen, and is also why the index dropping its
    provider on pickle is harmless in the common case.
    """
    app.build()
    assert app.env.sv_index.structure_provider.walk_count == 1

    app.build()

    assert app.env.sv_index.structure_provider.walk_count == 1
