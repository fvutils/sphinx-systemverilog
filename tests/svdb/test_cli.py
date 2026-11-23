"""D1-IMPL-3/6: ``svdb validate`` and the rest of the command line."""

from __future__ import annotations

import json

import pytest

from sphinx_systemverilog import svdb
from sphinx_systemverilog.svdb.cli import main
from sphinx_systemverilog.svdb.validate import validate

from .conftest import HEADER, example, obj

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("name", svdb.example_names())
def test_examples_validate_clean(name):
    pytest.importorskip("jsonschema")
    report = validate(example(name))
    assert report.ok, [str(i) for i in report.issues]
    assert report.schema_checked and report.objects > 0 or name == "minimal.ndjson" or report.objects > 0


def test_validate_reports_schema_and_semantic_errors():
    pytest.importorskip("jsonschema")
    recs = [HEADER, obj("p", "package"), obj("p", "package", pos=1), obj("p::C", "class", colour="red")]
    report = validate(recs)
    codes = {i.code for i in report.errors}
    assert {"Schema", "DuplicateKey"} <= codes
    assert any("colour" in i.message for i in report.errors if i.code == "Schema")


def test_validate_counts_unresolved_and_external():
    recs = [HEADER, obj("p", "package"),
            obj("p::C", "class", detail={"extends": {"text": "Nope", "refs": [{"at": [0, 4], "name": "Nope"}]}}),
            obj("p::D", "class", pos=1, detail={"extends": {"text": "uvm_object", "refs": [
                {"at": [0, 10], "name": "uvm_object", "target": "uvm_pkg::uvm_object"}]}})]
    report = validate(recs, check_schema=False)
    assert report.ok and (report.unresolved, report.external) == (1, 1)


def test_validate_fatal_header():
    report = validate([dict(HEADER, schema="3.1")], check_schema=False)
    assert not report.ok and report.errors[-1].code == "Fatal"


@pytest.fixture
def files(tmp_path):
    src = tmp_path / "classes.ndjson"
    src.write_text(svdb.example_text("classes.ndjson"))
    db = tmp_path / "classes.svdb"
    assert main(["import", str(src), "-o", str(db)]) == 0
    return src, db


def test_cli_import_export(files, tmp_path, capsys):
    src, db = files
    out = tmp_path / "out.ndjson"
    assert main(["export", str(db), "-o", str(out)]) == 0
    assert len(out.read_text().splitlines()) == len(src.read_text().splitlines())
    assert main(["export", str(db)]) == 0
    assert capsys.readouterr().out == out.read_text()


def test_cli_validate(files, tmp_path, capsys):
    src, db = files
    assert main(["validate", str(src)]) == 0
    assert main(["validate", str(db), "--no-schema"]) == 0
    assert "0 error(s)" in capsys.readouterr().out
    bad = tmp_path / "bad.ndjson"
    bad.write_text("\n".join(json.dumps(r) for r in [HEADER, obj("p", "package"), obj("p", "package", pos=1)]))
    assert main(["validate", str(bad), "--no-schema"]) == 1
    assert "DuplicateKey" in capsys.readouterr().out


def test_cli_stats(files, capsys):
    _, db = files
    assert main(["stats", str(db), "--unresolved", "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["kinds"]["class"] >= 4 and stats["sections"]["objects"] == "complete"
    assert main(["stats", str(db)]) == 0
    assert "references:" in capsys.readouterr().out


def test_cli_query(files, capsys):
    _, db = files
    assert main(["query", "-d", str(db), "get", "env_pkg::word_item"]) == 0
    assert "class" in capsys.readouterr().out
    assert main(["query", "-d", str(db), "get", "env_pkg::word_item", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["qname"] == "env_pkg::word_item"
    assert main(["query", "-d", str(db), "derived", "env_pkg::base_item"]) == 0
    assert "env_pkg::word_item" in capsys.readouterr().out
    assert main(["query", "-d", str(db), "bases", "env_pkg::base_item"]) == 0
    assert "(unresolved) uvm_sequence_item -> uvm_pkg::uvm_sequence_item" in capsys.readouterr().out
    assert main(["query", "-d", str(db), "find", "env_pkg::*", "--kind", "constraint"]) == 0
    assert capsys.readouterr().out.count("constraint") == 2
    assert main(["query", "-d", str(db), "refs", "env_pkg::base_item"]) == 0
    assert "extends" in capsys.readouterr().out
    assert main(["query", "-d", str(db), "get", "render"]) == 2
    assert "ambiguous" in capsys.readouterr().err
    assert main(["query", "-d", str(db), "get", "nothing"]) == 1


def test_cli_sql_and_errors(files, tmp_path, capsys):
    _, db = files
    assert main(["sql", str(db), "SELECT count(*) FROM object WHERE kind = ?", "class"]) == 0
    assert int(capsys.readouterr().out) >= 4
    assert main(["sql", str(db), "DROP TABLE object"]) == 1
    assert main(["export", str(tmp_path / "missing.svdb")]) == 1
    assert "no such database" in capsys.readouterr().err


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    assert "import" in capsys.readouterr().out


# -- uvm-tree --------------------------------------------------------------------


@pytest.fixture
def uvm_db(tmp_path):
    src = tmp_path / "uvm.ndjson"
    src.write_text(svdb.example_text("uvm.ndjson"))
    db = tmp_path / "uvm.svdb"
    assert main(["import", str(src), "-o", str(db)]) == 0
    return db


def test_cli_uvm_tree_json(uvm_db, capsys):
    assert main(["uvm-tree", "-d", str(uvm_db)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["format"] == "svdb-uvm-tree"
    assert data["root"] == {"name": "uvm_test_top", "type": "my_pkg::my_test"}
    assert {n["path"] for n in data["nodes"]} >= {"uvm_test_top", "uvm_test_top.env"}


def test_cli_uvm_tree_formats(uvm_db, capsys):
    assert main(["uvm-tree", "-d", str(uvm_db), "--format", "nested"]) == 0
    (root,) = json.loads(capsys.readouterr().out)["nodes"]
    assert root["children"][0]["name"] == "env"
    assert main(["uvm-tree", "-d", str(uvm_db), "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("uvm_test_top : my_test")
    assert main(["uvm-tree", "-d", str(uvm_db), "--format", "dot"]) == 0
    assert capsys.readouterr().out.startswith("digraph uvm {")


def test_cli_uvm_tree_options(uvm_db, tmp_path, capsys):
    out = tmp_path / "tree.json"
    assert main(["uvm-tree", "-d", str(uvm_db), "--root", "my_env", "--name", "top", "-o", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["root"] == {"name": "top", "type": "my_pkg::my_env"}
    assert main(["uvm-tree", "-d", str(uvm_db), "--no-conditional", "--format", "text"]) == 0
    assert "sb :" not in capsys.readouterr().out


def test_cli_uvm_tree_missing_root(uvm_db, capsys):
    assert main(["uvm-tree", "-d", str(uvm_db), "--root", "no_such_test"]) == 1
    assert "no_such_test" in capsys.readouterr().err
