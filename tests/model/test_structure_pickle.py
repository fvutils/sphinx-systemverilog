"""M1-TEST-5, as D2-IMPL-4 changed it: the index Sphinx pickles renders
structure after unpickling.

Sphinx pickles whatever is stored on ``env``.  Before the database, the index
there held a live pyslang ``Compilation``, which cannot be pickled, so it was
dropped and a re-read page lost its structural directives.  The index is now a
:class:`~sphinx_systemverilog.model.db.DbIndex`: it pickles to paths and
options, and the design structure comes back from the snapshot stored beside
the database --- without parsing.
"""

from __future__ import annotations

import pickle

import pytest

from sphinx_systemverilog.frontend import build
from sphinx_systemverilog.frontend.build import Options, open_index
from sphinx_systemverilog.model.index import build_index, clear_index_cache
from tests.conftest import DESIGN

pytestmark = pytest.mark.unit


@pytest.fixture
def no_parse(monkeypatch):
    """Call to make any later parse fail: the stand-in for "another process"."""

    def arm():
        clear_index_cache()

        def parse(options):
            raise AssertionError("parsed")

        monkeypatch.setattr(build, "parse", parse)

    return arm


def _index(tmp_path):
    return open_index(Options.make(source_dirs=[str(DESIGN)]), cache_dir=str(tmp_path))


def test_index_pickles_small(tmp_path):
    index = _index(tmp_path)
    data = pickle.dumps(index)

    assert b"Compilation" not in data
    assert len(data) < 4096, "paths and options, not objects"


def test_unpickled_index_renders_structure_without_parsing(tmp_path, no_parse):
    index = _index(tmp_path)
    before = index.structure
    no_parse()

    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure.tops == before.tops
    assert restored.structure.children_of("lane") == before.children_of("lane")
    assert restored.instance_edges == index.instance_edges
    assert len(restored) == len(index)
    assert restored.get("lane").kind == "module"


def test_in_memory_index_parses_again_when_unpickled(tmp_path):
    index = open_index(Options.make(source_dirs=[str(DESIGN)]), cache_dir=None)
    tops = index.structure.tops
    clear_index_cache()

    restored = pickle.loads(pickle.dumps(index))

    assert restored.structure.tops == tops
    assert restored.get("lane") is not None


def test_design_structure_is_picklable_on_its_own():
    """The data the walk produces holds no pyslang references (the snapshot
    depends on it)."""
    structure = build_index(
        source_dirs=[str(DESIGN)], use_cache=False
    ).structure

    restored = pickle.loads(pickle.dumps(structure))

    assert restored.tops == structure.tops
    assert restored.children_of("lane") == structure.children_of("lane")
