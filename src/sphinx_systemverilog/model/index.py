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
from .structure import DEFAULT_MAX_INSTANCES, DesignStructure, StructureProvider
from .uvm import DEFAULT_MAX_COMPONENTS, UvmProvider, UvmStructure

#: Attributes that hold a live pyslang ``Compilation`` and therefore must never
#: reach Sphinx's pickle.  Listed once, in one place, because forgetting to add
#: a new provider here breaks *every* build rather than only the pages that use
#: it --- see :meth:`SvIndex.__getstate__`.
_UNPICKLABLE_ATTRS = ("_provider", "_uvm_provider")


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
        #: Lazy access to the elaborated instance hierarchy.  Present only in the
        #: process that built the index -- see :meth:`__getstate__`.
        self._provider: "StructureProvider | None" = None
        #: Lazy access to the extracted UVM testbench hierarchy.  Same lifetime
        #: rules as :attr:`_provider`.
        self._uvm_provider: "UvmProvider | None" = None

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

    # -- design structure (lazy) ----------------------------------------------

    def attach_structure_provider(self, provider: "StructureProvider") -> None:
        """Attach the lazy hierarchy provider.  Does **not** walk anything."""
        self._provider = provider

    @property
    def structure_provider(self) -> "StructureProvider | None":
        return self._provider

    @property
    def structure(self) -> "DesignStructure | None":
        """The elaborated design structure, walking the hierarchy on first use.

        Returns ``None`` when no provider is attached, which is the normal state
        after the index has been unpickled from Sphinx's environment: the live
        ``Compilation`` cannot survive pickling, so structural directives on a
        re-read page degrade with a warning instead of crashing the build.
        """
        if self._provider is None:
            return None
        return self._provider.get()

    @property
    def instance_edges(self) -> dict[str, list[tuple[str, str]]]:
        """Deprecated: ``{parent: [(instance_name, child_type)]}``.

        Retained for the original instance-diagram API.  Touching it triggers
        the hierarchy walk, so prefer :attr:`structure`, whose records carry
        parameters, generate paths and array multiplicity.
        """
        structure = self.structure
        return structure.legacy_edges() if structure is not None else {}

    # -- UVM testbench structure (lazy) ---------------------------------------

    def attach_uvm_provider(self, provider: "UvmProvider") -> None:
        """Attach the lazy testbench provider.  Does **not** extract anything."""
        self._uvm_provider = provider

    @property
    def uvm_provider(self) -> "UvmProvider | None":
        return self._uvm_provider

    @property
    def uvm_structure(self) -> "UvmStructure | None":
        """The testbench hierarchy, extracting it on first use.

        ``None`` after the index has been unpickled, for the same reason
        :attr:`structure` is: the live ``Compilation`` cannot survive pickling,
        so a UVM directive on a re-read page degrades with a warning rather
        than crashing the build.
        """
        if self._uvm_provider is None:
            return None
        return self._uvm_provider.get()

    # -- pickling -------------------------------------------------------------

    def __getstate__(self) -> dict:
        """Drop every live provider before pickling.

        Sphinx pickles arbitrary attributes stored on ``env``, and the index
        lives there.  A pyslang ``Compilation`` is not picklable, so leaving a
        provider in place would break *every* build, structural or not --- not
        merely the pages that use it.
        """
        state = self.__dict__.copy()
        for attr in _UNPICKLABLE_ATTRS:
            state[attr] = None
        return state


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
    structure_tops: Iterable[str] | None = None,
    structure_max_instances: int = DEFAULT_MAX_INSTANCES,
    uvm_root: str = "",
    uvm_blackbox: Iterable[str] | None = None,
    uvm_blackbox_bases: Iterable[str] | None = None,
    uvm_max_components: int = DEFAULT_MAX_COMPONENTS,
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
        tuple(structure_tops or ()), structure_max_instances,
        uvm_root, tuple(uvm_blackbox or ()), tuple(uvm_blackbox_bases or ()),
        uvm_max_components,
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
    if builder.compilation is not None:
        # Attach only.  Nothing here walks the hierarchy; the first structural
        # directive to ask does, once.
        index.attach_structure_provider(
            StructureProvider(
                builder.compilation,
                builder.source_manager,
                tops=structure_tops,
                max_instances=structure_max_instances,
            )
        )
        # Likewise attach-only: extracting the testbench hierarchy means walking
        # every ``build_phase`` in the project, and most builds never ask.
        index.attach_uvm_provider(
            UvmProvider(
                builder.compilation,
                builder.source_manager,
                root=uvm_root,
                blackbox=uvm_blackbox,
                blackbox_bases=uvm_blackbox_bases,
                max_components=uvm_max_components,
            )
        )

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
