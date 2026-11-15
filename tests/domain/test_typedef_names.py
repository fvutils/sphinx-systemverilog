"""Signatures show types as written: a typedef's name, not what slang resolves
it to, and a typedef's own declaration."""

from __future__ import annotations

from pathlib import Path

import pytest
from sphinx import addnodes

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parent.parent / "fixtures" / "qualifiers"
CONF = {"sv_source_dirs": [str(SRC)]}


@pytest.fixture(scope="module")
def pkg():
    return ModelBuilder().build_from_text((SRC / "types_pkg.sv").read_text())[0]


def _get(obj, path):
    for name in path.split("."):
        obj = next(c for c in obj.children if c.name == name)
    return obj


@pytest.mark.parametrize("path, sig", [
    ("pair_t", "typedef int pair_t[2]"),
    ("cfg_t", "typedef struct { ... } cfg_t"),
    ("user.params_t", "typedef struct { ... } params_t"),
    ("user.mk", "function params_t mk(pair_t pairs[], cfg_t c)"),
    ("user.pp", "pair_t pp[3]"),
])
def test_signatures_as_written(pkg, path, sig):
    assert _get(pkg, path).signature == sig


@pytest.mark.sphinx("html", testroot="qualifiers", confoverrides=CONF)
def test_rendered_typedefs(app):
    app.build()
    doctree = app.env.get_doctree("index")
    sigs = [s.astext() for s in doctree.findall(addnodes.desc_signature)]
    assert any(s.startswith("typedef int pair_t[2]") for s in sigs), sigs
    assert any(s.startswith("static function params_t mk(pair_t pairs[], cfg_t c)")
               for s in sigs)
    # The keyword is not a cross-reference.
    targets = {x["reftarget"] for x in doctree.findall(addnodes.pending_xref)}
    assert "typedef" not in targets


def test_parameterized_class_typedefs_are_members():
    roots = ModelBuilder().build_from_text(
        "package p;\n"
        "  class g #(type T = int);\n"
        "    // This class.\n"
        "    typedef g #(T) this_t;\n"
        "  endclass\n"
        "endpackage\n")
    (g,) = roots[0].children
    (td,) = [c for c in g.children if c.kind == "typedef"]
    assert (td.name, td.signature, td.raw_doc) == ("this_t", "typedef g #(T) this_t", "This class.")
