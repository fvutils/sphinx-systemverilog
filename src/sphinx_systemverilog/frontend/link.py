"""Link a compile against other databases (docs/design/svdb-linking-plan.md §1.3).

A name the sources use but do not define, and that a link database does, is
satisfied by declaration-only text generated from that database
(:mod:`..svdb.declgen`), parsed into the compilation's own ``SourceManager``
under a ``svdb-link:`` buffer name.  `` `include `` files the include path
cannot find, but a link database recorded `` `define ``s from, are assigned
generated text before the sources are parsed.

The loop is driven by slang's own diagnostics: compile, collect the unknown
packages and definitions, add what the databases have, compile again.  The
last compilation is kept for the builder, so linking costs one extra
elaboration only when a round actually adds something.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import pyslang

from ..svdb import declgen
from ..svdb.database import Database, file_hash

#: Rounds of compile-and-link before giving up (each round links at least one unit).
MAX_ROUNDS = 8

#: Diagnostics whose first argument names a package or definition (L0).
UNKNOWN_CODES = {"UnknownPackage", "UnknownClassOrPackage", "UnknownModule", "UnknownInterface"}

_INCLUDE = re.compile(r'^\s*`include\s+"([^"]+)"', re.M)


@dataclass
class Link:
    """One link database and what a compile took from it (header ``links``)."""

    path: str
    origin: str
    hash: str | None = None
    units: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)

    def record(self) -> dict[str, Any]:
        rec: dict[str, Any] = {"origin": self.origin, "path": self.path}
        if self.hash:
            rec["hash"] = self.hash
        rec["units"] = list(self.units)
        if self.includes:
            rec["includes"] = list(self.includes)
        return rec


def database_hash(path: str) -> str | None:
    """The SHA-256 of a database file's bytes (``links[].hash``)."""
    return file_hash(path)


class Linker:
    """Links one compile against *paths* (searched in order; the first
    database that defines a name wins, as for :meth:`Database.open`)."""

    def __init__(self, paths: Iterable[str], include_dirs: Iterable[str] = ()):
        self.paths = [os.path.abspath(p) for p in paths]
        self.include_dirs = [os.path.abspath(d) for d in include_dirs]
        self.db = Database.open(self.paths)
        self.links = [Link(p, declgen.origin_of(self.db, i), database_hash(p)) for i, p in enumerate(self.paths)]
        #: A database that does not describe its declarations completely (a
        #: vendor's ``objects: partial``) cannot satisfy a compile: linking
        #: against it would report ports and members it merely left out.
        self._complete = [((h or {}).get("sections") or {}).get("objects") == "complete" for h in self.db.headers]
        #: Messages for names no source or link database defines, and for
        #: problems inside generated text; surfaced as warnings.
        self.errors: list[str] = []
        self._linked: set[str] = set()
        self._trees: list[Any] = []
        self._assigned: set[str] = set()
        self._defined: set[str] = set()

    def close(self) -> None:
        self.db.close()

    # -- includes ------------------------------------------------------------------

    def preinclude(self, sm: Any, files: Iterable[str]) -> None:
        """Assign generated text to each `` `include ``d file the include path
        cannot find but a link database recorded macros from.  Must run before
        the sources are parsed.  Only the files named in *files* and in the
        include files they reach are scanned."""
        by_name: dict[str, tuple[int, str]] = {}
        for src in range(len(self.paths)):
            for path in declgen.include_files(self.db, src):
                by_name.setdefault(os.path.basename(path), (src, path))
        if not by_name:
            return
        todo, seen = [os.path.abspath(f) for f in files], set()
        while todo:
            f = todo.pop()
            if f in seen:
                continue
            seen.add(f)
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for name in _INCLUDE.findall(text):
                found = self._find_include(name, os.path.dirname(f))
                if found is not None:
                    todo.append(found)
                    continue
                hit = by_name.get(os.path.basename(name))
                # slang looks next to the including file first: the text is
                # assigned there, so that is where it finds it.
                where = os.path.join(os.path.dirname(f), name)
                if hit is None or where in self._assigned:
                    continue
                src, path = hit
                sm.assignText(where, declgen.include_text(self.db, path, src))
                self._assigned.add(where)
                if name not in self.links[src].includes:
                    self.links[src].includes.append(name)

    def _find_include(self, name: str, here: str) -> str | None:
        for d in [here, *self.include_dirs]:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        return None

    # -- the loop --------------------------------------------------------------------

    def link(self, sm: Any, trees: list[Any]) -> Any:
        """Add linked syntax trees until no unknown name is one a link
        database has.  Returns the last ``Compilation`` (over *trees* plus
        the linked trees, :attr:`trees`)."""
        self._defined = _defined_names(trees)
        for _round in range(MAX_ROUNDS):
            comp = pyslang.ast.Compilation()
            for t in [*trees, *self._trees]:
                comp.addSyntaxTree(t)
            unknown = self._unknown_names(comp)
            names = [n for n in unknown if n not in self._linked and self._linkable(n)]
            if not names:
                self._report(comp, unknown)
                return comp
            self._add(sm, names)
        self.errors.append(f"link: gave up after {MAX_ROUNDS} rounds; names still unknown: "
                           + ", ".join(sorted(self._unknown_names(comp))))
        return comp

    def _linkable(self, name: str) -> bool:
        u = declgen.unit(self.db, name)
        return u is not None and self._complete[u.source]

    @property
    def trees(self) -> list[Any]:
        """The syntax trees generated so far."""
        return list(self._trees)

    def _add(self, sm: Any, names: list[str]) -> None:
        cl = declgen.closure(self.db, names)
        for u in cl.units:
            if u.qname in self._linked or u.qname in self._defined or not self._complete[u.source]:
                continue        # a name the sources define always wins
            self._linked.add(u.qname)
            name = declgen.buffer_name(self.links[u.source].origin, u.qname)
            text = declgen.unit_text(self.db, u)
            self._trees.append(pyslang.syntax.SyntaxTree.fromText(text, sm, name))
            self.links[u.source].units.append(u.qname)
        for n in sorted(cl.unit_scope):
            self.errors.append(f"link: '{n}' is declared in $unit of a link database; "
                               "$unit declarations cannot be linked")

    def _unknown_names(self, comp: Any) -> list[str]:
        out: list[str] = []
        for d in comp.getAllDiagnostics():
            if _code(d) not in UNKNOWN_CODES:
                continue
            try:
                name = str(d.args[0])
            except Exception:  # noqa: BLE001
                continue
            if name and name not in out:
                out.append(name)
        return out

    def _report(self, comp: Any, unknown: list[str]) -> None:
        """Problems inside generated text are link errors, not the sources' own."""
        engine = pyslang.DiagnosticEngine(comp.sourceManager)
        for d in comp.getAllDiagnostics():
            try:
                buffer = comp.sourceManager.getFileName(d.location)
            except Exception:  # noqa: BLE001
                continue
            if not declgen.is_link_buffer(buffer):
                continue
            try:
                if str(engine.getSeverity(d.code, d.location)) not in ("DiagnosticSeverity.Error",
                                                                          "DiagnosticSeverity.Fatal"):
                    continue
                text = engine.reportAll(comp.sourceManager, [d]).strip()
            except Exception:  # noqa: BLE001
                text = str(d.code)
            self.errors.append(f"link: in text generated from {self._db_of(buffer)}: {text}")

    def _db_of(self, buffer: str) -> str:
        origin = buffer[len(declgen.LINK_SCHEME):].split("/", 1)[0]
        return next((lk.path for lk in self.links if lk.origin == origin), origin)

    def used(self) -> list[Link]:
        """The link databases something was taken from, for the header."""
        return [lk for lk in self.links if lk.units or lk.includes]


_DECLARATIONS = {"PackageDeclaration", "ModuleDeclaration", "InterfaceDeclaration", "ProgramDeclaration"}


def _defined_names(trees: Iterable[Any]) -> set[str]:
    """Packages and definitions the sources declare (`` `include``s expanded)."""
    out: set[str] = set()
    for t in trees:
        for m in getattr(t.root, "members", None) or ():
            if str(m.kind).rsplit(".", 1)[-1] in _DECLARATIONS:
                name = getattr(getattr(getattr(m, "header", None), "name", None), "valueText", "")
                if name:
                    out.add(name)
    return out


def _code(d: Any) -> str:
    return str(d.code).removeprefix("DiagCode(").rstrip(")")


def is_linked(sm: Any, location: Any) -> bool:
    """Whether *location* lies in generated (linked) text."""
    try:
        return declgen.is_link_buffer(sm.getFileName(location))
    except Exception:  # noqa: BLE001
        return False
