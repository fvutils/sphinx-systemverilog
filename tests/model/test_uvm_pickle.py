"""U0-TEST-3, as D2-IMPL-4 changed it: the UVM views survive Sphinx's pickle.

The same contract as ``test_structure_pickle.py``, for the testbench: what
takes no argument (the default tree, config_db, overrides, bindings, the class
names) comes back from the snapshot without parsing; a tree under another root
is answered by parsing once in that process.
"""

from __future__ import annotations

import pickle

import pytest

from sphinx_systemverilog.frontend import build
from sphinx_systemverilog.frontend.build import Options, open_index
from sphinx_systemverilog.model.index import clear_index_cache
from tests.conftest import UVM_STUB, UVM_TB, uvm_stub_index

pytestmark = pytest.mark.unit


def _options(*tb_files):
    return Options.make(
        source_dirs=[str(UVM_STUB)],
        build_units=[str(UVM_STUB / "mini_uvm.sv"), *(str(UVM_TB / n) for n in tb_files)],
        include_dirs=[str(UVM_STUB)],
    )


def test_unpickled_index_answers_from_the_snapshot(tmp_path, monkeypatch):
    index = open_index(_options("basic_tb.sv"), cache_dir=str(tmp_path))
    provider = index.uvm_provider
    tree, config = provider.get(), provider.config()

    clear_index_cache()
    monkeypatch.setattr(build, "parse", lambda options: (_ for _ in ()).throw(AssertionError("parsed")))
    restored = pickle.loads(pickle.dumps(index))

    assert restored.uvm_structure.root == tree.root
    assert restored.uvm_structure.children == tree.children
    assert restored.uvm_provider.config().accesses == config.accesses
    assert restored.uvm_provider.overrides() == provider.overrides()
    assert restored.uvm_provider.knows("my_agent")
    assert not restored.uvm_provider.knows("no_such_class")


def test_another_root_parses_once_in_that_process(tmp_path):
    index = open_index(_options("basic_tb.sv"), cache_dir=str(tmp_path))
    expected = index.uvm_provider.get("my_agent")
    clear_index_cache()

    restored = pickle.loads(pickle.dumps(index))

    assert restored.uvm_provider.get("my_agent").children == expected.children


def test_uvm_structure_is_picklable_on_its_own():
    """The data the walk produces holds no pyslang references."""
    structure = uvm_stub_index("basic_tb.sv").uvm_structure

    restored = pickle.loads(pickle.dumps(structure))

    assert restored.root == structure.root
    assert restored.children == structure.children
