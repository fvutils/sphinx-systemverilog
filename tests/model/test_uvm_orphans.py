"""U2-TEST-3: orphan detection --- the finding, and the false positives.

A `config_db` field name is a string. A typo in one compiles, elaborates and
simulates without a murmur; the component keeps its default and the testbench
quietly does the wrong thing. Nothing at run time reports it. That is the bug
this view exists to catch, and it is worth catching.

It is also a bug worth being careful about, because the failure mode of a
detector like this is that it cries wolf. UVM lets both the scope and the field
name be globs, so a report that treated `set("n_*")` as unread because no
literal `"n_*"` is read would flag working code --- and a reader who is shown
one false orphan stops believing the true ones.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import field_matches
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def config():
    return uvm_stub_index("config_tb.sv").uvm_provider.config()


def test_the_typo_is_flagged(config):
    """`n_itmes` is a typo for `n_items`, and nothing reads it."""
    assert [a.field for a in config.orphan_sets] == ["n_itmes"]


def test_the_glob_field_set_is_not_flagged(config):
    """`set("n_*")` could reach `get("n_items")`, so it is not an orphan."""
    orphans = {a.field for a in config.orphan_sets}

    assert "n_*" not in orphans


def test_the_wildcard_scope_set_is_not_flagged(config):
    """A glob *scope* must not disturb the field match either."""
    assert "mode" not in {a.field for a in config.orphan_sets}


def test_a_get_nothing_sets_is_flagged(config):
    """The other direction: a component reading a knob no one provides."""
    assert [a.field for a in config.orphan_gets] == ["unset_depth"]


def test_a_matched_set_lists_its_consumers(config):
    row = next(r for r in config.rows() if r.access.field == "n_items"
               and r.access.owner == "cfg_agent")

    assert row.orphan is False
    assert row.consumers == ("cfg_driver.build_phase",)


def test_the_glob_set_lists_the_literal_get_it_could_match(config):
    row = next(r for r in config.rows() if r.access.field == "n_*")

    assert row.consumers == ("cfg_driver.build_phase",)


def test_a_computed_field_is_never_an_orphan(config):
    """It cannot be paired, so calling it unread would be an invention."""
    row = next(r for r in config.rows() if r.access.field is None)

    assert row.orphan is False
    assert row.consumers == ()


def test_computed_accesses_are_counted_so_the_gap_is_visible(config):
    """The honest half of excluding them: say how many were excluded.

    Pairing *against* a computed field would be the maximally conservative
    choice and is the wrong one --- a single computed name could in principle
    read anything, so it would clear every orphan in the project and the view
    would never report a thing. Excluding them and reporting the count keeps
    the finding useful while making its limit visible.
    """
    assert len(config.dynamic) == 1


def test_every_row_is_a_set(config):
    """The table is set-centric: a get with no set is reported separately."""
    assert len(config.rows()) == len(config.sets)


@pytest.mark.parametrize(
    "left, right, expected",
    [
        ("n_items", "n_items", True),
        ("n_items", "n_itmes", False),
        ("n_*", "n_items", True),       # glob on the set side
        ("n_items", "n_*", True),       # glob on the get side
        ("*", "anything", True),
        ("n_items", None, False),       # computed: excluded, not matched
        (None, "n_items", False),
        (None, None, False),
    ],
)
def test_field_matching_is_glob_aware_in_both_directions(left, right, expected):
    assert field_matches(left, right) is expected
