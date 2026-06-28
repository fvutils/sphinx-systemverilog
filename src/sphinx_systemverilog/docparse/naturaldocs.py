"""The NaturalDocs doc-comment dialect (the style UVM uses).

NaturalDocs documentation blocks start with a keyword header line such as::

    Function: get_name
    Function -- NODOCS -- get_name
    Group: Seeding

followed by prose.  Inline ``<symbol>`` references and ``~code~`` spans are
converted to reStructuredText.  The ``-- NODOCS --`` marker (used by UVM to keep
a block out of its IEEE extraction) is stripped by default so the prose is still
documented; association/skip policy lives in the model layer.
"""

from __future__ import annotations

import re

from .base import DocstringParser, ParsedDoc, register_parser
from .inline import collect_angle_xrefs, convert_inline

#: ND header keywords -> the canonical object kind they introduce.
HEADER_KEYWORDS = {
    "class": "class",
    "function": "function",
    "task": "task",
    "variable": "property",
    "group": "group",
    "topic": "topic",
    "macro": "macro",
    "typedef": "typedef",
    "module": "module",
    "interface": "interface",
    "package": "package",
    "port": "port",
}

# `Keyword <sep> name`, where <sep> is a colon or a dash-run that may embed the
# UVM `NODOCS` marker (e.g. ``Function -- NODOCS -- new``).  The name runs to the
# end of the line so multi-word Group names (``Group: Report Handling``) work.
_HEADER_RE = re.compile(
    r"""^\s*
        (?P<kw>[A-Za-z]+)\s*
        (?P<sep>:|-+(?:\s*(?P<nodocs>NODOCS)\s*-+)?)\s*
        (?P<name>\S.*?)\s*$
    """,
    re.VERBOSE,
)


class NaturalDocsHeader:
    __slots__ = ("kind", "name", "nodocs")

    def __init__(self, kind: str, name: str, nodocs: bool):
        self.kind = kind
        self.name = name
        self.nodocs = nodocs

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"NDHeader({self.kind} {self.name!r} nodocs={self.nodocs})"


def _is_separator(line: str) -> bool:
    """A blank line or a banner rule (e.g. ``------``, ``======``)."""
    s = line.strip()
    return not s or (len(s) >= 2 and set(s) <= set("-=*+/_~ "))


def _first_content_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if not _is_separator(line):
            return i
    return len(lines)


def parse_header(raw: str) -> NaturalDocsHeader | None:
    """Parse *raw*'s first content line as an ND header, or return ``None``.

    Leading banner/separator lines (UVM wraps headers in ``//-----`` rules) are
    skipped before the header line is matched.
    """
    if not raw:
        return None
    lines = raw.splitlines()
    idx = _first_content_index(lines)
    if idx >= len(lines):
        return None
    m = _HEADER_RE.match(lines[idx])
    if not m:
        return None
    kw = m.group("kw").lower()
    if kw not in HEADER_KEYWORDS:
        return None
    return NaturalDocsHeader(
        kind=HEADER_KEYWORDS[kw],
        name=m.group("name"),
        nodocs=bool(m.group("nodocs")),
    )


class NaturalDocsParser(DocstringParser):
    name = "naturaldocs"

    def parse(self, raw: str) -> ParsedDoc:
        text = (raw or "").strip("\n")
        if not text.strip():
            return ParsedDoc()

        lines = text.splitlines()
        header = parse_header(text)
        if header is not None:
            # Drop everything up to and including the header line; the symbol
            # already carries its name/kind.
            idx = _first_content_index(lines)
            lines = lines[idx + 1:]

        # Drop banner/separator lines and surrounding blanks from the body.
        lines = [ln for ln in lines if not _is_separator(ln) or ln.strip() == ""]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        body_text = convert_inline("\n".join(lines)).strip("\n")
        para = _first_paragraph(body_text)
        summary = " ".join(p.strip() for p in para.splitlines()).strip()
        rest = body_text[len(para):].strip("\n")

        xrefs = collect_angle_xrefs("\n".join(lines))
        return ParsedDoc(summary=summary, body=rest, fields=[], xrefs=xrefs)

    def matches(self, raw: str) -> bool:
        return parse_header(raw) is not None


def _first_paragraph(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            break
        out.append(line)
    return "\n".join(out)


register_parser(NaturalDocsParser())
