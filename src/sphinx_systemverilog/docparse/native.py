"""The 'native' doc-comment dialect.

A low-ceremony, Python-docstring-like style: the first paragraph is the summary,
the remainder is reStructuredText, and reST field lists (``:param x:``,
``:returns:``) are passed through untouched.  This is the recommended style for
new SystemVerilog code because the comment body *is* already RST.
"""

from __future__ import annotations

import re
import textwrap

from .base import DocField, DocstringParser, ParsedDoc, register_parser

#: Matches a reST field line, e.g. ``:param addr: the address``.  The closing
#: colon must be followed by whitespace or the end of the line, so a line that
#: merely begins with a role (``:sv:func:`build` has a body``) is prose.  Only
#: unindented lines are fields: an indented one is code or a continuation.
_FIELD_RE = re.compile(r"^:(\w+)(?:\s+([^:`]+))?:(?:\s+(.*))?$")

#: Inline cross-reference written as :sv:...:`name` - captured as an xref token.
_XREF_RE = re.compile(r":sv:\w+:`([^`]+)`")

#: Signals that a comment really was authored as reStructuredText.  Used only by
#: ``auto`` sniffing: a comment with none of these is prose, and handing it to
#: this parser (which passes the body through as RST) is how a stray ``*`` or
#: trailing ``_`` in a 15-year-old banner comment becomes a build warning.
_RST_SIGNALS = (
    re.compile(r"^\s*:\w+(?:\s+[^:]+)?:\s", re.M),   # :param x: / :returns:
    re.compile(r"``[^`]+``"),                         # ``literal``
    re.compile(r":\w+:`[^`]+`"),                      # :role:`target`
    re.compile(r"^\s*\.\.\s+\w+::", re.M),            # .. directive::
    re.compile(r"::\s*$", re.M),                      # literal block marker
)


class NativeParser(DocstringParser):
    name = "native"

    def parse(self, raw: str) -> ParsedDoc:
        text = (raw or "").strip("\n")
        if not text.strip():
            return ParsedDoc()

        lines = text.splitlines()
        summary_lines: list[str] = []
        body_lines: list[str] = []
        fields: list[DocField] = []

        # Summary = first paragraph (up to a blank line or the first field).
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if not line.strip() or _FIELD_RE.match(line):
                break
            summary_lines.append(line.strip())
            idx += 1

        # Remainder: separate field lines from free-form body.  A field's body
        # continues over the indented lines after it, as in reST.  Only an
        # unindented line can start a field, so a literal block (indented) is
        # body whatever it contains.
        while idx < len(lines):
            line = lines[idx]
            m = None if line[:1].isspace() else _FIELD_RE.match(line)
            if m:
                cont, idx = _continuation(lines, idx + 1)
                fields.append(_make_field(m, cont))
                continue
            body_lines.append(line)
            idx += 1

        summary = " ".join(summary_lines).strip()
        body = "\n".join(body_lines).strip("\n")
        xrefs = _XREF_RE.findall(text)
        return ParsedDoc(summary=summary, body=body, fields=fields, xrefs=xrefs)

    def matches(self, raw: str) -> bool:
        return any(sig.search(raw or "") for sig in _RST_SIGNALS)


def _continuation(lines: list[str], start: int) -> tuple[list[str], int]:
    """The indented lines continuing a field from *start*, dedented to their
    common indent, and the index after them.  Blank lines between indented
    lines are kept; trailing ones are left to the body."""
    end = idx = start
    while idx < len(lines):
        line = lines[idx]
        if line.strip():
            if not line[:1].isspace():
                break
            end = idx + 1
        idx += 1
    block = "\n".join(lines[start:end])
    return textwrap.dedent(block).splitlines(), end


def _make_field(m: "re.Match[str]", cont: list[str] = ()) -> DocField:
    tag, name, body = m.group(1), m.group(2), m.group(3) or ""
    # Normalize the common 'return' -> 'returns' spelling.
    if tag == "return":
        tag = "returns"
    text = "\n".join([body.strip(), *cont]).strip("\n")
    return DocField(kind=tag, name=name.strip() if name else None, body=text)


register_parser(NativeParser())
