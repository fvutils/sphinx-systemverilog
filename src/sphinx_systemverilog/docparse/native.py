"""The 'native' doc-comment dialect.

A low-ceremony, Python-docstring-like style: the first paragraph is the summary,
the remainder is reStructuredText, and reST field lists (``:param x:``,
``:returns:``) are passed through untouched.  This is the recommended style for
new SystemVerilog code because the comment body *is* already RST.
"""

from __future__ import annotations

import re

from .base import DocField, DocstringParser, ParsedDoc, register_parser

#: Matches a reST field line, e.g. ``:param addr: the address``.
_FIELD_RE = re.compile(r"^:(\w+)(?:\s+([^:]+))?:\s*(.*)$")

#: Inline cross-reference written as :sv:...:`name` - captured as an xref token.
_XREF_RE = re.compile(r":sv:\w+:`([^`]+)`")


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
            if not line.strip() or _FIELD_RE.match(line.strip()):
                break
            summary_lines.append(line.strip())
            idx += 1

        # Remainder: separate field lines from free-form body.
        for line in lines[idx:]:
            m = _FIELD_RE.match(line.strip())
            if m:
                fields.append(_make_field(m))
            else:
                body_lines.append(line)

        summary = " ".join(summary_lines).strip()
        body = "\n".join(body_lines).strip("\n")
        xrefs = _XREF_RE.findall(text)
        return ParsedDoc(summary=summary, body=body, fields=fields, xrefs=xrefs)


def _make_field(m: "re.Match[str]") -> DocField:
    tag, name, body = m.group(1), m.group(2), m.group(3)
    # Normalize the common 'return' -> 'returns' spelling.
    if tag == "return":
        tag = "returns"
    return DocField(kind=tag, name=name.strip() if name else None, body=body.strip())


register_parser(NativeParser())
