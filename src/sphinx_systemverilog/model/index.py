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
        #: module type -> [(instance_name, child_type)] structural edges.
        self.instance_edges: dict[str, list[tuple[str, str]]] = {}

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


#: In-process cache: signature -> SvIndex.  Avoids re-parsing across repeated
#: builds in one process (sphinx-autobuild, test sessions) when nothing changed.
_INDEX_CACHE: dict[tuple, SvIndex] = {}


def clear_index_cache() -> None:
    _INDEX_CACHE.clear()


def build_index(
    source_dirs: Iterable[str],
    build_units: Iterable[str] | None = None,
    doc_style: str = "native",
    include_dirs: Iterable[str] | None = None,
    defines: dict[str, str] | None = None,
    base_path: str | None = None,
    nodocs_policy: str = "include",
    document_macros: bool = True,
    use_cache: bool = True,
) -> SvIndex:
    """Build an :class:`SvIndex` from the configured sources.

    *build_units* (if given) are parsed as explicit roots; otherwise every
    ``.sv``/``.svh`` file found under *source_dirs* is parsed.  Paths are
    resolved relative to *base_path* (typically the Sphinx ``confdir``).

    Results are cached in-process keyed by the inputs and the mtimes of all
    candidate source files, so an unchanged tree is parsed only once.
    """
    source_dirs = list(source_dirs)
    build_units = list(build_units or [])
    include_dirs = list(include_dirs or [])

    files = _collect_files(source_dirs, build_units, base_path)
    # Hash the inputs + source mtimes (include dirs catch `include changes when
    # build units are used).
    scan_dirs = source_dirs if not build_units else include_dirs or source_dirs
    mtimes = _mtime_signature(files, scan_dirs, base_path)
    key = (
        tuple(sorted(files)), doc_style, tuple(sorted(include_dirs)),
        tuple(sorted((defines or {}).items())), nodocs_policy, document_macros,
        mtimes,
    )
    if use_cache and key in _INDEX_CACHE:
        return _INDEX_CACHE[key]

    builder = ModelBuilder(
        doc_style=doc_style,
        include_dirs=include_dirs,
        defines=defines,
        nodocs_policy=nodocs_policy,
        document_macros=document_macros,
    )
    index = SvIndex()
    if files:
        roots = builder.build_from_files(files)
        index.add_roots(roots)
    index.diagnostics = builder.diagnostics
    index.suppressed_count = builder.suppressed_count
    index.instance_edges = builder.instance_edges

    if use_cache:
        _INDEX_CACHE[key] = index
    return index


def _mtime_signature(
    files: list[str], scan_dirs: Iterable[str], base_path: str | None
) -> tuple:
    """A signature of file modification times for cache invalidation."""
    paths = set(files)
    for d in scan_dirs:
        root = d if os.path.isabs(d) or not base_path else os.path.join(base_path, d)
        if os.path.isfile(root):
            paths.add(root)
        else:
            for dirpath, _dirs, names in os.walk(root):
                for n in names:
                    if n.endswith((".sv", ".svh")):
                        paths.add(os.path.join(dirpath, n))
    sig = []
    for p in sorted(paths):
        try:
            sig.append((p, os.stat(p).st_mtime_ns))
        except OSError:
            sig.append((p, 0))
    return tuple(sig)


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
