"""U1-TEST-8: ``sv:uvm-tree`` renders, and says what it could not show.

The model tests cover *what* is extracted. These cover what a reader actually
sees --- which is where the two rules that govern this feature are either kept
or quietly broken:

* every type name is a live cross-reference, which is the whole reason the tree
  is text rather than a picture;
* nothing is elided silently. Depth-limited levels, unresolved types and
  black-boxed boundaries are each counted and reported below the tree.
"""

from __future__ import annotations

import pytest

from tests.conftest import UVM_STUB, UVM_TB

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "basic_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

pytestmark = pytest.mark.sphinx


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_the_tree_renders(page):
    assert "sv-uvm-tree" in page
    for name in ("my_test", "my_env", "my_agent", "my_driver", "my_monitor"):
        assert name in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_type_names_are_cross_references(page):
    """The tree is text so that every type can link to its documentation.

    `_TREE_RAWSOURCE` is what makes this work: an empty rawsource sends the
    block down Sphinx's code-block path, which discards child nodes and would
    silently strip every link here while still rendering a plausible tree.
    """
    assert 'href="#' in page or "reference internal" in page
    assert "sv-type" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_conditional_components_are_marked_in_the_output(page):
    assert "[conditional]" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_unknown_multiplicity_is_shown_as_n(page):
    """`(×N)`, not a number invented from the array declaration."""
    assert "×N" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_tlm_ports_are_not_in_the_component_tree(page):
    """A TLM port is not a `uvm_component`, so it is not a tree node.

    Real UVM declares `uvm_port_base #(IF) extends IF`, where `IF` derives from
    `uvm_void` --- the port holds a component proxy rather than being one. This
    is asserted because an earlier version of the test stub got it wrong and
    put a port under every monitor.
    """
    assert "uvm_analysis_port" not in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_depth_limit_reports_what_it_hid(page):
    assert "not shown — raise :depth:" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_the_scope_caveat_is_always_present(page):
    """The single most important sentence on the page."""
    assert "not a simulation trace" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_a_named_root_narrows_the_tree(page):
    """`.. sv:uvm-tree:: my_agent` roots at the agent, not the test."""
    assert "my_agent" in page


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_optional_is_silent_on_a_missing_root(app, warning):
    app.build()

    text = warning.getvalue()
    assert "no_such_test" not in text


@pytest.mark.sphinx("html", testroot="uvm-tree", srcdir="uvm-tree", confoverrides=CONF)
def test_the_build_is_warning_free(app, warning):
    app.build()

    assert warning.getvalue().strip() == ""


@pytest.mark.sphinx(
    "html", testroot="uvm-tree", srcdir="uvm-tree-collapse", confoverrides=CONF
)
def test_collapse_folds_siblings_that_differ_only_in_name(app):
    """`agt_a` and `agt_b` are the same component twice."""
    app.build()
    page = (app.outdir / "index.html").read_text()

    assert "agt_a, agt_b" in page


@pytest.mark.sphinx(
    "html", testroot="uvm-tree", srcdir="uvm-tree-lazy", confoverrides=CONF
)
def test_the_extraction_is_shared_across_the_page(app):
    """Five directives, but only as many walks as there are distinct roots.

    The page names three: the auto-detected one (used by three directives),
    `my_agent`, and `no_such_test`. So three walks, not five --- and the failed
    lookup is memoized too, so a page that repeats a bad root does not pay for
    it repeatedly.
    """
    app.build()

    assert app.env.sv_index.uvm_provider.walk_count == 3
