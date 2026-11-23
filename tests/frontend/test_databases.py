"""D2-IMPL-5 and D2-IMPL-6: pre-built databases (``sv_databases``) and the
``svdb build`` command that makes them."""

from __future__ import annotations

import pytest

from sphinx_systemverilog.svdb import Database
from sphinx_systemverilog.svdb.cli import main
from tests.conftest import DESIGN, FIXTURES

pytestmark = pytest.mark.sphinx


@pytest.fixture(scope="module")
def sample_db(tmp_path_factory):
    out = tmp_path_factory.mktemp("prebuilt") / "sample.svdb"
    assert main(["build", "--source-dir", str(FIXTURES / "sample_pkg.sv"), "-o", str(out)]) == 0
    return out


def test_svdb_build_writes_a_database(sample_db, capsys):
    with Database.open(sample_db) as db:
        assert db.get("sample_pkg::sample_txn").kind == "class"
        assert db.headers[0]["producer"]["name"] == "sphinx-systemverilog"
    assert main(["validate", str(sample_db), "--no-schema"]) == 0


def test_svdb_build_reads_a_sphinx_conf(tmp_path, capsys):
    conf = tmp_path / "conf.py"
    conf.write_text(f"sv_source_dirs = [{str(DESIGN)!r}]\nsv_doc_style = 'native'\n")
    out = tmp_path / "design.svdb"
    assert main(["build", "--sphinx-conf", str(conf), "-o", str(out)]) == 0
    assert "object(s)" in capsys.readouterr().out
    with Database.open(out) as db:
        assert db.get("lane").kind == "module"
    assert main(["build", "-o", str(out)]) == 1, "nothing to parse"


@pytest.fixture
def databases_conf(sample_db):
    return {"sv_source_dirs": [str(DESIGN)], "sv_databases": [str(sample_db)]}


def test_a_prebuilt_database_is_documented_and_linked(make_app, rootdir, tmp_path, sample_db):
    import shutil

    src = tmp_path / "databases"
    shutil.copytree(rootdir / "test-databases", src)
    app = make_app("html", srcdir=src, confoverrides={
        "sv_source_dirs": [str(DESIGN)], "sv_databases": [{"path": str(sample_db), "role": "local"}]})
    app.build()
    text = app.env.get_doctree("index").astext()
    assert "lane" in text and "sample_txn" in text
    assert "cannot" not in app._warning.getvalue()
    html = (app.outdir / "index.html").read_text()
    assert 'href="#sample_pkg::sample_txn"' in html or "sample_pkg::sample_txn" in html


def test_the_front_end_comes_first(make_app, rootdir, tmp_path):
    """A name in both the sources and a database is the sources' object."""
    import shutil

    other = tmp_path / "other.svdb"
    stale = tmp_path / "lane.sv"
    stale.write_text("// stale copy\nmodule lane; endmodule\n")
    assert main(["build", "--source-dir", str(stale), "-o", str(other)]) == 0
    src = tmp_path / "databases"
    shutil.copytree(rootdir / "test-databases", src)
    app = make_app("html", srcdir=src, confoverrides={
        "sv_source_dirs": [str(DESIGN)], "sv_databases": [str(other)]})
    lane = app.env.sv_index.get("lane")
    assert lane.location.file.endswith("design/lane.sv")


def test_a_missing_database_is_a_configuration_error(make_app, rootdir, tmp_path):
    import shutil

    from sphinx.errors import ConfigError

    src = tmp_path / "databases"
    shutil.copytree(rootdir / "test-databases", src)
    with pytest.raises(ConfigError, match="no such database"):
        make_app("html", srcdir=src, confoverrides={
            "sv_source_dirs": [str(DESIGN)], "sv_databases": ["nope.svdb"]})
