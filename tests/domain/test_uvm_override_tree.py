"""U6-TEST-1 (`U6-IMPL-1`, rendering): the tree says when it is being lied to.

The model finding is worthless unless it reaches the page the reader is on.
A component whose type is overridden looks completely ordinary in a tree, and
that is precisely the problem the annotation exists to solve.

The assertion that matters most here is the *negative* one: the tree must go on
naming the type its ``create`` call names. Substituting the override's type
would trade one confident wrong answer for another.
"""

from __future__ import annotations

import pytest
from docutils import nodes

from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "override_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-override", srcdir="uvm-override", confoverrides=CONF
)


@pytest.fixture
def tree(app):
    app.build()
    doctree = app.env.get_doctree("index")
    return next(iter(doctree.findall(nodes.literal_block))).astext()


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


@pytest.mark.sphinx
@sphinx_config
def test_an_overridden_component_is_annotated(tree):
    assert "drv : ovr_driver" in tree
    assert "[overridden → fast_driver]" in tree


@pytest.mark.sphinx
@sphinx_config
def test_the_tree_still_names_the_type_the_source_names(tree):
    """The negative assertion, and the important one. Whether an override
    applies is decided at run time; printing ``fast_driver`` here would be a
    claim about a simulation."""
    assert "drv : fast_driver" not in tree


@pytest.mark.sphinx
@sphinx_config
def test_an_inst_override_shows_the_path_it_is_keyed_on(tree):
    """A type override and an inst override are not the same claim, and the
    path is the difference."""
    assert "under env.agt.drv" in tree


@pytest.mark.sphinx
@sphinx_config
def test_a_conditional_override_says_so(tree):
    """``if (want_noise)`` — it may not run at all."""
    assert "conditionally]" in tree


@pytest.mark.sphinx
@sphinx_config
def test_a_broken_override_is_marked_on_the_node_too(tree):
    """Counted under the tree *and* marked inline. A reader scanning for what
    affects this component should not have to cross-check a note to learn that
    one of the two overrides listed here never fires."""
    assert "[overridden → noisy_moniter — no such type" in tree


@pytest.mark.sphinx
@sphinx_config
def test_every_override_of_a_type_is_shown(tree):
    """``ovr_monitor`` is overridden three times: by name (with a typo),
    through the registry, and never mind which wins — that is a run-time
    question and all three are in the source."""
    line = next(l for l in tree.splitlines() if "mon : ovr_monitor" in l)
    assert line.count("[overridden") == 2, line


@pytest.mark.sphinx
@sphinx_config
def test_the_override_type_is_a_cross_reference(app):
    from sphinx import addnodes

    app.build()
    doctree = app.env.get_doctree("index")
    targets = {n["reftarget"] for n in doctree.findall(addnodes.pending_xref)}

    assert {"ovr_driver", "fast_driver"} <= targets


@pytest.mark.sphinx
@sphinx_config
def test_the_page_explains_why_nothing_was_resolved(page):
    assert "affected by a factory override" in page
    assert "decided at run time" in page


@pytest.mark.sphinx
@sphinx_config
def test_the_broken_override_is_reported_under_the_tree(page):
    assert "name a type that is not in the parsed sources" in page
    assert "noisy_moniter" in page
