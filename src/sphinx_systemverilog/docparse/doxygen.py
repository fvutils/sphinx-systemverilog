"""The Doxygen doc-comment dialect.

Handles the common Doxygen command set written with either ``@`` or ``\\``
prefixes (``@brief``, ``@param``, ``@return``, ``@note`` ...), plus inline
markup (``@p``/``@c`` code, ``@a`` emphasis, ``#ref`` / ``@ref`` cross-refs).
Comment delimiters (``/**``, ``///``, ``//!``, leading ``*``) are already
stripped by the model layer before the text reaches this parser.
"""

from __future__ import annotations

import re

from .base import DocField, DocstringParser, ParsedDoc, register_parser
from .inline import escape_rst_inline

# A command line: ``@cmd`` or ``\cmd`` followed by its argument(s).
_CMD_RE = re.compile(r"^[@\\](\w+)\b[ \t]*(.*)$")

# Inline conversions applied to prose (after RST-escaping).
_INLINE_CODE = re.compile(r"[@\\][pc]\s+(\S+)")        # @p x / @c x -> ``x``
_INLINE_EM = re.compile(r"[@\\]a\s+(\S+)")             # @a x -> *x*
_INLINE_REF = re.compile(r"[@\\]ref\s+(\w+)")          # @ref sym -> xref
_HASH_REF = re.compile(r"(?<![\w`])#(\w+)")             # #sym -> xref

#: Commands that introduce paragraph-level fields.
_FIELD_COMMANDS = {
    "param": "param",
    "tparam": "param",
    "return": "returns",
    "returns": "returns",
    "retval": "retval",
    "note": "note",
    "warning": "warning",
    "see": "see",
    "sa": "see",
    "pre": "pre",
    "post": "post",
    "throws": "throws",
    "exception": "throws",
}

#: Commands whose text contributes to the summary/body, not a field.
_PROSE_COMMANDS = {"brief", "short", "details", "summary"}


class DoxygenParser(DocstringParser):
    name = "doxygen"

    def parse(self, raw: str) -> ParsedDoc:
        text = (raw or "").strip("\n")
        if not text.strip():
            return ParsedDoc()

        brief: list[str] = []
        body: list[str] = []
        fields: list[DocField] = []
        xrefs: list[str] = []

        target = body          # where free text currently accumulates
        saw_brief = False
        current_field: DocField | None = None

        for line in text.splitlines():
            if not line.strip():
                # A blank line ends the @brief paragraph and any open field.
                current_field = None
                if target is brief:
                    target = body
                else:
                    target.append("")
                continue
            m = _CMD_RE.match(line.strip())
            if m:
                cmd, rest = m.group(1).lower(), m.group(2)
                current_field = None
                if cmd in _PROSE_COMMANDS:
                    if cmd in ("brief", "short"):
                        saw_brief = True
                        target = brief
                    else:
                        target = body
                    if rest:
                        target.append(_inline(rest, xrefs))
                    continue
                if cmd in _FIELD_COMMANDS:
                    current_field = _make_field(cmd, rest, xrefs)
                    fields.append(current_field)
                    continue
                # Unknown command: keep its argument as plain text.
                target.append(_inline(rest, xrefs))
                continue

            # Continuation / plain text line.
            if current_field is not None:
                extra = _inline(line.strip(), xrefs)
                current_field.body = (current_field.body + " " + extra).strip()
            else:
                target.append(_inline(line, xrefs))

        # Without an explicit @brief, the first paragraph of body is the summary.
        if not saw_brief:
            brief, body = _split_first_paragraph(body)

        summary = " ".join(s.strip() for s in brief if s.strip()).strip()
        body_text = "\n".join(body).strip("\n")
        return ParsedDoc(summary=summary, body=body_text, fields=fields, xrefs=xrefs)

    def matches(self, raw: str) -> bool:
        # Auto-detect: any Doxygen command present.
        return bool(re.search(r"(^|\s)[@\\](brief|param|return|returns|details|"
                              r"note|see|retval)\b", raw or ""))


def _make_field(cmd: str, rest: str, xrefs: list[str]) -> DocField:
    kind = _FIELD_COMMANDS[cmd]
    name = None
    if kind in ("param", "retval", "throws"):
        # Strip optional [in]/[out]/[in,out] direction, then take the name.
        rest = re.sub(r"^\[[^\]]*\]\s*", "", rest)
        parts = rest.split(None, 1)
        if parts:
            name = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
    if kind == "see":
        for ref in re.split(r"[,\s]+", rest.strip()):
            if ref:
                xrefs.append(ref)
    return DocField(kind=kind, name=name, body=_inline(rest, xrefs).strip())


def _inline(text: str, xrefs: list[str]) -> str:
    text = escape_rst_inline(text)

    def code(m: "re.Match[str]") -> str:
        return f"``{m.group(1)}``"

    def em(m: "re.Match[str]") -> str:
        return f"*{m.group(1)}*"

    def ref(m: "re.Match[str]") -> str:
        xrefs.append(m.group(1))
        return f":sv:obj:`{m.group(1)}`"

    text = _INLINE_CODE.sub(code, text)
    text = _INLINE_EM.sub(em, text)
    text = _INLINE_REF.sub(ref, text)
    text = _HASH_REF.sub(ref, text)
    return text


def _split_first_paragraph(lines: list[str]) -> tuple[list[str], list[str]]:
    summary: list[str] = []
    idx = 0
    while idx < len(lines) and lines[idx].strip():
        summary.append(lines[idx])
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return summary, lines[idx:]


register_parser(DoxygenParser())
