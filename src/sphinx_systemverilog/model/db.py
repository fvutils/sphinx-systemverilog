"""``SvIndex`` over svdb databases (plan D2-IMPL-4).

:class:`DbIndex` answers everything :class:`~.index.SvIndex` answers ---
``get``, ``candidates``, ``roots``, ``structure``, ``uvm_structure``,
``uvm_provider`` --- from database files, so the rest of the extension keeps
working on :class:`~.objects.SvObject` trees.  Objects are read on demand and
cached per process; children are read when first asked for.

It pickles to a few paths and options, which is what Sphinx's environment
needs: an unpickled index reopens the files read-only, in whichever process
it lands.  The structure view comes from the cache's snapshot (see
:mod:`~..frontend.build`), the UVM views from the database's ``uvm.*``
records (:func:`~..frontend.uvm.read`); a question neither can answer --- a
UVM tree under a root a directive names --- is put to a live provider, which
means parsing in that process if no parse happened there yet.  Structural
pages therefore render the same whether or not the environment was pickled.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Iterable

from .objects import SvObject

log = logging.getLogger("sphinx_systemverilog.model")

#: When one qname exists in several name spaces, the order ``SvIndex``
#: resolved it in: packages were added first, then definitions, then macros.
_NS_ORDER = {"package": 0, "design": 1, "macro": 2, "unit": 3}

#: Kinds the renderer documents.  The database holds more (plan D3); D6 gives
#: them directives, and until then this facade shows Sphinx exactly what the
#: object model did.
_RENDERED = frozenset({"package", "module", "interface", "program", "class", "constraint", "parameter",
                       "port", "variable", "typedef", "function", "task", "covergroup", "coverpoint",
                       "macro"})


def rendered(o: Any) -> bool:
    """Whether *o* (an ``svdb`` object) is one the renderer knows about: a
    rendered kind, and not one of the declarations only the database has ---
    body declarations of a definition, non-ANSI ports, parameters outside a
    ``#(...)`` list."""
    if o.kind not in _RENDERED:
        return False
    if o.kind == "parameter":
        return bool(o.detail.get("port_list"))
    if o.kind == "port":
        return bool(o.detail.get("ansi"))
    return o.ns != "design" or o.parent is None


class _DbObject(SvObject):
    """An :class:`SvObject` whose children are read on first access."""

    def __init__(self, base: SvObject, index: "DbIndex", key: tuple[int, int]):
        state = dict(base.__dict__)
        state.pop("children", None)
        self.__dict__.update(state)
        self._index = index
        self._key = key
        self._kids: list[SvObject] | None = None

    @property
    def children(self) -> list[SvObject]:  # type: ignore[override]
        if self._kids is None:
            self._kids = self._index._children(self._key)
        return self._kids

    @children.setter
    def children(self, value: list[SvObject]) -> None:
        self._kids = value

    def __reduce__(self):
        # Outside its index (in a pickle) an object is plain data.
        plain = SvObject(**{k: v for k, v in self.__dict__.items() if not k.startswith("_")},
                         children=list(self.children))
        return plain.__reduce__()


class DbIndex:
    """A name-resolved view of every object in one or more databases."""

    def __init__(self, paths: Iterable[str], *, options: Any = None, snapshot_path: str | None = None,
                 live: Any = None, default_doc_style: str | None = None):
        self._paths = [os.fspath(p) for p in paths]
        self._options = options
        self._snapshot_path = snapshot_path
        self._default_doc_style = default_doc_style
        self._memory: bytes | None = None
        self._reset()
        self._live = live
        self._load_meta()

    @classmethod
    def in_memory(cls, conn: sqlite3.Connection, options: Any, snapshot: Any, databases: Iterable[str] = (),
                  *, live: Any = None, default_doc_style: str | None = None) -> "DbIndex":
        """An index whose own database lives in *conn* rather than a file.

        Pickled, it keeps only the options; unpickled in another process, it
        runs the front end again (``sv_db_cache = False`` means no cache).
        """
        self = cls.__new__(cls)
        self._paths = [":memory:", *[os.fspath(p) for p in databases]]
        self._options = options
        self._snapshot_path = None
        self._default_doc_style = default_doc_style
        self._reset()
        self._memory = conn.serialize() if hasattr(conn, "serialize") else None
        self._live = live
        self._snapshot = snapshot
        self._mem_conn = conn
        self._load_meta()
        return self

    def _load_meta(self) -> None:
        """The object count and the front end's diagnostics (file 0's ``diag``
        records): parser errors and identity conflicts, as messages, and the
        number of non-error parser diagnostics suppressed."""
        db = self._database()
        self._len = len(db)
        self.diagnostics: list[str] = []
        self.suppressed_count = 0
        for d in db.diagnostics(0) if self._paths else ():
            if d.get("code") == "Suppressed":
                self.suppressed_count += int(d["message"].split()[0])
            elif d.get("severity") in ("error", "warning"):
                self.diagnostics.append(d["message"])

    # -- per-process state ---------------------------------------------------------

    def _reset(self) -> None:
        self._db = None
        self._pid = None
        self._objs: dict[tuple[int, int], SvObject] = {}
        self._roots: list[SvObject] | None = None
        self._snapshot = None
        self._snapshot_loaded = False
        self._live = None
        self._mem_conn = None
        self._uvm_view = None
        self._uvm_views_ = None
        self._uvm_loaded = False

    def __getstate__(self) -> dict:
        keep = ("_paths", "_options", "_snapshot_path", "_default_doc_style", "_len", "diagnostics",
                "suppressed_count")
        return {k: self.__dict__[k] for k in keep}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._memory = None
        self._reset()

    def _database(self):
        """The open :class:`~..svdb.Database`, reopened after a fork or an unpickle."""
        from ..svdb.database import Database

        if self._db is not None and self._pid == os.getpid():
            return self._db
        # A connection must not cross a fork: open new ones, and leave the
        # parent's alone (closing them here would close nothing of ours).
        others = Database.open(self._paths[1:]) if len(self._paths) > 1 else None
        if self._paths and self._paths[0] == ":memory:":
            conn = self._memory_conn()
            first = Database.from_connection(conn)
            db = Database(first._sources + (others._sources if others else []))
        else:
            db = Database.open(self._paths)
        self._db, self._pid = db, os.getpid()
        self._objs.clear()
        self._roots = None
        return db

    def _memory_conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None and self._pid in (None, os.getpid()):
            return self._mem_conn
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        if self._memory is not None:
            conn.deserialize(self._memory)
            return conn
        # Unpickled with no cache to go back to: run the front end again.
        from ..frontend import build

        conn.close()
        log.info("sphinx-systemverilog: rebuilding the in-memory database in this process")
        live = build.parse(self._options)
        self._live = live
        self._snapshot = build.take_snapshot(live)
        self._snapshot_loaded = True
        conn = build.write(live, self._options, ":memory:").conn
        self._mem_conn = conn
        return conn

    # -- objects -------------------------------------------------------------------

    def _sv(self, o: Any) -> SvObject:
        key = (o.source, o.id)
        obj = self._objs.get(key)
        if obj is None:
            from ..frontend.emit import to_sv_object

            style = (self._database().headers[o.source].get("inputs") or {}).get("doc_style")
            doc = o.doc
            if style is None:
                style = (doc.style if doc is not None else None) or self._default_doc_style
            obj = _DbObject(to_sv_object(o, doc_style=style, doc=doc), self, key)
            self._objs[key] = obj
        return obj

    def _children(self, key: tuple[int, int]) -> list[SvObject]:
        db = self._database()
        parent = db._by_id(*key)
        return [self._sv(o) for o in db.members(parent) if rendered(o)] if parent is not None else []

    @property
    def roots(self) -> list[SvObject]:
        db = self._database()
        if self._roots is None:
            self._roots = [self._sv(o) for o in db.roots() if rendered(o)]
        return self._roots

    def _qname(self, qname: str) -> SvObject | None:
        found = [o for o in self._database().by_qname(qname) if rendered(o)]
        if not found:
            return None
        found.sort(key=lambda o: (o.source, _NS_ORDER.get(o.ns, 9)))
        return self._sv(found[0])

    def get(self, name: str) -> SvObject | None:
        """Resolve *name*, qualified (``a::b``) or bare, to a single object.

        A bare name that is ambiguous returns ``None``; callers should warn.
        """
        obj = self._qname(name)
        if obj is not None:
            return obj
        alt = name.replace(".", "::")
        if alt != name:
            obj = self._qname(alt)
            if obj is not None:
                return obj
        matches = self._by_name(name) or self._by_name(alt.split("::")[-1])
        if len(matches) == 1:
            return self._sv(matches[0])
        return None

    def candidates(self, name: str) -> list[SvObject]:
        """All objects matching a bare or qualified *name* (for diagnostics)."""
        obj = self._qname(name)
        if obj is not None:
            return [obj]
        return [self._sv(o) for o in self._by_name(name.split("::")[-1], None)]

    def _by_name(self, name: str, limit: int | None = 2) -> list:
        """Rendered objects named *name*, at most *limit* of them."""
        out = []
        for o in self._database().by_name(name):
            if rendered(o):
                out.append(o)
                if len(out) == limit:
                    break
        return out

    def __len__(self) -> int:
        return self._len

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None

    @property
    def database(self):
        """The underlying :class:`~..svdb.Database`."""
        return self._database()

    # -- structure and UVM ---------------------------------------------------------

    def _snap(self):
        if not self._snapshot_loaded:
            from ..frontend.build import load_snapshot

            if self._snapshot is None:
                self._snapshot = load_snapshot(self._snapshot_path)
            self._snapshot_loaded = True
        return self._snapshot

    def live(self):
        """The live :class:`~.index.SvIndex`, parsing in this process if need be."""
        if self._live is None:
            if self._options is None:
                return None
            from ..frontend import build

            log.info("sphinx-systemverilog: parsing the sources to answer a structural query")
            self._live = build.parse(self._options)
        return self._live

    @property
    def structure(self):
        """The elaborated design structure."""
        snap = self._snap()
        if snap is not None and snap.structure is not None:
            return snap.structure
        live = self.live()
        return live.structure if live is not None else None

    @property
    def structure_provider(self):
        live = self.live()
        return live.structure_provider if live is not None else None

    @property
    def instance_edges(self) -> dict[str, list[tuple[str, str]]]:
        """Deprecated: ``{parent: [(instance_name, child_type)]}``."""
        structure = self.structure
        return structure.legacy_edges() if structure is not None else {}

    def _uvm_views(self):
        """The UVM views stored in the database (file 0), or ``None`` when it
        holds none (no ``uvm.*`` header section)."""
        if not self._uvm_loaded:
            from ..frontend import uvm

            db = self._database()
            views = uvm.read(db) if self._paths else None
            self._uvm_views_ = views if views is not None and views.sections() else None
            self._uvm_loaded = True
        return self._uvm_views_

    @property
    def uvm_provider(self):
        """A provider answering from the database, then from a live one;
        ``None`` when there is no testbench to ask (no sources)."""
        if self._uvm_view is None:
            if self._uvm_views() is None:
                live = self.live()
                if live is None or live.uvm_provider is None:
                    return None
            self._uvm_view = _UvmView(self)
        return self._uvm_view

    @property
    def uvm_structure(self):
        provider = self.uvm_provider
        return provider.get() if provider is not None else None


class _UvmView:
    """``UvmProvider``'s interface over the ``uvm.*`` records of a database."""

    def __init__(self, index: DbIndex):
        self._index = index

    @property
    def walk_count(self) -> int:
        """Tree walks done in this process, eager ones included."""
        live = self._index._live
        provider = live.uvm_provider if live is not None else None
        return provider.walk_count if provider is not None else 0

    def _views(self):
        return self._index._uvm_views()

    def _live(self):
        live = self._index.live()
        provider = live.uvm_provider if live is not None else None
        if provider is None:
            raise RuntimeError("no UVM provider: the sources cannot be parsed in this process")
        return provider

    def get(self, root: str = ""):
        views = self._views()
        if views is not None and views.structure is not None and root == "":
            return views.structure
        return self._live().get(root)

    def config(self):
        views = self._views()
        return views.config if views is not None and views.config is not None else self._live().config()

    def overrides(self):
        views = self._views()
        return views.overrides if views is not None and views.overrides is not None else self._live().overrides()

    def bridge(self):
        views = self._views()
        return views.bridge if views is not None and views.bridge is not None else self._live().bridge()

    def knows(self, name: str) -> bool:
        if self._views() is None:
            return self._live().knows(name)
        bare = (name or "").split("::")[-1]
        db = self._index._database()
        return any(db.sql("SELECT 1 FROM object WHERE name = ? AND kind = 'class' LIMIT 1", (bare,), source=i)
                   for i in range(len(db.paths)))

    def sequence(self, name: str):
        """A non-library class's sequence from the database (``None`` when it
        is not a sequence); a library class's from the live provider."""
        from .uvm import _LIBRARY_PREFIX

        key = (name or "").strip().split("::")[-1]
        views = self._views()
        if views is not None and "uvm.sequences" in views.sections() and not key.startswith(_LIBRARY_PREFIX):
            return next((q for q in views.sequences if q.name.split("::")[-1] == key), None)
        return self._live().sequence(name)
