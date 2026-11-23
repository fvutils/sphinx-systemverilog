"""Canonical forms shared by every svdb producer and reader.

Everything here is part of the interchange contract (``svdb-1.schema.json`` and
``docs/design/svdb-schema-plan.md`` §3, §6): two producers that follow these
rules give the same object the same name, the same elaboration the same key,
and the same content the same hash.  Nothing here imports Sphinx or pyslang.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, NamedTuple

#: The four name spaces of LRM 3.13 that svdb keeps apart.
NAMESPACES = ("design", "package", "unit", "macro")

#: Name space of a *root* object, by kind.  A root of any other kind lives at
#: compilation-unit scope.
_ROOT_NS = {
    "package": "package",
    "module": "design",
    "interface": "design",
    "program": "design",
    "checker": "design",
    "primitive": "design",
    "config": "design",
    "macro": "macro",
}

SEP = "::"


class QNameError(ValueError):
    """A string is not a well-formed qname or key."""


# -- qualified names -----------------------------------------------------------


def parse_qname(text: str) -> list[str]:
    """Split *text* into segments, each in its canonical written form.

    Segments are separated by ``::``.  An escaped identifier (``\\a::b ``)
    runs to the first whitespace and may itself contain ``::`` or ``#``; its
    segment keeps the backslash and exactly one terminating space, which is
    supplied when the string ends without one.  Any segment may carry a
    ``#<n>`` disambiguator (§3.3); after an escaped identifier it follows the
    space: ``\\a+b #1``.
    """
    if not text:
        raise QNameError("empty qname")
    segs: list[str] = []
    i, n = 0, len(text)
    while True:
        if i >= n:
            raise QNameError(f"empty segment at end of {text!r}")
        if text[i] == "\\":
            j = i + 1
            while j < n and not text[j].isspace():
                j += 1
            if j == i + 1:
                raise QNameError(f"empty escaped identifier in {text!r}")
            seg = text[i:j] + " "
            if j < n:
                j += 1
            if j < n and text[j] == "#":
                k = j + 1
                while k < n and text[k].isdigit():
                    k += 1
                if k == j + 1:
                    raise QNameError(f"'#' without ordinal in {text!r}")
                seg += text[j:k]
                j = k
            segs.append(seg)
            i = j
        else:
            j = text.find(SEP, i)
            seg = text[i:] if j < 0 else text[i:j]
            if not seg:
                raise QNameError(f"empty segment in {text!r}")
            if any(c.isspace() for c in seg):
                raise QNameError(f"whitespace in segment {seg!r} of {text!r}")
            segs.append(seg)
            i = n if j < 0 else j
        if i >= n:
            return segs
        if not text.startswith(SEP, i):
            raise QNameError(f"expected '::' at offset {i} of {text!r}")
        i += len(SEP)


def segment(name: str) -> str:
    """The canonical segment for a declared *name* (as stored in ``name``).

    An escaped identifier gains its terminating space; anything else is
    returned unchanged.
    """
    if not name:
        raise QNameError("empty name")
    if name.startswith("\\") and " " not in name:
        return name + " "
    return name


def format_qname(segments: Iterable[str]) -> str:
    """Join *segments* into a canonical qname (inverse of :func:`parse_qname`)."""
    segs = [segment(s) for s in segments]
    if not segs:
        raise QNameError("no segments")
    return SEP.join(segs)


def join(parent: str | None, name: str) -> str:
    """The qname of *name* declared in *parent* (``None`` for a root)."""
    seg = segment(name)
    return seg if not parent else parent + SEP + seg


def base_name(seg: str) -> str:
    """A segment without its ``#<n>`` disambiguator."""
    if seg.startswith("$"):
        return seg
    head, sep, tail = seg.rpartition("#")
    if not sep or not tail.isdigit():
        return seg
    # In an escaped identifier a '#' before the terminating space is part of
    # the name; the disambiguator always follows that space.
    if seg.startswith("\\") and not head.endswith(" "):
        return seg
    return head


def root_ns(kind: str) -> str:
    """The name space a root object of *kind* belongs to."""
    return _ROOT_NS.get(kind, "unit")


# -- keys: the text form of an identity ----------------------------------------


class Key(NamedTuple):
    """An object identity: ``(ns, unit, qname)``.

    ``ns`` and ``unit`` are ``None`` when the text form left them implicit; the
    reader then resolves across name spaces and reports ambiguity.
    """

    qname: str
    ns: str | None = None
    unit: str | None = None

    def __str__(self) -> str:
        return format_key(self)


_UNIT_PREFIX = "$unit["


def parse_key(text: str) -> Key:
    """Parse ``[ns:]qname`` or ``$unit[<id>]::qname``."""
    if text.startswith(_UNIT_PREFIX):
        close = text.find("]", len(_UNIT_PREFIX))
        if close < 0 or not text.startswith(SEP, close + 1):
            raise QNameError(f"malformed $unit key {text!r}")
        unit = text[len(_UNIT_PREFIX):close]
        if not unit:
            raise QNameError(f"empty unit id in {text!r}")
        qname = text[close + 1 + len(SEP):]
        parse_qname(qname)
        return Key(qname, "unit", unit)
    # 'ns:' is a single colon directly after a bare word; '::' is a separator.
    colon = text.find(":")
    if colon > 0 and not text.startswith("\\") and text[colon:colon + 2] != SEP:
        ns = text[:colon]
        if ns not in NAMESPACES:
            raise QNameError(f"unknown name space {ns!r} in {text!r}")
        qname = text[colon + 1:]
        parse_qname(qname)
        return Key(qname, ns)
    parse_qname(text)
    return Key(text)


def format_key(key: Key, *, qualify: bool = False) -> str:
    """The text form of *key*.

    The ``ns:`` prefix is written when *qualify* is true (the caller knows the
    bare qname is ambiguous); a compilation-unit key with a ``unit`` always
    uses the ``$unit[...]`` form when qualified.
    """
    if qualify and key.ns == "unit" and key.unit:
        return f"{_UNIT_PREFIX}{key.unit}]{SEP}{key.qname}"
    if qualify and key.ns:
        return f"{key.ns}:{key.qname}"
    return key.qname


# -- generated names -----------------------------------------------------------


def genblk_names(constructs: Iterable[str | None], declared: Iterable[str] = ()) -> list[str]:
    """Names of the generate constructs in one scope, per LRM 27.6.

    *constructs* lists every generate construct in the scope in source order:
    its label, or ``None`` when unnamed.  Every construct is numbered from 1,
    named or not; an unnamed one is called ``genblk<n>``.  If that name clashes
    with a name declared in the scope (*declared*, which should include the
    labels), leading zeros are added to the number until it does not.
    """
    items = list(constructs)
    taken = set(declared) | {c for c in items if c}
    out: list[str] = []
    for number, label in enumerate(items, start=1):
        if label:
            out.append(label)
            continue
        digits = str(number)
        name = "genblk" + digits
        while name in taken:
            digits = "0" + digits
            name = "genblk" + digits
        out.append(name)
    return out


def disambiguate(names: Iterable[str]) -> list[str]:
    """Make repeated sibling names unique with a ``#<n>`` suffix.

    The first occurrence keeps its name; the k-th repeat (k >= 1) becomes
    ``name#k``.  Used for the arms of one if/case generate construct, which may
    legally share a name because only one of them is ever elaborated.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        k = seen.get(name, 0)
        out.append(name if k == 0 else f"{name}#{k}")
        seen[name] = k + 1
    return out


def anonymous_name(kind: str, ordinal: int) -> str:
    """Name of the *ordinal*-th (0-based) unnamed object of *kind* in a parent."""
    if ordinal < 0:
        raise ValueError("ordinal must be >= 0")
    return f"${kind}#{ordinal}"


# -- elaboration key -----------------------------------------------------------


def elab_key(params: Iterable[tuple[str, str]]) -> str:
    """The key of one elaboration: 16 hex digits identifying a parameter set.

    SHA-256 over the UTF-8 bytes of ``name=value`` lines joined by ``\\n``,
    sorted by name (code-point order), where *value* is the full value text --
    the identity, never the display text.  An unparameterized definition has
    the key of the empty set.
    """
    lines = sorted(f"{n}={v}" for n, v in params)
    names = [ln.split("=", 1)[0] for ln in lines]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate parameter name in {names}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def elab_ref(definition: str, key: str) -> str:
    """The text form of a reference to an elaboration: ``<def>@<key>``."""
    return f"{definition}@{key}"


# -- canonical JSON and content hash -------------------------------------------


def canonical_json(value: Any) -> str:
    """RFC 8785 (JCS) serialization of *value*, restricted to svdb's types.

    svdb records hold only strings, integers, booleans, null, arrays and
    objects; floats are rejected rather than risk a number-formatting
    mismatch between producers.  Object keys are sorted by UTF-16 code units,
    as JCS requires.
    """
    return "".join(_jcs(value))


def _jcs(value: Any) -> Iterable[str]:
    if value is None or value is True or value is False or isinstance(value, str):
        yield json.dumps(value, ensure_ascii=False)
    elif isinstance(value, int):
        yield str(value)
    elif isinstance(value, float):
        raise TypeError("svdb records do not contain floating-point numbers")
    elif isinstance(value, (list, tuple)):
        yield "["
        for i, item in enumerate(value):
            if i:
                yield ","
            yield from _jcs(item)
        yield "]"
    elif isinstance(value, dict):
        yield "{"
        for i, k in enumerate(sorted(value, key=lambda s: s.encode("utf-16-be"))):
            if not isinstance(k, str):
                raise TypeError("object keys must be strings")
            if i:
                yield ","
            yield json.dumps(k, ensure_ascii=False)
            yield ":"
            yield from _jcs(value[k])
        yield "}"
    else:
        raise TypeError(f"cannot serialize {type(value).__name__}")


#: Fields excluded from an object's content hash: positions only.  An edit
#: above a declaration moves it without changing it (plan §6.3, decision #6).
HASH_EXCLUDED = ("hash", "loc", "extent", "body_loc", "pos")


def object_hash(record: dict, body: str | None = None) -> str:
    """Content hash of an ``object`` record (hex SHA-256).

    Covers the record without :data:`HASH_EXCLUDED` fields and without the
    location inside ``doc`` and ``via``, followed by the text of the object's
    ``body`` record when there is one.
    """
    clean = {k: v for k, v in record.items() if k not in HASH_EXCLUDED}
    if isinstance(clean.get("doc"), dict):
        clean["doc"] = {k: v for k, v in clean["doc"].items() if k != "loc"}
    if isinstance(clean.get("via"), list):
        clean["via"] = [{k: v for k, v in step.items() if k != "loc"} for step in clean["via"]]
    h = hashlib.sha256(canonical_json(clean).encode("utf-8"))
    if body is not None:
        h.update(b"\n")
        h.update(body.encode("utf-8"))
    return h.hexdigest()
