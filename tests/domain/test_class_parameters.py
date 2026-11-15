"""A parameterized class shows its parameter list in its signature, and a class
parameter with its own doc comment is documented as a member."""

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
    return ModelBuilder().build_from_text((SRC / "gen_pkg.sv").read_text())[0]


def _cls(pkg, name):
    return next(c for c in pkg.children if c.name == name)


def test_signature_carries_parameter_list(pkg):
    assert _cls(pkg, "holder").signature == "holder #(type T = bit, int unsigned W = $bits(T))"
    # A multi-line list, with comments, collapses to one line without them.
    assert _cls(pkg, "shaped").signature == "shaped #(int DW = 8, int AW = 4)"
    assert _cls(pkg, "mix").signature == "mix #(type B = holder #(bit))"


def test_class_parameters_are_members(pkg):
    params = [c for c in _cls(pkg, "shaped").children if c.kind == "parameter"]
    assert [(p.name, p.raw_doc) for p in params] == [
        ("DW", "the data width"), ("AW", "the address width")]


@pytest.mark.sphinx("html", testroot="qualifiers", confoverrides=CONF)
def test_rendered_class_signature(app):
    app.build()
    doctree = app.env.get_doctree("index")
    sigs = [s.astext() for s in doctree.findall(addnodes.desc_signature)]

    def sig(fragment):
        return next(s for s in sigs if fragment in s)

    assert sig("holder #(").startswith("class holder #(type T = bit, int unsigned W = $bits(T))")
    assert "parameterized" not in " ".join(sigs)
    assert sig("mix #(").startswith("class mix #(type B = holder #(bit))  extends B")
    # Documented class parameters are members; holder's undocumented T and W
    # are in the signature only.
    assert any(s.startswith("parameter int DW = 8") for s in sigs)
    assert not any(s.startswith("parameter type T") for s in sigs)
