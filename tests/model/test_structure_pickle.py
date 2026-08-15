"""M1-TEST-5: the retained ``Compilation`` must never reach Sphinx's pickle.

Sphinx pickles whatever is stored on ``env``, and this extension stores the
index there.  A pyslang ``Compilation`` raises ``TypeError: cannot pickle`` on
``pickle.dumps``, so a provider surviving into ``__getstate__`` would break
*every* build --- not just pages using a structural directive.  This guards the
highest-probability failure mode of the lazy-structure design.
"""

from __future__ import annotations

import pickle

import pytest

from sphinx_systemverilog.model.index import build_index
from tests.conftest import DESIGN

pytestmark = pytest.mark.unit


def test_index_with_live_provider_pickles():
    index = build_index(source_dirs=[str(DESIGN)], use_cache=False)
    assert index.structure_provider is not None

    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure_provider is None
    assert len(restored) == len(index)


def test_index_pickles_after_the_walk():
    """A memoized DesignStructure must not keep the compilation alive either."""
    index = build_index(source_dirs=[str(DESIGN)], use_cache=False)
    assert index.structure is not None

    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure_provider is None


def test_unpickled_index_degrades_instead_of_crashing():
    """M1-IMPL-10: no provider means no structure, not an exception."""
    index = build_index(source_dirs=[str(DESIGN)], use_cache=False)
    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure is None
    assert restored.instance_edges == {}


def test_design_structure_is_picklable_on_its_own():
    """The data the walk produces holds no pyslang references."""
    structure = build_index(
        source_dirs=[str(DESIGN)], use_cache=False
    ).structure

    restored = pickle.loads(pickle.dumps(structure))

    assert restored.tops == structure.tops
    assert restored.children_of("lane") == structure.children_of("lane")
