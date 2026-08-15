"""Struct-valued parameters: readable display without merging distinct configs.

Found by running the extension over CVA6, which passes its entire configuration
as a single ``config_pkg::cva6_cfg_t`` parameter. That struct elaborates to one
**17268-bit integer**, so every line of the instance tree read like::

    i_frontend : frontend  #(CVA6Cfg=17268'd22865738816596544988970659865...e5153)

This is not an exotic style --- it is how modern parameterized RTL is written,
so the tree has to cope with it. The fix has two halves, and both matter:

* the *display* falls back to the type name, so the tree stays readable;
* the *identity* stays the full value, so two different configurations are still
  two different elaborations. Collapsing them would claim a design uses one
  configuration where it uses two.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.index import build_index
from sphinx_systemverilog.model.structure import MAX_PARAM_VALUE_TEXT, SvParam
from tests.conftest import CONFIG, DESIGN

pytestmark = pytest.mark.unit


@pytest.fixture
def structure():
    return build_index(source_dirs=[str(CONFIG)], use_cache=False).structure


def test_struct_value_is_genuinely_unreadable(structure):
    """Guards the premise: without the fix there is a wall of digits to show."""
    cfg = structure.children_of("cfg_top")[0].params[0]

    assert cfg.name == "Cfg"
    assert len(cfg.value) > MAX_PARAM_VALUE_TEXT
    assert cfg.value[0].isdigit()


def test_long_values_display_as_their_type(structure):
    small, big = structure.children_of("cfg_top")

    assert small.param_text == "#(Cfg=core_cfg_t, TAG=1)"
    assert big.param_text == "#(Cfg=core_cfg_t, TAG=2)"


def test_short_values_are_untouched(structure):
    tag = structure.children_of("cfg_top")[0].params[1]

    assert tag.value == "1"
    assert tag.display == "1"


def test_distinct_configs_remain_distinct_elaborations(structure):
    """The half that is easy to get wrong: display must not become identity."""
    small, big = structure.children_of("cfg_top")

    assert small.params[0].display == big.params[0].display == "core_cfg_t"
    assert small.params[0].value != big.params[0].value
    assert len(structure.elaborations_of("cfg_leaf")) == 2


def test_matrix_numbers_configs_that_would_otherwise_collide(structure):
    usage = structure.param_usage("cfg_leaf")

    assert set(usage["Cfg"]) == {"core_cfg_t #1", "core_cfg_t #2"}
    assert usage["Cfg"]["core_cfg_t #1"] == ["cfg_top.u_small.u_leaf"]
    assert usage["Cfg"]["core_cfg_t #2"] == ["cfg_top.u_big.u_leaf"]


def test_ordinary_parameters_are_not_numbered():
    """Numbering appears only where labels would otherwise collide."""
    structure = build_index(source_dirs=[str(DESIGN)], use_cache=False).structure

    assert set(structure.param_usage("leaf")["W"]) == {"8", "32"}


@pytest.mark.parametrize(
    "value,type_name,expected",
    [
        ("8", "int", "8"),
        ("1'b0", "bit", "1'b0"),
        # Long value, named type -> the bare type name.
        ("9" * 80, "pkg::cfg_t", "cfg_t"),
        ("9" * 80, "cfg_t", "cfg_t"),
        # Module-local typedefs are scope-qualified with '.', not '::'.
        ("9" * 80, "instr_tracer.interrupts_t", "interrupts_t"),
        # Long value, no usable type name -> truncate rather than mislead.
        ("9" * 80, "", "9" * 31 + "…"),
        # For an array type the head of the value shows the elements, which is
        # more informative than the type name.
        ("9" * 80, "copro_issue_resp_t$[0:9]", "9" * 31 + "…"),
        ("9" * 80, "logic[63:0]$[0:9]", "9" * 31 + "…"),
        ("9" * 80, "logic[63:0][5:0]", "9" * 31 + "…"),
        ("9" * 80, "struct packed{...}", "9" * 31 + "…"),
    ],
)
def test_display_rules(value, type_name, expected):
    assert SvParam("P", value, type_name).display == expected
