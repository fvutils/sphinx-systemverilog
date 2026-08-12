"""How a signature is broken into nodes for display.

Covers the pieces that used to be dropped between the model and the page: the
``virtual`` qualifier, a function's return type, and unpacked dimensions (which
bind to the declarator, not to the name used for lookup).
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_systemverilog.domain import (
    _signature_name,
    _signature_return,
    _split_data_signature,
)
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)]}


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,name,expected",
    [
        ("function py_object call(py_tuple args)", "call", "py_object"),
        ("function void dispose()", "dispose", "void"),
        ("function bit [7:0] mask(int n)", "mask", "bit [7:0]"),
        # A hand-written signature may carry qualifiers inline; those are
        # rendered from the options, so they are not part of the return type.
        ("virtual function int f()", "f", "int"),
        ("static function int g()", "g", "int"),
        # Tasks have no return type.
        ("task drive(int cycles)", "drive", ""),
        # Nothing sensible to extract.
        ("f()", "f", ""),
        ("", "", ""),
    ],
)
def test_signature_return(sig, name, expected):
    kind = "task" if sig.startswith("task") else "function"
    assert _signature_return(sig, name, kind) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,expected",
    [
        ("int m_q[$]", "m_q"),
        ("byte m_dyn[]", "m_dyn"),
        ("int m_assoc[string]", "m_assoc"),
        ("logic[7:0] m_packed", "m_packed"),
        ("int m_init = 3", "m_init"),
    ],
)
def test_property_name_excludes_dimensions(sig, expected):
    """The lookup name must not carry dimensions, or targets/refs break."""
    assert _signature_name(sig, "property") == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,type_part,tail",
    [
        ("int m_q[$]", "int", "[$]"),
        ("byte m_dyn[]", "byte", "[]"),
        ("logic[7:0] m_packed", "logic[7:0]", ""),
        ("int m_init = 3", "int", "= 3"),
        ("int m_both[4] = 3", "int", "[4] = 3"),
    ],
)
def test_split_data_signature(sig, type_part, tail):
    name = _signature_name(sig, "property")
    assert _split_data_signature(sig, name) == (type_part, tail)


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_virtual_qualifier_is_rendered(app):
    """``:virtual:`` is a flag option, so its value is None when present."""
    app.build()
    html = (app.outdir / "index.html").read_text()
    # sample_pkg::sample_base declares `virtual function string get_name()`.
    assert "virtual" in html
    doctree = app.env.get_doctree("index")
    rendered = [
        sig.astext()
        for sig in doctree.findall(addnodes.desc_signature)
        if "get_name" in sig.astext()
    ]
    assert rendered, "get_name signature not found"
    assert rendered[0].startswith("virtual function string get_name")


@pytest.mark.sphinx("html", testroot="basic", confoverrides=CONF)
def test_return_type_is_rendered(app):
    app.build()
    doctree = app.env.get_doctree("index")
    rendered = [
        sig.astext()
        for sig in doctree.findall(addnodes.desc_signature)
        if "parity" in sig.astext()
    ]
    assert rendered, "parity signature not found"
    assert rendered[0].startswith("function bit parity(")
