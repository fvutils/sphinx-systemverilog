"""Normalized, parser-agnostic object model.

The ``model.builder`` walks pyslang's AST and produces a tree of :class:`SvObject`
nodes.  Everything downstream of the builder (docparse, the domain, autodoc)
consumes :class:`SvObject` and never touches pyslang directly, so the pyslang
API surface is isolated to one module.
"""

from __future__ import annotations

from dataclasses import dataclass, field


#: Canonical object kinds.  Keep in sync with the directives in ``domain.py``.
KIND_PACKAGE = "package"
KIND_MODULE = "module"
KIND_INTERFACE = "interface"
KIND_PROGRAM = "program"
KIND_CLASS = "class"
KIND_FUNCTION = "function"
KIND_TASK = "task"
KIND_PROPERTY = "property"      # class property / variable / data member
KIND_PORT = "port"
KIND_PARAMETER = "parameter"
KIND_TYPEDEF = "typedef"
KIND_MACRO = "macro"
KIND_COVERGROUP = "covergroup"
KIND_COVERPOINT = "coverpoint"
KIND_CONSTRAINT = "constraint"

#: Kinds that may contain members (used by the builder and autodoc recursion).
SCOPE_KINDS = frozenset(
    {
        KIND_PACKAGE, KIND_MODULE, KIND_INTERFACE, KIND_PROGRAM, KIND_CLASS,
        KIND_COVERGROUP,
    }
)


@dataclass(frozen=True)
class SourceRef:
    """A resolved source location: file, 1-based line, 1-based column."""

    file: str
    line: int
    column: int = 0

    @property
    def is_valid(self) -> bool:
        return bool(self.file) and self.line > 0


@dataclass
class SvObject:
    """A documented SystemVerilog declaration.

    Attributes mirror what a renderer needs: identity (``kind``/``name``),
    a rendered ``signature``, the raw doc comment (left untouched for the
    docparse layer), and structural relations (``children``, ``extends``).
    """

    kind: str
    name: str
    qualifiers: list[str] = field(default_factory=list)
    signature: str = ""
    extends: str | None = None
    raw_doc: str | None = None
    doc_style: str | None = None
    location: SourceRef | None = None
    group: str | None = None
    children: list["SvObject"] = field(default_factory=list)
    #: Fully-qualified name within the index (e.g. ``my_pkg::my_class``).
    qualified_name: str | None = None

    @property
    def is_scope(self) -> bool:
        return self.kind in SCOPE_KINDS

    @property
    def is_documented(self) -> bool:
        return bool(self.raw_doc and self.raw_doc.strip())

    def add_child(self, child: "SvObject") -> "SvObject":
        self.children.append(child)
        return child

    def walk(self):
        """Yield this object and all descendants, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SvObject({self.kind} {self.name!r}, children={len(self.children)})"
