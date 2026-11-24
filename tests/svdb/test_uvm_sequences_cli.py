"""``svdb uvm-sequences``: catalog, tree, users and tasks from database files
(run-phase plan, phase 4c)."""

from __future__ import annotations

import json

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, write
from sphinx_systemverilog.model.index import clear_index_cache
from sphinx_systemverilog.svdb.cli import main
from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("seqcli") / "calls.svdb"
    options = Options.make(build_units=[str(UVM_STUB / "mini_uvm.sv"), str(UVM_TB / "seq_call_tb.sv")],
                           include_dirs=[str(UVM_STUB)], doc_style="native")
    write(parse(options), options, str(path)).conn.close()
    clear_index_cache()
    return str(path)


def test_the_catalog_as_json(db, capsys):
    assert main(["uvm-sequences", "-d", db, "call_test"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert (data["root"], data["method"]) == ("call_test", "run_phase")
    assert [(e["type_name"], e["depth"]) for e in data["entries"]] == [
        ("call_seq", 1), ("tail_seq", 1), ("step_seq", 2)]
    assert data["entries"][0]["sites"][0]["via"] == ["super.run_phase()", "traffic()"]
    assert data["entries"][0]["sites"][0]["location"]["line"] > 0


def test_the_tree_as_text(db, capsys):
    assert main(["uvm-sequences", "-d", db, "call_test", "--view", "tree", "--format", "text"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "call_test.run_phase()"
    assert lines[1].startswith("  c: call_seq  on uvm_test_top.seqr  via super.run_phase() -> traffic()")
    assert lines[2].startswith("    s: step_seq  in repeat (2)  on uvm_test_top.seqr  via do_steps()")
    assert "(shown above)" in lines[3]


def test_users_and_tasks(db, capsys):
    assert main(["uvm-sequences", "-d", db, "step_seq", "--view", "users"]) == 0
    users = json.loads(capsys.readouterr().out)["users"]
    assert [(u["root"], u["depth"]) for u in users][:2] == [("call_base_test", 1), ("call_test", 2)]
    assert main(["uvm-sequences", "-d", db, "--view", "tasks", "--format", "text"]) == 0
    assert "call_test.run_phase()" in capsys.readouterr().out.splitlines()


def test_errors(db, capsys):
    assert main(["uvm-sequences", "-d", db, "nope"]) == 1
    assert "no behavioural task named 'nope'" in capsys.readouterr().err
    assert main(["uvm-sequences", "-d", db]) == 1
    assert "needs a class name" in capsys.readouterr().err
    assert main(["uvm-sequences", "-d", db, "call_test", "--view", "users"]) == 1
