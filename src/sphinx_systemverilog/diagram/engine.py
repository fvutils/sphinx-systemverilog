"""Run ELK on an ELK JSON graph, with a layout cache.

Engines, tried in this order:

``mini-racer``
    elkjs in an embedded V8 (the ``mini-racer`` package, a core dependency).
``node``
    elkjs in a ``node`` subprocess, when Node is on the ``PATH``.

:func:`get_engine` returns ``None`` when neither can run, for example when
``elk.bundled.js`` is missing from a source checkout where ``ivpm update``
hasn't been run; :func:`unavailable_reason` then says why and how to fix it.
Callers fall back to Graphviz in that case.

ELK layered is deterministic for a fixed input, except for its internal
``$H`` ids, which :func:`layout` strips from the result.  The cache key is a
hash of the input graph, the elkjs version and :data:`LAYOUT_REV`.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import subprocess
from importlib import resources
from typing import Any, Protocol

#: Bump when the adapter changes what a cached layout means.
LAYOUT_REV = 1

#: Seconds one layout may take before it is abandoned.
TIMEOUT = 120


class LayoutError(RuntimeError):
    """ELK rejected the graph or failed while laying it out."""


class Engine(Protocol):
    name: str

    def layout(self, graph: dict) -> dict: ...


def _js_file(name: str) -> Any:
    return resources.files("sphinx_systemverilog.diagram").joinpath("js", name)


def elk_version() -> str | None:
    """The shipped elkjs version, or ``None`` when elkjs isn't there."""
    f = _js_file("VERSION")
    return f.read_text().strip() if f.is_file() else None


def elk_source() -> str | None:
    f = _js_file("elk.bundled.js")
    return f.read_text(encoding="utf-8") if f.is_file() else None


class MiniRacerElk:
    """elkjs in mini-racer.  One V8 context per process, created on first use."""

    name = "mini-racer"

    # elkjs schedules work with setTimeout, which bare V8 doesn't have; a
    # microtask is enough, since the layout itself is synchronous.
    _PRELUDE = ("var self=this; var window=this;"
                "globalThis.setTimeout=(f,ms)=>{Promise.resolve().then(f);return 0};")

    def __init__(self, source: str):
        from py_mini_racer import MiniRacer

        self._ctx = MiniRacer()
        self._ctx.eval(self._PRELUDE)
        self._ctx.eval(source)
        self._ctx.eval("var __elk = new ELK();")
        # A context still open at interpreter exit upsets shutdown enough that
        # nanobind (pyslang) reports every pyslang object alive then as leaked.
        atexit.register(self.close)

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def layout(self, graph: dict) -> dict:
        try:
            p = self._ctx.eval("__elk.layout(%s).then(r => JSON.stringify(r))"
                               % json.dumps(graph))
            return json.loads(p.get(timeout=TIMEOUT))
        except Exception as e:      # mini-racer raises its own JS* error types
            raise LayoutError(f"elkjs (mini-racer): {e}") from e


class NodeElk:
    """elkjs in a ``node`` subprocess, one process per layout."""

    name = "node"

    _SCRIPT = (
        "const ELK=require(process.argv[1]);let s='';"
        "process.stdin.on('data',d=>s+=d).on('end',()=>new ELK().layout(JSON.parse(s))"
        ".then(r=>process.stdout.write(JSON.stringify(r)),"
        "e=>{process.stderr.write(String(e));process.exit(1)}));"
    )

    def __init__(self, node: str, path: str):
        self._node, self._path = node, path

    def layout(self, graph: dict) -> dict:
        r = subprocess.run([self._node, "-e", self._SCRIPT, self._path],
                           input=json.dumps(graph), capture_output=True, text=True,
                           timeout=TIMEOUT)
        if r.returncode:
            raise LayoutError(f"elkjs (node): {r.stderr.strip()}")
        return json.loads(r.stdout)


_engine: Engine | None = None
_engine_pid: int | None = None
_reason: str = ""


def _make(prefer: str | None) -> tuple[Engine | None, str]:
    src = elk_source()
    if src is None:
        return None, ("elkjs is missing from sphinx_systemverilog/diagram/js/; in a source "
                      "checkout run `ivpm update` (or scripts/fetch_elkjs.py)")
    reasons = []
    for name in ([prefer] if prefer else ["mini-racer", "node"]):
        if name == "mini-racer":
            try:
                return MiniRacerElk(src), ""
            except Exception as e:
                reasons.append(f"mini-racer: {e}")
        elif name == "node":
            node = shutil.which("node")
            if node:
                with resources.as_file(_js_file("elk.bundled.js")) as path:
                    return NodeElk(node, str(path)), ""
            reasons.append("node: not on PATH")
        else:
            reasons.append(f"unknown engine {name!r}")
    return None, "no layout engine could run (" + "; ".join(reasons) + ")"


def get_engine(prefer: str | None = None) -> Engine | None:
    """The layout engine for this process, or ``None`` if none can run.

    *prefer* (``"mini-racer"`` or ``"node"``) restricts the choice to one
    engine.  The engine is created once per process; a forked worker (Sphinx
    parallel builds) gets its own, since a V8 context doesn't survive a fork.
    """
    global _engine, _engine_pid, _reason
    if prefer is not None:
        eng, why = _make(prefer)
        _reason = why
        return eng
    if _engine_pid != os.getpid():
        _engine, _reason = _make(None)
        _engine_pid = os.getpid()
    return _engine


def unavailable_reason() -> str:
    """Why the last :func:`get_engine` call returned ``None``."""
    return _reason


def strip_ids(o: Any) -> Any:
    """*o* without ELK's ``$H`` ids, which differ between runs."""
    if isinstance(o, dict):
        return {k: strip_ids(v) for k, v in o.items() if k != "$H"}
    if isinstance(o, list):
        return [strip_ids(x) for x in o]
    return o


def cache_key(graph: dict) -> str:
    h = hashlib.sha256()
    h.update(f"elkjs {elk_version()} rev {LAYOUT_REV}\n".encode())
    h.update(json.dumps(strip_ids(graph), sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()


def layout(graph: dict, engine: Engine | None = None, cache_dir: str | None = None) -> dict:
    """Lay out *graph* (ELK JSON) and return the positioned graph.

    With *cache_dir*, a layout of an identical graph is read back from there
    instead of being recomputed, and new layouts are stored there.  Raises
    :class:`LayoutError` if the graph can't be laid out, and
    :class:`RuntimeError` if no engine can run.
    """
    path = None
    if cache_dir:
        path = os.path.join(cache_dir, cache_key(graph) + ".json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    engine = engine or get_engine()
    if engine is None:
        raise RuntimeError(unavailable_reason())
    laid = strip_ids(engine.layout(graph))
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(laid, f, separators=(",", ":"))
        os.replace(tmp, path)
    return laid
