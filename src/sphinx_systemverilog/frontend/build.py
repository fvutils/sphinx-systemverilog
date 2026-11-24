"""Run the front end into a database, and keep the one-shot cache (D2-IMPL-3).

:func:`open_index` is what Sphinx calls once per build.  It digests the build
inputs (:func:`~..model.index.index_key`: the files, every option and every
source file's modification time) and either opens ``<cache>/<digest>.svdb``
or builds it: parse, emit the records, compute the :class:`Snapshot`, then
write both files atomically.  A second build of unchanged sources therefore
does not parse.

The **snapshot** holds the design structure and the UVM testbench views that
the records cannot carry yet (D3c and D4 move them into the database).  It is
computed eagerly, while the compilation is alive, so that any process can
render a structural page without it.  It is a pickle and is only ever read
from this cache, which this process family wrote: a database from elsewhere
(``sv_databases``) never brings one.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pickle
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Iterator

from ..model.index import SvIndex, build_index, external_sources_pairs, index_key
from ..model.structure import DEFAULT_MAX_INSTANCES
from ..model.uvm import DEFAULT_MAX_COMPONENTS
from ..svdb.writer import Writer
from . import emit

log = logging.getLogger("sphinx_systemverilog.frontend")

#: Bumped when the records or the snapshot of the same sources change shape,
#: so that an old cache entry is not reused.
CACHE_VERSION = 2


@dataclass(frozen=True)
class Options:
    """The inputs of one front-end run; the keyword arguments of
    :func:`~..model.index.build_index`."""

    source_dirs: tuple[str, ...] = ()
    build_units: tuple[str, ...] = ()
    doc_style: str = "native"
    include_dirs: tuple[str, ...] = ()
    defines: tuple[tuple[str, str], ...] = ()
    base_path: str | None = None
    nodocs_policy: str = "include"
    document_macros: bool = True
    structure_tops: tuple[str, ...] = ()
    structure_max_instances: int = DEFAULT_MAX_INSTANCES
    #: Opt in to gate instances (``of_kind: gate``, section ``structure.gates``);
    #: off by default, since a gate-level netlist can be huge (plan §5.2.1).
    structure_gates: bool = False
    uvm_root: str = ""
    uvm_blackbox: tuple[str, ...] = ()
    uvm_blackbox_bases: tuple[str, ...] | None = None
    uvm_max_components: int = DEFAULT_MAX_COMPONENTS
    #: ``sv_external`` name patterns (plan §6.2 option 1).
    external: tuple[str, ...] = ()
    #: ``sv_external_sources`` as ``(origin, path-or-glob)`` pairs (§6.2 option 2).
    external_sources: tuple[tuple[str, str], ...] = ()
    #: Link databases (linking plan §1.7): what the sources use but do not
    #: define is compiled from these, and not written to this database.
    links: tuple[str, ...] = ()

    @classmethod
    def make(cls, **kw: Any) -> "Options":
        """Options from ``build_index``-style keyword arguments (lists, dicts)."""
        out = {}
        for k, v in kw.items():
            if k == "defines":
                v = tuple(sorted((str(a), "" if b is None else str(b)) for a, b in (v or {}).items()))
            elif k == "external_sources":
                v = external_sources_pairs(v)
            elif k == "uvm_blackbox_bases":
                v = None if v is None else tuple(v)
            elif isinstance(v, (list, tuple)):
                v = tuple(v)
            elif v is None and k in ("source_dirs", "build_units", "include_dirs", "structure_tops",
                                     "uvm_blackbox", "external", "links"):
                v = ()
            out[k] = v
        return cls(**out)

    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments of :func:`~..model.index.build_index`, which
        does not take ``structure_gates``: it only changes what
        :func:`records` emits afterward, not how the sources are parsed or
        the hierarchy walked."""
        kw = asdict(self)
        kw.pop("structure_gates", None)
        kw["defines"] = dict(self.defines)
        for k in ("source_dirs", "build_units", "include_dirs", "structure_tops", "uvm_blackbox", "external",
                  "links"):
            kw[k] = list(kw[k])
        kw["external_sources"] = list(self.external_sources)
        if self.uvm_blackbox_bases is not None:
            kw["uvm_blackbox_bases"] = list(self.uvm_blackbox_bases)
        return kw

    def key(self) -> tuple:
        """What a build of these options depends on (the on-disk cache's
        digest input): :func:`~..model.index.index_key`, plus
        ``structure_gates`` -- excluded from :meth:`kwargs` but still part of
        what the *records* a build produces depend on, and the extension's
        version, so that an upgrade never reads records an older one cached."""
        from ..__version__ import __version__

        return (*index_key(**self.kwargs()), self.structure_gates, __version__)

    def inputs(self) -> dict[str, Any]:
        """``header.inputs``."""
        return {"defines": dict(self.defines), "include_dirs": list(self.include_dirs),
                "tops": list(self.structure_tops), "uvm_root": self.uvm_root}


#: ``conf.py`` setting -> ``build_index`` keyword.
CONF_SETTINGS = {
    "sv_source_dirs": "source_dirs", "sv_build_units": "build_units", "sv_doc_style": "doc_style",
    "sv_include_dirs": "include_dirs", "sv_defines": "defines", "sv_naturaldocs_nodocs": "nodocs_policy",
    "sv_document_macros": "document_macros", "sv_structure_tops": "structure_tops",
    "sv_structure_max_instances": "structure_max_instances", "sv_structure_gates": "structure_gates",
    "sv_uvm_root": "uvm_root",
    "sv_uvm_blackbox": "uvm_blackbox", "sv_uvm_blackbox_bases": "uvm_blackbox_bases",
    "sv_uvm_max_components": "uvm_max_components", "sv_external": "external",
    "sv_external_sources": "external_sources",
}


def conf_kwargs(conf_py: str) -> dict[str, Any]:
    """The front-end settings of a Sphinx ``conf.py`` (``svdb build
    --sphinx-conf``).  The file is executed, from its own directory, as Sphinx
    would; paths in it stay relative to that directory."""
    import runpy

    conf_py = os.path.abspath(conf_py)
    confdir = os.path.dirname(conf_py)
    cwd = os.getcwd()
    os.chdir(confdir)
    try:
        ns = runpy.run_path(conf_py, run_name="conf")
    finally:
        os.chdir(cwd)
    kw: dict[str, Any] = {key: ns[name] for name, key in CONF_SETTINGS.items() if name in ns}
    kw["base_path"] = confdir
    return kw


def digest(key: tuple) -> str:
    """A short file name for a cache key."""
    return hashlib.sha256(repr((CACHE_VERSION, key)).encode()).hexdigest()[:16]


@dataclass
class Snapshot:
    """The structure view of one build, computed eagerly (the UVM views are
    ``uvm.*`` records in the database, D4-IMPL-2).

    ``structure`` is ``None`` when it was not computed or the computation
    failed; a reader then asks the live provider.
    """

    structure: Any = None


def take_snapshot(index: SvIndex) -> Snapshot:
    """Ask the live providers of *index* everything that takes no argument."""
    snap = Snapshot()
    provider = index.structure_provider
    if provider is not None:
        snap.structure = _quietly(provider.get, "design structure")
    return snap


def _quietly(fn, what: str):
    try:
        return fn()
    except Exception as e:  # the directive that asks will report it, as before
        log.debug("sphinx-systemverilog: precomputing the %s failed: %s", what, e)
        return None


def records(index: SvIndex, options: Options) -> Iterable[dict]:
    """The records of a front-end run (D2-IMPL-1), plus ``elab``/``top``
    (D3c-IMPL-2) when a structure walk succeeds -- the same, lazily-computed
    walk a structural directive would otherwise trigger later (§D2-IMPL-2)."""
    from ..model import structure as structure_mod
    from ..model.declarations import extract
    from . import uvm as uvm_mod

    extras = extract(index.builder, gates=options.structure_gates) if index.builder is not None else None
    provider = index.structure_provider
    design = _quietly(provider.get, "design structure") if provider is not None else None
    extra_sections: dict[str, str] | None = {"elaboration": "partial"} if design is not None else None
    if options.structure_gates:
        extra_sections = {**(extra_sections or {}), "structure.gates": "complete"}
    yield from emit.emit(index.roots, doc_style=options.doc_style, diagnostics=index.diagnostics,
                         suppressed=index.suppressed_count, inputs=options.inputs(), extras=extras,
                         extra_sections=extra_sections,
                         origin_of=index.builder.origin_of if index.builder is not None else None,
                         uvm=uvm_mod.views(index.uvm_provider) if index.uvm_provider is not None else None,
                         links=[lk.record() for lk in getattr(index.builder, "linked", None) or ()])
    if design is not None:
        linked = {u for lk in getattr(index.builder, "linked", None) or () for u in lk.units}
        yield from _unlinked_elab(structure_mod.elab_records(design), linked)
        yield from (r for r in structure_mod.top_records(design, configured=bool(options.structure_tops))
                    if r.get("elab", "").split("@", 1)[0] not in linked)


def _unlinked_elab(recs: Iterable[dict], linked: set[str]) -> Iterator[dict]:
    """*recs* without the elaborations of linked definitions: those are
    described by the database they were linked from (linking plan §1.5)."""
    for rec in recs:
        if rec.get("def") in linked:
            continue
        for site in rec.get("sites", ()):
            if site.get("elab", "").split("@", 1)[0] in linked:
                del site["elab"]
        yield rec


def parse(options: Options) -> SvIndex:
    """Run the front end: the live index, with its providers attached.

    Memoized in-process by :func:`~..model.index.build_index`, so a process
    that parsed once (and every process forked from it) parses no more.
    """
    return build_index(**options.kwargs())


def write(index: SvIndex, options: Options, path: str) -> Writer:
    """Write the records of *index* to *path* (``":memory:"`` for none)."""
    w = Writer(path)
    try:
        for rec in records(index, options):
            w.add(rec)
        w.finish()
    except BaseException:
        w.abort()
        raise
    return w


def build(options: Options, path: str, snapshot_path: str | None = None) -> tuple[SvIndex, Snapshot]:
    """Parse, then write the database to *path* and the snapshot beside it.

    The snapshot goes first: a database file that exists always has its
    snapshot, so a reader never mistakes a half-written cache entry for a
    whole one.
    """
    index = parse(options)
    snap = take_snapshot(index)
    if snapshot_path:
        save_snapshot(snap, snapshot_path)
    w = write(index, options, path)
    w.conn.close()
    return index, snap


def save_snapshot(snap: Snapshot, path: str) -> None:
    part = path + ".part"
    try:
        with open(part, "wb") as f:
            pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(part, path)
    except Exception as e:
        # A snapshot that will not pickle costs a re-parse later, not the build.
        log.debug("sphinx-systemverilog: cannot save the snapshot: %s", e)
        try:
            os.remove(part)
        except OSError:
            pass


def load_snapshot(path: str | None) -> Snapshot | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            snap = pickle.load(f)
    except Exception as e:
        log.debug("sphinx-systemverilog: cannot read the snapshot %s: %s", path, e)
        return None
    return snap if isinstance(snap, Snapshot) else None


def cache_paths(cache_dir: str, options: Options) -> tuple[str, str]:
    """``(database, snapshot)`` paths of *options* in *cache_dir*."""
    name = digest(options.key())
    return os.path.join(cache_dir, name + ".svdb"), os.path.join(cache_dir, name + ".snapshot")


def prune(cache_dir: str, keep: str) -> None:
    """Remove every other cache entry: only the current build's is useful."""
    stem = os.path.basename(keep).rsplit(".", 1)[0]
    try:
        names = os.listdir(cache_dir)
    except OSError:
        return
    for n in names:
        if n.split(".", 1)[0] != stem and n.endswith((".svdb", ".snapshot", ".part", ".build")):
            try:
                os.remove(os.path.join(cache_dir, n))
            except OSError:
                pass


def open_index(options: Options, *, cache_dir: str | None, databases: Iterable[str] = (),
               default_doc_style: str | None = None, stitch_databases: Iterable[str] = ()):
    """The :class:`~..model.db.DbIndex` for *options*: the front end's own
    database first, then *databases* in order.  *stitch_databases* are read
    only by the UVM stitcher, after those (linked ``role: external`` ones).

    With *cache_dir*, the front end's database is the cache entry, built
    when absent.  Without it (``sv_db_cache = False``), it is built in memory.
    """
    from ..model.db import DbIndex

    databases = [os.fspath(p) for p in databases]
    if cache_dir is None:
        index, snap = parse(options), None
        snap = take_snapshot(index)
        w = write(index, options, ":memory:")
        return DbIndex.in_memory(w.conn, options, snap, databases, live=index,
                                 default_doc_style=default_doc_style or options.doc_style,
                                 stitch_databases=stitch_databases)

    os.makedirs(cache_dir, exist_ok=True)
    db_path, snap_path = cache_paths(cache_dir, options)
    live = None
    if os.path.isfile(db_path):
        log.debug("sphinx-systemverilog: using the cached database %s", db_path)
    else:
        live, _ = build(options, db_path, snap_path)
        prune(cache_dir, db_path)
    return DbIndex([db_path, *databases], options=options, snapshot_path=snap_path, live=live,
                   default_doc_style=default_doc_style or options.doc_style,
                   stitch_databases=stitch_databases)
