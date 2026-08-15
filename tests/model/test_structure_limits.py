"""M1-TEST-8/9: budgets, scoping, and the cost of *not* asking.

``tests/fixtures/deep`` elaborates 4680 instances from 29 lines of source --- a
small illustration of why the walk has to be optional.  Indexing it takes
milliseconds; walking it takes most of a second.
"""

from __future__ import annotations

import time

import pytest

from sphinx_systemverilog.model.index import build_index
from sphinx_systemverilog.model.structure import MAX_DEPTH
from tests.conftest import DEEP, DESIGN

pytestmark = pytest.mark.unit


def test_budget_truncates_rather_than_hanging():
    index = build_index(
        source_dirs=[str(DEEP)], structure_max_instances=100, use_cache=False
    )
    structure = index.structure

    assert structure.truncated is True
    assert structure.instance_count == 100
    # Truncated is not empty: what was walked is still reported.
    assert structure.edges


def test_full_walk_is_not_marked_truncated():
    structure = build_index(source_dirs=[str(DEEP)], use_cache=False).structure

    assert structure.truncated is False
    assert structure.instance_count == 4680


def test_depth_cap_is_generous_enough_for_real_designs():
    """The design fixture is 4 levels deep; the cap exists for pathology only."""
    assert MAX_DEPTH > 8
    structure = build_index(source_dirs=[str(DESIGN)], use_cache=False).structure
    assert structure.truncated is False


def test_structure_tops_narrows_the_walk():
    """``sv_structure_tops`` is the escape hatch for an oversized design."""
    everything = build_index(source_dirs=[str(DEEP)], use_cache=False).structure
    scoped = build_index(
        source_dirs=[str(DEEP)], structure_tops=["nonexistent"], use_cache=False
    ).structure

    assert everything.tops == ["deep_top"]
    assert scoped.tops == []
    assert scoped.instance_count == 0


def test_indexing_costs_a_fraction_of_walking():
    """M1-TEST-9: the eager walk must not creep back into ``build_index``.

    Deliberately a ratio with a wide margin rather than an absolute ceiling, so
    it catches a reintroduced eager walk (which would make the two costs equal)
    without failing on a slow CI machine.
    """
    start = time.perf_counter()
    index = build_index(source_dirs=[str(DEEP)], use_cache=False)
    index_time = time.perf_counter() - start

    assert index.structure_provider.computed is False

    start = time.perf_counter()
    index.structure
    walk_time = time.perf_counter() - start

    assert index_time * 5 < walk_time, (
        f"indexing took {index_time:.3f}s and walking {walk_time:.3f}s; "
        "indexing appears to be elaborating the hierarchy"
    )
