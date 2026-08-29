"""U2-TEST-4: ``sv:uvm-config`` renders the table and states its own limits.

The model tests cover the pairing. These cover what a reader sees, which is
where the value of an orphan report is actually won or lost: a finding that is
not visible, or that is presented without its caveats, is not a finding.
"""

from __future__ import annotations

import pytest

from tests.conftest import UVM_STUB, UVM_TB

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "config_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

pytestmark = pytest.mark.sphinx

sphinx_config = pytest.mark.sphinx(
    "html", testroot="uvm-config", srcdir="uvm-config", confoverrides=CONF
)


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


@sphinx_config
def test_the_table_renders(page):
    assert "sv-uvm-config" in page
    for header in ("Setter", "Scope", "Field", "Type", "Value", "Consumers"):
        assert header in page


@sphinx_config
def test_settings_and_their_consumers_are_shown(page):
    assert "cfg_agent.build_phase" in page
    assert "cfg_driver.build_phase" in page
    assert "n_items" in page


@sphinx_config
def test_the_orphan_is_visible_in_the_table(page):
    assert "n_itmes" in page
    assert "unread" in page


@sphinx_config
def test_the_orphan_note_explains_why_it_matters(page):
    """A count on its own does not tell a reader what to do about it."""
    assert "read by nothing" in page
    assert "typo" in page


@sphinx_config
def test_the_unset_get_is_reported(page):
    assert "unset_depth" in page
    assert "read but never set" in page


@sphinx_config
def test_computed_field_names_are_counted_not_hidden(page):
    assert "build their field name at run time" in page


@sphinx_config
def test_the_scope_caveat_is_stated(page):
    """Scope is in the table but not in the match, and the page must say so."""
    assert "Pairing is on the field name only" in page


@sphinx_config
def test_the_scope_note_is_present(page):
    assert "not a simulation trace" in page


@sphinx_config
def test_type_names_are_cross_referenced(page):
    assert "sv-type" in page


@sphinx_config
def test_a_top_module_setting_appears(page):
    """The virtual-interface binding is set outside any component."""
    assert "cfg_tb_top" in page
    assert "uvm_test_top" in page


@sphinx_config
def test_conditional_settings_are_marked(page):
    assert "[conditional]" in page


@sphinx_config
def test_orphans_option_shows_only_orphans(page):
    """The filtered view is for a page that wants the finding, not the table.

    The test root renders the full table *and* an ``:orphans:`` one, so the
    orphaned field appears twice while a matched field appears only in the
    full table.
    """
    assert page.count("n_itmes") >= 2
    assert page.count("n_itmes") < page.count("cfg_agent.build_phase")


@sphinx_config
def test_a_component_filter_narrows_the_table(page):
    """`.. sv:uvm-config:: cfg_agent` renders, and does so without warning."""
    assert page.count("cfg_agent.build_phase") >= 2
