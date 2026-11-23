"""Replaying a component's methods: the ``run`` rule (stitching plan §3.3).

A class's records hold only what the class itself writes: the creates,
connections and overrides in each of its functions, numbered by ``step``, and
a method table listing the helper calls each function makes (``uvm.type``
``methods``).  This module turns that back into what a method *does* when it
runs on a component whose actual type is known: its own items in step order,
with every followable call replaced by what the called function does.

* A call is bound the way SystemVerilog binds it.  ``super.m()`` is looked up
  from the base of the class it is written in.  An unqualified or ``this.``
  call is looked up from that same class and, when the function found there
  is virtual, looked up again from the actual type.
* An inherited method is found by the same lookup, so a class that writes no
  ``build_phase`` runs its base's.
* A call under an ``if`` makes everything it does conditional, and one in a
  loop multiplies it.
* A constructor with no ``super.new`` call still runs its base's constructor
  first, as SystemVerilog inserts the call.
* Recursion is cut at :data:`MAX_INLINE` levels and at the first repeated
  ``(class, method)``, each reported as an issue.

Pure Python over duck-typed records: the Sphinx model runs it over live
classes and the stitcher over a database's records.  No pyslang, no Sphinx.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

#: How deep calls are followed before giving up (each level is a helper call).
MAX_INLINE = 8

#: The constructor's name as a method.
CONSTRUCTOR = "new"

#: Issue kinds.
ISSUE_CYCLE = "inline_cycle"
ISSUE_DEPTH = "inline_depth"


class ClassModel(Protocol):
    """What :func:`run` reads about classes, by key."""

    def type(self, key: str) -> Any | None:
        """The class's :class:`~sphinx_systemverilog.model.uvm.UvmType`
        (anything with ``method(name)``), or ``None`` when it is not known ---
        a library class, or one outside every database."""

    def base(self, key: str) -> str | None:
        """The key of the class's immediate base, or ``None``."""

    def items(self, key: str, method: str) -> Sequence[Any]:
        """What the class itself writes in *method*: each with ``step``,
        ``conditional`` and, optionally, ``multiplicity``."""


@dataclass(frozen=True)
class RunItem:
    """One item a method run reaches, in the order it runs."""

    item: Any
    #: Key of the class whose source wrote it.
    owner: str
    #: The item's own ``conditional``, or any call on the way to it.
    conditional: bool = False
    #: ``"N"`` when the item, or any call on the way to it, is in a loop.
    multiplicity: str = "1"
    #: The calls followed to reach it: ``(class key, method, step)`` for each,
    #: outermost first.  Empty for an item the method writes itself.
    via: tuple[tuple[str, str, int], ...] = ()


@dataclass(frozen=True)
class RunIssue:
    """A call :func:`run` did not follow."""

    kind: str
    #: Class key and method of the call not followed.
    owner: str
    method: str
    via: tuple[tuple[str, str, int], ...] = ()


@dataclass
class RunResult:
    items: list[RunItem]
    issues: list[RunIssue]


def find(model: ClassModel, start: str | None, method: str) -> tuple[str | None, Any]:
    """``(key, method)`` of the first class from *start* up that defines *method*.

    ``(None, None)`` when none does, or when the search reaches a class the
    model does not know (the library defines nothing the stitcher follows).
    """
    seen: set[str] = set()
    key = start
    while key and key not in seen:
        seen.add(key)
        t = model.type(key)
        if t is None:
            return None, None
        found = t.method(method)
        if found is not None:
            return key, found
        key = model.base(key)
    return None, None


def run(model: ClassModel, actual: str, method: str, *, max_inline: int = MAX_INLINE) -> RunResult:
    """Everything *method* does on a component of type *actual*, in order."""
    out = RunResult([], [])
    key, found = find(model, actual, method)
    if key is not None:
        _replay(model, actual, key, found, False, "1", (), {(key, method)}, max_inline, out)
    return out


def _replay(model: ClassModel, actual: str, key: str, method: Any, conditional: bool,
            multiplicity: str, via: tuple, active: set, max_inline: int, out: RunResult) -> None:
    name = method.name
    events: list[tuple[float, int, int, Any]] = []
    for i, item in enumerate(model.items(key, name)):
        step = getattr(item, "step", None)
        events.append((float("inf") if step is None else step, 1, i, item))
    calls = list(getattr(method, "calls", ()))
    if name == CONSTRUCTOR and not any(c.super and c.method == CONSTRUCTOR for c in calls):
        events.append((-1, 0, 0, _ImplicitSuperNew()))
    for i, call in enumerate(calls):
        events.append((call.step, 0, i, call))
    events.sort(key=lambda e: e[:3])

    for step, is_item, _i, event in events:
        if is_item:
            out.items.append(RunItem(
                item=event, owner=key,
                conditional=conditional or bool(getattr(event, "conditional", False)),
                multiplicity=_times(multiplicity, getattr(event, "multiplicity", "1")),
                via=via))
            continue
        target_key, target = _bind(model, actual, key, event)
        if target_key is None:
            continue
        here = via + ((key, name, int(step)),)
        if (target_key, event.method) in active:
            out.issues.append(RunIssue(ISSUE_CYCLE, target_key, event.method, here))
            continue
        if len(here) > max_inline:
            out.issues.append(RunIssue(ISSUE_DEPTH, target_key, event.method, here))
            continue
        active.add((target_key, event.method))
        _replay(model, actual, target_key, target,
                conditional or event.conditional, _times(multiplicity, event.multiplicity),
                here, active, max_inline, out)
        active.discard((target_key, event.method))


def _bind(model: ClassModel, actual: str, key: str, call: Any) -> tuple[str | None, Any]:
    """The function *call*, written in class *key*, runs."""
    if call.super:
        return find(model, model.base(key), call.method)
    found_key, found = find(model, key, call.method)
    if found is not None and found.virtual and found_key != actual:
        return find(model, actual, call.method)
    return found_key, found


def _times(outer: str, inner: str) -> str:
    return "1" if outer == "1" and inner in ("1", "", None) else "N"


@dataclass(frozen=True)
class _ImplicitSuperNew:
    """The ``super.new()`` SystemVerilog inserts into a constructor without one."""

    method: str = CONSTRUCTOR
    super: bool = True
    conditional: bool = False
    multiplicity: str = "1"


# -- the declared-type walk --------------------------------------------------------
#
# The Sphinx views' tree: from a root, each component's children are what its
# constructor and build_phase reach, by *declared* type (factory overrides stay
# annotations there).  One implementation for the live classes and for records
# read back from a database, so a page renders the same tree either way.

BUILD_PHASE = "build_phase"
CONNECT_PHASE = "connect_phase"


class WalkModel(ClassModel, Protocol):
    """A :class:`ClassModel` that also makes the walk's output objects."""

    def describe(self, key: str, display: str) -> Any:
        """The ``UvmType`` to report for *key*, named *display*."""

    def child(self, reached: RunItem) -> tuple[Any, str | None]:
        """``(UvmChild, key to descend into or None)`` for a reached create."""

    def connection(self, reached: RunItem, display: str) -> Any | None:
        """The ``UvmConnection`` to report for a reached item, or ``None``
        when the item is not a connection."""

    def is_child(self, item: Any) -> bool:
        """True for a create (rather than a connection or an override)."""


def effective_children(model: WalkModel, key: str) -> list[RunItem]:
    """The creates a component of type *key* reaches: constructor, then build."""
    out = []
    for method in (CONSTRUCTOR, BUILD_PHASE):
        out.extend(r for r in run(model, key, method).items if model.is_child(r.item))
    return out


@dataclass
class Walk:
    """What :func:`walk` found, keyed by display type name like ``UvmStructure``."""

    types: dict[str, Any]
    children: dict[str, list[Any]]
    connections: dict[str, list[Any]]
    visited: int = 0
    truncated: bool = False


def walk(model: WalkModel, root_key: str, root_name: str, *, budget: int, max_depth: int) -> Walk:
    """The declared-type tree from *root_key*, each type described once.

    Memoized by display name (a type built twice is described once), which
    also ends cycles; *budget* caps the types described and *max_depth* the
    depth, either setting ``truncated``.
    """
    out = Walk({}, {}, {})

    def descend(display: str, key: str, depth: int) -> None:
        if display in out.children:
            return
        if depth >= max_depth or out.visited >= budget:
            out.truncated = True
            return
        out.visited += 1
        out.types.setdefault(display, model.describe(key, display))
        out.connections.setdefault(display, [
            c for c in (model.connection(r, display) for r in run(model, key, CONNECT_PHASE).items)
            if c is not None])
        made = [model.child(r) for r in effective_children(model, key)]
        out.children[display] = [child for child, _key in made]
        for child, child_key in made:
            if child_key is not None:
                descend(child.type_name, child_key, depth + 1)

    descend(root_name, root_key, 0)
    return out
