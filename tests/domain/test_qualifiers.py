"""Class and method qualifiers: what tells a reader ``T::create`` is static, a
method must be overridden, or a class is an interface.

Covered on both model paths: elaborated classes (from symbols) and
parameterized classes (recovered from syntax).
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_systemverilog.model import ModelBuilder
from pathlib import Path

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parent.parent / "fixtures" / "qualifiers"
CONF = {"sv_source_dirs": [str(SRC)]}


@pytest.fixture(scope="module")
def pkg():
    roots = ModelBuilder().build_from_text((SRC / "qual_pkg.sv").read_text())
    return roots[0]


def _get(obj, path):
    for name in path.split("."):
        obj = next(c for c in obj.children if c.name == name)
    return obj


@pytest.mark.parametrize("path, quals", [
    ("q_if", {"interface"}),
    ("q_if.f", {"pure", "virtual"}),
    ("q_base", {"virtual"}),
    ("q_base.make", {"static"}),
    ("q_base.helper", {"protected", "static"}),
    ("q_base.hook", {"local", "virtual"}),
    ("q_base.must", {"pure", "virtual"}),
    ("q_gif", {"interface"}),
    ("q_gif.create", {"pure", "virtual"}),
    ("q_gen", {"virtual"}),
    ("q_gen.get", {"static"}),
    ("q_gen.hook", {"protected", "virtual"}),
])
def test_model_qualifiers(pkg, path, quals):
    got = set(_get(pkg, path).qualifiers) - {"parameterized"}
    assert got == quals


def test_extern_is_not_a_qualifier(pkg):
    assert "extern" not in _get(pkg, "q_base.make").qualifiers
    assert "extern" not in _get(pkg, "q_gen.get").qualifiers


@pytest.mark.sphinx("html", testroot="qualifiers", confoverrides=CONF)
def test_rendered_qualifier_order(app):
    app.build()
    doctree = app.env.get_doctree("index")
    sigs = [s.astext() for s in doctree.findall(addnodes.desc_signature)]

    def sig(fragment):
        return next(s for s in sigs if fragment in s)

    assert sig("q_if").startswith("interface class q_if")
    assert sig(" f(").startswith("pure virtual function int f(")
    assert sig("make(").startswith("static function q_base make(")
    assert sig("helper(").startswith("protected static function int helper(")
    assert sig("must(").startswith("pure virtual function void must(")
    assert "interface" in sig("q_gif").split("class")[0]
    assert sig("create(").startswith("pure virtual function T create(")
    assert "virtual" in sig("q_gen").split("class")[0]
    assert sig("get(").startswith("static function this_t get(")
