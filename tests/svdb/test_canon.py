"""D0-TEST-2: canonical names, keys, elaboration keys and content hashes."""

from __future__ import annotations

import hashlib

import pytest

from sphinx_systemverilog.svdb import canon
from sphinx_systemverilog.svdb.canon import Key, QNameError

pytestmark = pytest.mark.unit


# -- qnames --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,segments",
    [
        ("a", ["a"]),
        ("pkg::cls::m", ["pkg", "cls", "m"]),
        ("top::genblk2#1", ["top", "genblk2#1"]),
        ("m::$assertion#3", ["m", "$assertion#3"]),
        # Escaped identifiers may contain '::' and '#'; the terminating space
        # belongs to the segment.
        ("top::\\a::b ::x", ["top", "\\a::b ", "x"]),
        ("\\bus[0] ", ["\\bus[0] "]),
        ("top::\\a#1 ", ["top", "\\a#1 "]),
        ("top::\\a+b #2::y", ["top", "\\a+b #2", "y"]),
    ],
)
def test_qname_round_trip(text, segments):
    assert canon.parse_qname(text) == segments
    assert canon.format_qname(segments) == text


def test_escaped_identifier_at_end_gains_its_space():
    assert canon.parse_qname("top::\\a+b") == ["top", "\\a+b "]
    assert canon.join("top", "\\a+b") == "top::\\a+b "
    assert canon.join(None, "x") == "x"


@pytest.mark.parametrize("bad", ["", "::a", "a::", "a::::b", "a b", "\\", "a::\\ ", "\\a #"])
def test_malformed_qnames(bad):
    with pytest.raises(QNameError):
        canon.parse_qname(bad)


@pytest.mark.parametrize(
    "seg,base",
    [
        ("genblk2#1", "genblk2"),
        ("g_lane", "g_lane"),
        ("$process#0", "$process#0"),
        ("\\a#1 ", "\\a#1 "),       # '#' inside the escaped name is the name
        ("\\a+b #2", "\\a+b "),     # after the space it is a disambiguator
        ("x#y", "x#y"),
    ],
)
def test_base_name(seg, base):
    assert canon.base_name(seg) == base


@pytest.mark.parametrize(
    "kind,ns",
    [("package", "package"), ("module", "design"), ("interface", "design"), ("program", "design"),
     ("checker", "design"), ("primitive", "design"), ("config", "design"), ("macro", "macro"),
     ("class", "unit"), ("typedef", "unit"), ("function", "unit")],
)
def test_root_ns(kind, ns):
    assert canon.root_ns(kind) == ns


# -- keys ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,key",
    [
        ("pkg::cls", Key("pkg::cls")),
        ("package:foo", Key("foo", "package")),
        ("design:foo::bar", Key("foo::bar", "design")),
        ("$unit[cu1]::byte_t", Key("byte_t", "unit", "cu1")),
        ("design::x", Key("design::x")),           # a package called 'design'
        ("\\a:b ", Key("\\a:b ")),                   # colon inside an escaped name
        ("top::\\a:b ", Key("top::\\a:b ")),
    ],
)
def test_parse_key(text, key):
    assert canon.parse_key(text) == key


def test_format_key():
    assert canon.format_key(Key("foo", "package")) == "foo"
    assert canon.format_key(Key("foo", "package"), qualify=True) == "package:foo"
    assert canon.format_key(Key("t", "unit", "cu0"), qualify=True) == "$unit[cu0]::t"
    for text in ("package:foo", "$unit[cu0]::t"):
        assert canon.format_key(canon.parse_key(text), qualify=True) == text


@pytest.mark.parametrize("bad", ["widget:foo", "$unit[]::x", "$unit[cu0]x", "package:"])
def test_malformed_keys(bad):
    with pytest.raises(QNameError):
        canon.parse_key(bad)


# -- generated names (LRM 27.6) -----------------------------------------------


def test_genblk_numbers_count_every_construct():
    # LRM 27.6 example: named constructs consume a number too.
    assert canon.genblk_names([None, "g_named", None]) == ["genblk1", "g_named", "genblk3"]


def test_genblk_adds_leading_zeros_on_conflict():
    # A declared 'genblk1' forces the unnamed first construct to 'genblk01';
    # a further clash adds another zero.
    assert canon.genblk_names([None], declared={"genblk1"}) == ["genblk01"]
    assert canon.genblk_names([None], declared={"genblk1", "genblk01"}) == ["genblk001"]
    # A label on another construct counts as declared.
    assert canon.genblk_names(["genblk2", None]) == ["genblk2", "genblk02"]


def test_disambiguate_arms():
    assert canon.disambiguate(["genblk2", "genblk2"]) == ["genblk2", "genblk2#1"]
    assert canon.disambiguate(["a", "b", "a", "a"]) == ["a", "b", "a#1", "a#2"]


def test_anonymous_name():
    assert canon.anonymous_name("assertion", 0) == "$assertion#0"
    with pytest.raises(ValueError):
        canon.anonymous_name("process", -1)


# -- elaboration keys ----------------------------------------------------------


def test_elab_key_ignores_parameter_order():
    a = canon.elab_key([("W", "8"), ("D", "4")])
    b = canon.elab_key([("D", "4"), ("W", "8")])
    assert a == b and len(a) == 16


def test_elab_key_definition():
    # Normative: sha256 over sorted 'name=value' lines joined by '\n'.
    expected = hashlib.sha256(b"D=4\nW=8").hexdigest()[:16]
    assert canon.elab_key([("W", "8"), ("D", "4")]) == expected
    assert canon.elab_key([]) == hashlib.sha256(b"").hexdigest()[:16]


def test_elab_key_distinguishes_values_and_rejects_duplicates():
    assert canon.elab_key([("W", "8")]) != canon.elab_key([("W", "16")])
    with pytest.raises(ValueError):
        canon.elab_key([("W", "8"), ("W", "9")])


def test_elab_ref():
    assert canon.elab_ref("leaf", "0123456789abcdef") == "leaf@0123456789abcdef"


# -- canonical JSON and content hash -------------------------------------------


def test_canonical_json_sorts_keys_by_utf16():
    # JCS sorts by UTF-16 code units: U+1F600 (surrogates D83D DE00) sorts
    # *before* U+FFFD, the reverse of code-point order.
    value = {"b": 1, "a": [True, None, "x"], "�": 0, "\U0001F600": 0}
    text = canon.canonical_json(value)
    assert text.startswith('{"a":[true,null,"x"],"b":1,')
    assert text.index("\U0001F600") < text.index("�")


def test_canonical_json_rejects_floats():
    with pytest.raises(TypeError):
        canon.canonical_json({"x": 1.5})


_OBJ = {
    "r": "object", "kind": "function", "ns": "package", "qname": "p::f", "name": "f",
    "parent": "p", "pos": 3, "loc": {"file": "f1", "line": 10, "col": 3},
    "sig": "function void f()", "doc": {"text": "Does f.", "loc": {"file": "f1", "line": 9}},
    "via": [{"macro": "M", "loc": {"file": "f1", "line": 10}}],
}


def test_hash_ignores_position():
    moved = dict(_OBJ, pos=7, loc={"file": "f1", "line": 99, "col": 1},
                 doc={"text": "Does f.", "loc": {"file": "f1", "line": 98}},
                 via=[{"macro": "M", "loc": {"file": "f1", "line": 99}}],
                 extent={"file": "f1", "line": 99}, body_loc={"file": "f1", "line": 120})
    assert canon.object_hash(moved) == canon.object_hash(_OBJ)


def test_hash_tracks_content():
    base = canon.object_hash(_OBJ)
    assert canon.object_hash(dict(_OBJ, sig="function int f()")) != base
    assert canon.object_hash(dict(_OBJ, doc={"text": "Does g."})) != base
    assert canon.object_hash(_OBJ, body="return;") != base
    assert canon.object_hash(_OBJ, body="return;") != canon.object_hash(_OBJ, body="return 1;")
    # A stale hash in the record does not feed into the new one.
    assert canon.object_hash(dict(_OBJ, hash="0" * 64)) == base
