"""Inline markup conversion shared by the NaturalDocs and Doxygen dialects.

NaturalDocs writes cross-references as ``<symbol>`` and inline code as
``~code~``; Doxygen uses ``#symbol`` / ``@p name``.  Both normalize to
reStructuredText so the rest of the pipeline is dialect-agnostic.
"""

from __future__ import annotations

import re

from .sanitize import literal_line_mask, match_list_item

# A NaturalDocs <reference>: an identifier, scoped name, or method-ish token.
# Deliberately conservative so prose like "a < b" or generics are left alone.
_ANGLE_XREF = re.compile(r"<([A-Za-z_][\w]*(?:::[A-Za-z_]\w*)*(?:\(\))?)>")

# NaturalDocs ~inline code~ (no embedded tilde or newline).
_TILDE_CODE = re.compile(r"~([^~\n]+)~")


def convert_angle_xrefs(text: str) -> str:
    """Turn ``<symbol>`` references into ``:sv:obj:`symbol``` roles."""

    def repl(m: "re.Match[str]") -> str:
        target = m.group(1)
        return f":sv:obj:`{target}`"

    return _ANGLE_XREF.sub(repl, text)


def convert_tilde_code(text: str) -> str:
    """Turn ``~code~`` spans into reStructuredText ``\\`\\`code\\`\\``` literals."""

    def repl(m: "re.Match[str]") -> str:
        return f"``{m.group(1)}``"

    return _TILDE_CODE.sub(repl, text)


# RST inline-markup characters that, left raw in prose, trigger
# "start-string without end-string" warnings.
_RST_SPECIAL = re.compile(r"([*`|])")

# A trailing underscore at a word boundary (``rhs_``) is an RST reference and
# triggers "Unknown target name" errors; escape it without touching internal
# underscores in identifiers like ``get_name``.
_TRAILING_UNDERSCORE = re.compile(r"(?<=\w)_(?=\W|$)")


def escape_rst_inline(text: str) -> str:
    """Backslash-escape stray RST inline-markup characters in prose.

    Applied to NaturalDocs/Doxygen prose (which is not authored as RST) *before*
    our own conversions add intentional ``literals`` and roles, so those survive.

    Works line by line so a leading list marker survives verbatim: escaping a
    ``*`` bullet into ``\\*`` would stop it ever rendering as a list, and the
    Doxygen dialect escapes *before* :func:`~.sanitize.sanitize_prose` runs, so
    the marker has to still be there when the folder looks for it.  Everything
    after the marker -- and every non-leading ``*`` in prose -- escapes as before.

    Lines inside a literal block are left alone: they are code, and a backslash
    escape would be rendered rather than consumed.
    """
    literal = literal_line_mask(text)
    return "\n".join(
        line if is_literal else _escape_line(line)
        for line, is_literal in zip(text.split("\n"), literal)
    )


def _escape_line(line: str) -> str:
    marker = match_list_item(line)
    prefix, rest = ("", line) if marker is None else (marker.group(0), line[marker.end():])
    rest = _RST_SPECIAL.sub(r"\\\1", rest)
    return prefix + _TRAILING_UNDERSCORE.sub(r"\\_", rest)


def convert_inline(text: str) -> str:
    """Apply all NaturalDocs inline conversions (escaping stray RST first).

    Literal-block lines are passed through: ``~`` and ``<...>`` inside a code
    sample are the language's own syntax, not NaturalDocs markup.
    """
    literal = literal_line_mask(text)
    escaped = escape_rst_inline(text).split("\n")
    return "\n".join(
        line if is_literal else convert_angle_xrefs(convert_tilde_code(line))
        for line, is_literal in zip(escaped, literal)
    )


def collect_angle_xrefs(text: str) -> list[str]:
    return _ANGLE_XREF.findall(text)
