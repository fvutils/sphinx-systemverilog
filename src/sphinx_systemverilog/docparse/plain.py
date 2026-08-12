"""The fallback dialect: prose that is not written in any markup at all.

``auto`` resolves to this when a comment matches no dialect *and* shows no sign
of being reStructuredText.  Treating such text as RST is what produces the
"Inline strong start-string without end-string" class of warning: a banner like
``*** Do not call directly ***`` is not emphasis, it is a comment someone wrote
in 2011.  Here the text is escaped and structurally repaired instead, so an
arbitrary source comment can never break a page.

Explicitly configuring ``sv_doc_style = "native"`` still gets the native parser,
which passes RST through untouched.
"""

from __future__ import annotations

from .base import DocstringParser, ParsedDoc, register_parser
from .inline import escape_rst_inline
from .sanitize import sanitize_prose


class PlainParser(DocstringParser):
    name = "plain"

    def parse(self, raw: str) -> ParsedDoc:
        text = sanitize_prose((raw or "").strip("\n")).strip("\n")
        if not text.strip():
            return ParsedDoc()

        lines = [escape_rst_inline(line) for line in text.splitlines()]
        summary_lines: list[str] = []
        idx = 0
        while idx < len(lines) and lines[idx].strip():
            summary_lines.append(lines[idx].strip())
            idx += 1
        body = "\n".join(lines[idx:]).strip("\n")
        return ParsedDoc(summary=" ".join(summary_lines).strip(), body=body)

    def matches(self, raw: str) -> bool:
        # Never sniffed: this is the fallback get_parser_for falls back *to*.
        return False


register_parser(PlainParser())
