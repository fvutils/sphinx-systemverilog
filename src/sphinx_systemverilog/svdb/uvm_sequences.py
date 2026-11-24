"""``svdb uvm-sequences``: a behavioural task's sequence dependencies, for scripts.

The catalog, nested tree and users views of :mod:`..model.uvm_catalog`, read
from database files alone --- the same values the ``sv:uvm-sequence-catalog``,
``sv:uvm-sequence-tree`` and ``sv:uvm-sequence-users`` directives render --- as
JSON or as plain text.  Meant for CI checks such as "no test depends on a
sequence from this VIP" or "this change touches these tests".
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

#: The views, by the name the command takes.
VIEWS = ("catalog", "tree", "users", "tasks")


def open_provider(paths: list[str], follow_links: bool = False):
    """The UVM provider of the databases *paths* (and, with *follow_links*,
    those they were linked against)."""
    from ..model.db import DbIndex
    from .database import Database

    with Database.open(paths, follow_links=follow_links) as db:
        opened = list(db.paths)
    return DbIndex(opened).uvm_provider


def view(provider, kind: str, name: str = "", method: str = ""):
    """The value of one view; ``None`` when *name* names no such task or
    sequence."""
    if kind == "tasks":
        return [{"name": _bare(t.name), "method": t.method} for t in provider.tasks() if t.overridden]
    if kind == "users":
        return provider.users(name) if provider.sequence(name) is not None else None
    if kind == "tree":
        return provider.tree(name, method)
    return provider.catalog(name, method)


def to_json(value: Any) -> Any:
    """*value* as plain JSON data: dataclasses as objects without their empty
    or default fields, locations as ``{"file", "line"}``."""
    from ..model.objects import SourceRef

    if isinstance(value, SourceRef):
        return {"file": value.file, "line": value.line}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out = {}
        for f in dataclasses.fields(value):
            item = getattr(value, f.name)
            default = f.default if f.default is not dataclasses.MISSING else None
            if item in ((), "", None) or (item == default and f.name not in ("depth", "found")):
                continue
            out[f.name] = to_json(item)
        return out
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    return value


def render_text(kind: str, value: Any) -> str:
    """*value* as indented plain text, one start or sequence per line."""
    lines: list[str] = []
    if kind == "tasks":
        lines += [f"{t['name']}.{t['method']}()" for t in value]
    elif kind == "catalog":
        lines.append(f"{_bare(value.root)}.{value.method}()")
        for e in value.entries:
            flags = [f for f, on in (("recursive", e.recursive), ("no body found", not e.found),
                                     ("possibly overridden", bool(e.possible))) if on]
            origin = f"  [{e.origin}]" if e.origin else ""
            lines.append(f"  {e.depth}  {e.type_name}{origin}" + (f"  ({', '.join(flags)})" if flags else ""))
            for s in e.sites:
                lines.append(f"       started by {s.started_by}.{s.method}(){_where(s)}")
        for o in value.applied:
            lines.append(f"  override applied: {o.original} -> {o.replacement}")
    elif kind == "tree":
        lines.append(f"{_bare(value.root)}.{value.method}()")
        _tree_lines(value.children, 1, lines)
    elif kind == "users":
        lines.append(value.name)
        for u in value.users:
            lines.append(f"  {u.depth}  {_bare(u.root)}.{u.method}()"
                         + ("  (component)" if u.component else ""))
        for s in value.sites:
            lines.append(f"     started by {s.started_by}.{s.method}(){_where(s)}")
        for o in value.replaces:
            lines.append(f"  replaces {o.original} (override in {o.where})")
    return "\n".join(lines) + "\n"


def _tree_lines(nodes, level: int, lines: list[str]) -> None:
    for n in nodes:
        flags = [f for f, on in (("recursive", n.recursive), ("shown above", n.repeated),
                                 ("no body found", not n.found)) if on]
        if n.origin:
            flags.append(f"from {n.origin}")
        context = f"  in {', '.join(n.context)}" if n.context else ""
        on = f"  on {n.sequencer_path}" if n.sequencer_path else ""
        lines.append("  " * level + f"{n.handle}: {n.type_name}" + (f"  ({', '.join(flags)})" if flags else "")
                     + context + on + _where(n))
        _tree_lines(n.children, level + 1, lines)


def _where(site) -> str:
    out = ""
    if site.via:
        out += f"  via {' -> '.join(site.via)}"
    if site.location is not None:
        out += f"  at {os.path.basename(site.location.file)}:{site.location.line}"
    return out


def _bare(name: str) -> str:
    return (name or "").split("::")[-1]
