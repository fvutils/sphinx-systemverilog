"""Doc-comment parser interface and registry.

A :class:`DocstringParser` turns the raw comment text attached to an
:class:`~sphinx_systemverilog.model.objects.SvObject` into a :class:`ParsedDoc`:
a summary line, a reStructuredText body, structured fields (params/returns), and
a set of cross-reference tokens.  Implementations live alongside this module
(``native``, later ``naturaldocs`` and ``doxygen``) and register themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DocField:
    """A structured field such as ``:param addr:`` or ``:returns:``."""

    kind: str          # 'param' | 'returns' | 'note' | 'see' | ...
    name: str | None   # e.g. the parameter name; None for returns/note
    body: str


@dataclass
class ParsedDoc:
    """The normalized result of parsing one doc comment."""

    summary: str = ""
    body: str = ""               # reStructuredText (excluding the summary)
    fields: list[DocField] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.summary or self.body or self.fields)

    def as_rst(self) -> list[str]:
        """Render to a list of RST lines (summary + body + field list)."""
        lines: list[str] = []
        if self.summary:
            lines.append(self.summary)
            lines.append("")
        if self.body:
            lines.extend(self.body.splitlines())
            lines.append("")
        for f in self.fields:
            if f.name:
                lines.append(f":{f.kind} {f.name}: {f.body}")
            else:
                lines.append(f":{f.kind}: {f.body}")
        if lines and lines[-1] != "":
            lines.append("")
        return lines


class DocstringParser(ABC):
    """Base class for doc-comment dialect parsers."""

    #: Registry name, e.g. ``"native"``.
    name: str = ""

    @abstractmethod
    def parse(self, raw: str) -> ParsedDoc:
        """Parse *raw* (already comment-delimiter-stripped) into a ParsedDoc."""

    def matches(self, raw: str) -> bool:
        """Heuristic used by the ``auto`` dialect to sniff this style.

        Default: never auto-selected.  Dialects override with cheap signature
        checks (e.g. presence of ``@brief`` or NaturalDocs headers).
        """
        return False


_REGISTRY: dict[str, DocstringParser] = {}


def register_parser(parser: DocstringParser) -> None:
    _REGISTRY[parser.name] = parser


def get_parser(style: str) -> DocstringParser:
    """Return the parser for *style*, resolving ``"auto"`` by sniffing.

    Falls back to the ``native`` parser for unknown styles.
    """
    if style in _REGISTRY:
        return _REGISTRY[style]
    return _REGISTRY.get("native", _NullParser())


def get_parser_for(style: str, raw: str) -> DocstringParser:
    """Like :func:`get_parser` but resolves ``"auto"`` against *raw* content."""
    if style == "auto":
        for parser in _REGISTRY.values():
            if parser.matches(raw):
                return parser
        return get_parser("native")
    return get_parser(style)


class _NullParser(DocstringParser):
    name = "_null"

    def parse(self, raw: str) -> ParsedDoc:
        text = (raw or "").strip()
        return ParsedDoc(summary=text.splitlines()[0] if text else "")
