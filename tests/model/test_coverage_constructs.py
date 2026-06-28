"""Tests for covergroup and constraint extraction (P4-TEST-1)."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder
from tests.conftest import read_fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def item():
    roots = ModelBuilder().build_from_text(read_fixture("cov_pkg.sv"), "cov_pkg.sv")
    return next(o for o in roots[0].walk() if o.name == "cov_item")


def _child(obj, name):
    return next((c for c in obj.children if c.name == name), None)


def test_covergroup_documented(item):
    cg = _child(item, "mode_cg")
    assert cg is not None
    assert cg.kind == "covergroup"
    assert cg.raw_doc == "Coverage of the mode field."


def test_coverpoint_child(item):
    cg = _child(item, "mode_cg")
    cp = _child(cg, "cp_mode")
    assert cp is not None
    assert cp.kind == "coverpoint"


def test_constraint_documented(item):
    con = _child(item, "c_value")
    assert con is not None
    assert con.kind == "constraint"
    assert con.signature == "constraint c_value"
    assert con.raw_doc == "value must be non-negative"


def test_covergroup_not_a_plain_property(item):
    # The covergroup must not also appear as a duplicate ClassProperty.
    cgs = [c for c in item.children if c.name == "mode_cg"]
    assert len(cgs) == 1
    assert cgs[0].kind == "covergroup"
