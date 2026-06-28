"""NaturalDocs detached-block index.

NaturalDocs documentation blocks are frequently *not* adjacent to the
declaration they document - UVM separates them with ``@uvm-ieee`` annotation
comments and blank lines.  This module scans the whole token stream of a syntax
tree, collects every comment block that begins with an ND header, and indexes
them by name so the builder can associate them with symbols.

Name collisions across scopes (e.g. ``get_name`` in many classes) are resolved
by source-line proximity: a symbol picks the same-named block nearest to - and
at or above - its own declaration line.
"""

from __future__ import annotations

from typing import Any

from .comments import clean_comment_block, iter_comment_blocks
from .locations import is_real_location

try:  # pyslang Token type, for traversal
    from pyslang.parsing import Token
except Exception:  # pragma: no cover - import guard
    Token = ()  # type: ignore[assignment]


class NDBlock:
    __slots__ = ("kind", "name", "nodocs", "raw", "line", "file")

    def __init__(
        self, kind: str, name: str, nodocs: bool, raw: str, line: int, file: str
    ):
        self.kind = kind
        self.name = name
        self.nodocs = nodocs
        self.raw = raw
        self.line = line
        self.file = file


class NDBlockIndex:
    """All ND blocks found in one or more syntax trees.

    Line numbers are per-file, so name lookups and group resolution are scoped to
    a single file to avoid cross-file confusion (many UVM classes share method
    names like ``get_name``).
    """

    def __init__(self) -> None:
        self._by_name: dict[str, list[NDBlock]] = {}
        #: (file, line, group-name) markers for member grouping.
        self.groups: list[tuple[str, int, str]] = []

    def add(self, block: NDBlock) -> None:
        if block.kind == "group":
            self.groups.append((block.file, block.line, block.name))
        else:
            self._by_name.setdefault(block.name, []).append(block)

    @property
    def is_empty(self) -> bool:
        return not self._by_name and not self.groups

    def lookup(
        self, name: str, line: int | None, file: str | None = None
    ) -> NDBlock | None:
        """Best ND block for *name*, in *file*, nearest to *line*."""
        candidates = self._by_name.get(name)
        if not candidates:
            return None
        if file is not None:
            same = [b for b in candidates if b.file == file]
            if same:
                candidates = same
        if line is None or len(candidates) == 1:
            return candidates[0]

        def distance(block: NDBlock) -> tuple[int, int]:
            if block.line <= line:
                return (0, line - block.line)
            return (1, block.line - line)

        return min(candidates, key=distance)

    def group_for(self, line: int | None, file: str | None = None) -> str | None:
        if line is None or not self.groups:
            return None
        chosen = None
        for gfile, gline, gname in sorted(self.groups, key=lambda g: (g[0], g[1])):
            if file is not None and gfile != file:
                continue
            if gline <= line:
                chosen = gname
            elif chosen is not None:
                break
        return chosen


def build_nd_index(
    tree: Any, source_manager: Any, index: NDBlockIndex | None = None
) -> NDBlockIndex:
    """Scan *tree* for NaturalDocs blocks, adding them to *index* (or a new one)."""
    from ..docparse.naturaldocs import parse_header

    if index is None:
        index = NDBlockIndex()
    root = getattr(tree, "root", None)
    if root is None:
        return index

    for token in _iter_tokens(root):
        line = 0
        file = ""
        loc = getattr(token, "location", None)
        if is_real_location(source_manager, loc):
            line = source_manager.getLineNumber(loc)
            file = str(source_manager.getFileName(loc))
        for block_lines in iter_comment_blocks(token):
            raw = clean_comment_block(block_lines)
            if not raw:
                continue
            header = parse_header(raw)
            if header is None:
                continue
            index.add(
                NDBlock(header.kind, header.name, header.nodocs, raw, line, file)
            )
    return index


def _iter_tokens(node: Any):
    """Yield every pyslang Token under *node*, in source order."""
    try:
        children = list(node)
    except TypeError:
        return
    for child in children:
        if child is None:
            continue
        if Token and isinstance(child, Token):
            yield child
        elif hasattr(child, "kind"):
            yield from _iter_tokens(child)
