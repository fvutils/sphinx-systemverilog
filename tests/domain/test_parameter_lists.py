"""Argument lists rendered as real parameter lists, with linked types.

The parser must be forgiving: anything it does not understand falls back to the
opaque string the extension used to emit, rather than failing the build.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docutils import nodes
from sphinx import addnodes

from sphinx_systemverilog.domain import (
    _parse_arglist,
    _parse_argument,
    _split_top_level,
)

SIG_FIXTURES = Path(__file__).parent.parent / "fixtures" / "sig"
CONF = {"sv_source_dirs": [str(SIG_FIXTURES)]}


def _signature(app, contains):
    doctree = app.env.get_doctree("index")
    for sig in doctree.findall(addnodes.desc_signature):
        if contains in sig.astext():
            return sig
    raise AssertionError(f"no signature containing {contains!r}")


# -- P5-TEST-1: bracket-aware splitting ---------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("", [""]),
        ("a", ["a"]),
        ("a,b", ["a", "b"]),
        # A comma inside a bracket of any kind is not a separator.
        ("int q[$] = '{1, 2}, int b", ["int q[$] = '{1, 2}", " int b"]),
        ("f(a, b), c", ["f(a, b)", " c"]),
        ("int a[1:0], int b", ["int a[1:0]", " int b"]),
        # ...nor one inside a string literal.
        ('string s = "a, b", int n', ['string s = "a, b"', " int n"]),
        ('string s = "esc\\", x", int n', ['string s = "esc\\", x"', " int n"]),
    ],
)
def test_split_top_level(text, expected):
    assert _split_top_level(text, ",") == expected


@pytest.mark.unit
@pytest.mark.parametrize("text", ["a)", "(a", "a[1", 'a = "unterminated'])
def test_split_top_level_rejects_unbalanced(text):
    assert _split_top_level(text, ",") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig,expected",
    [
        # An empty list is a real zero-argument subroutine...
        ("function void f()", []),
        ("function void f(  )", []),
        ("function void f(int a)", ["int a"]),
        ("task t(int a, int b)", ["int a", "int b"]),
        ("function void f(int q[$] = '{1, 2}, int b = 3)", ["int q[$] = '{1, 2}", "int b = 3"]),
        ("function void f(int a)   ", ["int a"]),
    ],
)
def test_parse_arglist(sig, expected):
    assert _parse_arglist(sig) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "sig",
    [
        "function void f",          # no list at all
        "function void f(int a",    # unclosed
        "function void f(int a,)",  # empty trailing argument
        "function void f(,)",
    ],
)
def test_parse_arglist_rejects_what_it_cannot_read(sig):
    """...but ``None`` means "fall back", and must not be read as empty."""
    assert _parse_arglist(sig) is None


# -- P5-TEST-2: one argument at a time ----------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("int a", ("", "int", "a", "", "")),
        ("bit [7:0] data", ("", "bit [7:0]", "data", "", "")),
        ("output bit [7:0] data", ("output", "bit [7:0]", "data", "", "")),
        ("inout logic sel", ("inout", "logic", "sel", "", "")),
        ("ref int q[$]", ("ref", "int", "q", "[$]", "")),
        ("const ref int q", ("const ref", "int", "q", "", "")),
        ("byte d[]", ("", "byte", "d", "[]", "")),
        ("int assoc[string]", ("", "int", "assoc", "[string]", "")),
        ("int b = 3", ("", "int", "b", "", "3")),
        ("int q[$] = '{1, 2}", ("", "int", "q", "[$]", "'{1, 2}")),
        ('string s = "a, b"', ("", "string", "s", "", '"a, b"')),
        # Dimensions written apart from the declarator still bind to the name.
        ("bit [7:0] q [3]", ("", "bit [7:0]", "q", "[3]", "")),
        ("sig_payload p", ("", "sig_payload", "p", "", "")),
    ],
)
def test_parse_argument(text, expected):
    assert _parse_argument(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "[3]", "int 9bad", "int a = b = c"])
def test_parse_argument_rejects_non_declarations(text):
    assert _parse_argument(text) is None


# -- P5-TEST-3/4: rendered markup ---------------------------------------------


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_parameter_list_markup(app):
    app.build()
    sig = _signature(app, "transfer")
    plists = list(sig.findall(addnodes.desc_parameterlist))
    assert len(plists) == 1
    params = list(plists[0].findall(addnodes.desc_parameter))
    # ``input`` is the default direction, so the model does not restate it.
    assert [p.astext() for p in params] == ["bit[7:0] addr", "output bit[7:0] data"]
    html = (app.outdir / "index.html").read_text()
    assert "sig-param" in html


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_comma_in_default_is_one_argument(app):
    """D3: the case that makes naive comma-splitting wrong."""
    app.build()
    params = list(_signature(app, "seed").findall(addnodes.desc_parameter))
    assert [p.astext() for p in params] == ["int vals[$] = '{1, 2}", "int repeat_count = 3"]


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_string_default_containing_a_comma(app):
    app.build()
    params = list(_signature(app, "label").findall(addnodes.desc_parameter))
    assert [p.astext() for p in params] == ['string text = "a, b"']


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_no_argument_subroutine_renders_empty_parens(app):
    app.build()
    sig = _signature(app, "reset")
    plists = list(sig.findall(addnodes.desc_parameterlist))
    assert len(plists) == 1
    assert not list(plists[0].findall(addnodes.desc_parameter))
    assert "reset()" in sig.astext()


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_malformed_signature_falls_back_without_raising(app):
    """D2: polish is lost, the build is not."""
    app.build()
    sig = _signature(app, "malformed")
    assert not list(sig.findall(addnodes.desc_parameterlist))
    assert "(int a" in sig.astext()


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_hand_written_directives_get_parameter_lists_too(app):
    """D1: the domain parses, so both paths benefit."""
    app.build()
    params = list(_signature(app, "hand_written").findall(addnodes.desc_parameter))
    assert [p.astext() for p in params] == ["int a", "sig_payload p"]


# -- P5-TEST-7/8: linked types ------------------------------------------------


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_user_types_link_and_builtins_do_not(app):
    app.build()
    sig = _signature(app, "wrap")
    targets = [x["reftarget"] for x in sig.findall(addnodes.pending_xref)]
    # Both the return type and the argument type.
    assert targets == ["sig_payload", "sig_payload"]

    plain = _signature(app, "transfer")
    assert not list(plain.findall(addnodes.pending_xref))

    html = (app.outdir / "index.html").read_text()
    assert 'href="#sv-signatures_pkg-sig_payload"' in html


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_signature_xrefs_do_not_warn(app, warning):
    app.build()
    assert "cannot resolve" not in warning.getvalue()


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_queue_dimensions_bind_to_the_name(app):
    app.build()
    params = list(_signature(app, "push").findall(addnodes.desc_parameter))
    # ``ref`` carries to the following argument -- that is SV semantics, and
    # the model reproduces it.
    assert [p.astext() for p in params] == ["ref int q[$]", "ref int value"]
    # The dimensions are punctuation on the declarator, not part of the name.
    names = [n.astext() for n in params[0].findall(addnodes.desc_sig_name)]
    assert names == ["q"]


@pytest.mark.sphinx("html", testroot="signatures", confoverrides=CONF)
def test_default_values_are_marked_up(app):
    app.build()
    params = list(_signature(app, "seed").findall(addnodes.desc_parameter))
    defaults = [
        n.astext() for n in params[1].findall(nodes.inline)
        if "default_value" in n.get("classes", [])
    ]
    assert defaults == ["3"]
