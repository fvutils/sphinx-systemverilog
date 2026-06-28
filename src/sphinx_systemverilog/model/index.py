"""Project-wide source index ("parse wide, reference scope").

The index is built once per Sphinx build from ``sv_source_dirs`` / ``sv_build_units``
and shared across every directive, so a large source tree is parsed a single
time.  Directives and cross-reference roles resolve qualified names against it.
"""

from __future__ import annotations

import os
from typing import Iterable

from .builder import ModelBuilder
from .objects import SvObject


class SvIndex:
    """A name-resolved map of every documented SystemVerilog object."""

    def __init__(self) -> None:
        self.roots: list[SvObject] = []
        #: qualified name (``pkg::cls::member``) -> object
        self._by_qname: dict[str, SvObject] = {}
        #: bare name -> list of objects (for unqualified lookup)
        self._by_name: dict[str, list[SvObject]] = {}
        self.diagnostics: list[str] = []
        self.suppressed_count: int = 0

    # -- construction ---------------------------------------------------------

    def add_roots(self, roots: Iterable[SvObject]) -> None:
        for root in roots:
            self.roots.append(root)
            for obj in root.walk():
                qn = obj.qualified_name or obj.name
                self._by_qname.setdefault(qn, obj)
                self._by_name.setdefault(obj.name, []).append(obj)

    # -- lookup ---------------------------------------------------------------

    def get(self, name: str) -> SvObject | None:
        """Resolve *name*, qualified (``a::b``) or bare, to a single object.

        A bare name that is ambiguous returns ``None``; callers should warn.
        """
        if name in self._by_qname:
            return self._by_qname[name]
        # Accept '.' as an alternative separator.
        alt = name.replace(".", "::")
        if alt in self._by_qname:
            return self._by_qname[alt]
        matches = self._by_name.get(name) or self._by_name.get(alt.split("::")[-1])
        if matches and len(matches) == 1:
            return matches[0]
        return None

    def candidates(self, name: str) -> list[SvObject]:
        """All objects matching a bare or qualified *name* (for diagnostics)."""
        if name in self._by_qname:
            return [self._by_qname[name]]
        return list(self._by_name.get(name.split("::")[-1], []))

    def __len__(self) -> int:
        return len(self._by_qname)

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None


def build_index(
    source_dirs: Iterable[str],
    build_units: Iterable[str] | None = None,
    doc_style: str = "native",
    include_dirs: Iterable[str] | None = None,
    defines: dict[str, str] | None = None,
    base_path: str | None = None,
    nodocs_policy: str = "include",
) -> SvIndex:
    """Build an :class:`SvIndex` from the configured sources.

    *build_units* (if given) are parsed as explicit roots; otherwise every
    ``.sv``/``.svh`` file found under *source_dirs* is parsed.  Paths are
    resolved relative to *base_path* (typically the Sphinx ``confdir``).
    """
    builder = ModelBuilder(
        doc_style=doc_style,
        include_dirs=include_dirs,
        defines=defines,
        nodocs_policy=nodocs_policy,
    )
    files = _collect_files(source_dirs, build_units, base_path)
    index = SvIndex()
    if files:
        roots = builder.build_from_files(files)
        index.add_roots(roots)
    index.diagnostics = builder.diagnostics
    index.suppressed_count = builder.suppressed_count
    return index


def _collect_files(
    source_dirs: Iterable[str],
    build_units: Iterable[str] | None,
    base_path: str | None,
) -> list[str]:
    def _abs(p: str) -> str:
        return p if os.path.isabs(p) or not base_path else os.path.join(base_path, p)

    if build_units:
        return [_abs(u) for u in build_units]

    found: list[str] = []
    for d in source_dirs:
        root = _abs(d)
        if os.path.isfile(root):
            found.append(root)
            continue
        for dirpath, _dirs, filenames in os.walk(root):
            for fn in sorted(filenames):
                if fn.endswith((".sv", ".svh")):
                    found.append(os.path.join(dirpath, fn))
    return found
