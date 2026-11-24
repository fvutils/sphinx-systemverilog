"""The sub-sequence catalog: every sequence a behavioural task depends on.

A behavioural task is a sequence's ``body()`` or a component's task phase
(:meth:`~.uvm.UvmProvider.activity`).  Its catalog is the transitive closure of
the sequences it starts, each listed once, with every place it is started
from.  It answers "what do we depend on?" --- which an activity diagram, being
one task at a time, cannot.

Built from :class:`~.uvm.UvmSequence` values alone, through a *lookup*
callable, so the same code serves the live provider and a database.  Nothing
here parses or elaborates.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, Iterable

from .objects import SourceRef
from .uvm import (ACT_BRANCH, ACT_CALL, ACT_DECISION, ACT_FORK, ACT_ITEM, ACT_LOOP, ACT_SEQUENCE,
                  BY_FACTORY, JOIN_ALL, OVERRIDE_TYPE, SEQUENCE_BODY, UvmOverride,
                  UvmSequence)

#: Past this many distinct sequences the walk stops and says so.  A real
#: testbench's tests reach tens; this bounds a pathological database, not them.
MAX_CATALOG_ENTRIES = 500


@dataclass(frozen=True)
class CatalogSite:
    """One place a catalogued sequence is started."""

    #: The class whose task starts it: the root, or another catalogued sequence.
    started_by: str = ""
    #: That task: ``body``, or the root's task phase.
    method: str = ""
    #: The handle ``start`` was called on.
    handle: str = ""
    #: The sequencer passed to ``start``, as written; ``""`` when none is.
    sequencer: str = ""
    #: How the type was worked out (``RESOLVED_*`` in :mod:`.uvm`).
    resolved: str = ""
    #: For a member created elsewhere in the class, the method creating it.
    created_in: str = ""
    #: The type the source creates, when a factory type override replaced it
    #: with the catalogued one; ``""`` otherwise.
    original: str = ""
    #: The macro the start was recovered from, when it came from one.
    macro: str = ""
    location: SourceRef | None = None
    #: The helper tasks the start is reached through, outermost first, as
    #: their calls are written (``run_traffic()``, ``super.run_phase()``).
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogEntry:
    """One sequence the root depends on."""

    type_name: str = ""
    #: Sub-sequence levels below the root: 1 for a sequence the root starts
    #: itself.  The shortest path, so a sequence started both ways is direct.
    depth: int = 1
    #: Every start of it, from the root and from other catalogued sequences.
    sites: tuple[CatalogSite, ...] = ()
    #: The database it comes from; ``""`` for the design being documented.
    origin: str = ""
    #: False when its body could not be read: absent from the parsed sources,
    #: or not a sequence.  What it starts in turn is then unknown.
    found: bool = True
    #: False when it inherits the library's empty ``body()``.
    defines_body: bool = True
    #: True when it can start itself again, directly or through others.
    recursive: bool = False
    #: Transaction types its own ``body()`` drives, in first-seen order.
    items: tuple[str, ...] = ()
    #: Factory overrides that may replace it but are not certain to for this
    #: root: conditional, per-instance, or registered by another class.  Not
    #: walked: what the replacements start is not listed.
    possible: tuple[UvmOverride, ...] = ()

    @property
    def direct(self) -> bool:
        return self.depth == 1

    @property
    def started_by(self) -> list[str]:
        """The classes that start it, deduplicated, in first-seen order."""
        out: list[str] = []
        for site in self.sites:
            if site.started_by not in out:
                out.append(site.started_by)
        return out

    @property
    def resolutions(self) -> list[str]:
        """How its type was worked out, over all its sites."""
        out: list[str] = []
        for site in self.sites:
            if site.resolved and site.resolved not in out:
                out.append(site.resolved)
        return out


@dataclass(frozen=True)
class SequenceCatalog:
    """The catalog of one behavioural task."""

    #: The class whose task is the root.
    root: str = ""
    #: The task: ``body`` or a task phase.
    method: str = ""
    #: Catalogued sequences, by depth, then in the order they are first met.
    entries: tuple[CatalogEntry, ...] = ()
    #: Transaction types the root's own task drives.
    items: tuple[str, ...] = ()
    #: True when :data:`MAX_CATALOG_ENTRIES` stopped the walk.
    truncated: bool = False
    #: The factory type overrides applied: certain for this root.
    applied: tuple[UvmOverride, ...] = ()

    def entry(self, type_name: str) -> CatalogEntry | None:
        return next((e for e in self.entries if e.type_name == type_name), None)

    @property
    def direct(self) -> list[CatalogEntry]:
        return [e for e in self.entries if e.direct]

    @property
    def transitive(self) -> list[CatalogEntry]:
        return [e for e in self.entries if not e.direct]


def build_catalog(
    root: UvmSequence,
    lookup: Callable[[str], UvmSequence | None],
    origin: Callable[[str], str] = lambda name: "",
    limit: int = MAX_CATALOG_ENTRIES,
    overrides: Iterable[UvmOverride] = (),
) -> SequenceCatalog:
    """The catalog of *root*.

    *lookup* returns a sequence's ``body()`` by type name (``None`` when it is
    not a known sequence); *origin* names the database a class comes from.
    Breadth-first, so each entry's depth is its shortest distance from the
    root, and each sequence is looked up once however often it is started.

    *overrides* are the project's factory overrides.  For a component's task,
    an unconditional type override registered by its class or a base class
    (:func:`applied_overrides`) replaces the type of every sequence created
    through the factory, and the replacement is walked; any other override of
    a catalogued type is listed on its entry as possible.
    """
    root_name = root.name.split("::")[-1]
    overrides = list(overrides)
    certain = applied_overrides(root, overrides)
    replace = {_bare(o.original): _bare(o.replacement) for o in certain}
    sites: dict[str, list[CatalogSite]] = {}
    depth: dict[str, int] = {}
    bodies: dict[str, UvmSequence | None] = {}
    edges: dict[str, set[str]] = {}
    order: list[str] = []
    truncated = False

    frontier: list[tuple[str, UvmSequence]] = [(root_name, root)]
    level = 1
    while frontier:
        nxt: list[tuple[str, UvmSequence]] = []
        for owner, task in frontier:
            for node, via in _walk_calls(task.body):
                if node.kind != ACT_SEQUENCE or not node.type_name:
                    continue
                name, original = node.type_name, ""
                if node.created_by == BY_FACTORY and name in replace:
                    original, name = name, _final(replace, name)
                edges.setdefault(owner, set()).add(name)
                if name not in depth:
                    if len(order) >= limit:
                        truncated = True
                        continue
                    depth[name] = level
                    order.append(name)
                    bodies[name] = found = lookup(name)
                    # The root is walked already: a sequence that starts
                    # itself is catalogued, not walked twice.
                    if found is not None and name != root_name:
                        nxt.append((name, found))
                sites.setdefault(name, []).append(CatalogSite(
                    started_by=owner, method=task.method, handle=node.label, sequencer=node.sequencer,
                    resolved=node.resolved, created_in=node.created_in, original=original,
                    macro=node.macro, location=node.location, via=via,
                ))
        frontier, level = nxt, level + 1

    entries = []
    for name in order:     # breadth-first, so already by depth
        body = bodies[name]
        entries.append(CatalogEntry(
            type_name=name,
            depth=depth[name],
            sites=tuple(sites.get(name, ())),
            origin=origin(name) or "",
            found=body is not None,
            defines_body=body is not None and body.overridden,
            recursive=_reaches(edges, name, name),
            items=tuple(_items(body)) if body is not None else (),
            possible=tuple(o for o in overrides if _bare(o.original) == name and o not in certain),
        ))
    return SequenceCatalog(
        root=root.name, method=root.method, entries=tuple(entries),
        items=tuple(_items(root)), truncated=truncated, applied=tuple(certain),
    )


@dataclass(frozen=True)
class TreeNode:
    """One start in the nested sequence tree: the sequence, and what it starts.

    Unlike a catalog entry, one node per *start*: a sequence started from two
    places is two nodes.  Only the first is opened; the rest are marked
    :attr:`repeated`, so the tree stays the size of the design.
    """

    type_name: str = ""
    #: The handle ``start`` was called on.
    handle: str = ""
    #: How the type was worked out (``RESOLVED_*``), as on :class:`CatalogSite`.
    resolved: str = ""
    created_in: str = ""
    original: str = ""
    sequencer: str = ""
    macro: str = ""
    location: SourceRef | None = None
    #: Helper tasks the start is reached through (:attr:`CatalogSite.via`).
    via: tuple[str, ...] = ()
    #: The statements around the start that decide whether and how often it
    #: runs, outermost first: ``repeat (4)``, ``n > 0: yes``, ``fork: branch 1``.
    context: tuple[str, ...] = ()
    origin: str = ""
    #: False when its body could not be read.
    found: bool = True
    #: True when it is opened higher up the tree already.
    repeated: bool = False
    #: True when it is one of its own ancestors: the tree stops there.
    recursive: bool = False
    children: tuple["TreeNode", ...] = ()
    #: The component instance *sequencer* names in the stitched tree
    #: (``uvm_test_top.env.agt.sqr``), and its type; ``""`` when it cannot be
    #: worked out (:func:`resolve_sequencers`).
    sequencer_path: str = ""
    sequencer_type: str = ""

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class SequenceTree:
    """The nested tree of the sequences one behavioural task starts."""

    root: str = ""
    method: str = ""
    children: tuple[TreeNode, ...] = ()
    #: The factory type overrides applied (as :attr:`SequenceCatalog.applied`).
    applied: tuple[UvmOverride, ...] = ()
    #: True when :data:`MAX_CATALOG_ENTRIES` nodes stopped the tree.
    truncated: bool = False

    def walk(self):
        for child in self.children:
            yield from child.walk()


def build_tree(
    root: UvmSequence,
    lookup: Callable[[str], UvmSequence | None],
    origin: Callable[[str], str] = lambda name: "",
    limit: int = MAX_CATALOG_ENTRIES,
    overrides: Iterable[UvmOverride] = (),
) -> SequenceTree:
    """The nested sequence tree of *root*: depth-first, in source order.

    The same lookups and override rule as :func:`build_catalog`, so a tree
    and the catalog of the same task list the same sequences.
    """
    root_name = _bare(root.name)
    certain = applied_overrides(root, list(overrides))
    replace = {_bare(o.original): _bare(o.replacement) for o in certain}
    opened: set[str] = set()
    count = 0
    truncated = False

    def starts(task: UvmSequence, ancestors: tuple[str, ...]) -> tuple[TreeNode, ...]:
        nonlocal count, truncated
        out: list[TreeNode] = []
        for node, via, context in _walk_context(task.body):
            if node.kind != ACT_SEQUENCE or not node.type_name:
                continue
            if count >= limit:
                truncated = True
                break
            count += 1
            name, original = node.type_name, ""
            if node.created_by == BY_FACTORY and name in replace:
                original, name = name, _final(replace, name)
            body = lookup(name)
            recursive = name in ancestors
            repeated = not recursive and name in opened
            children: tuple[TreeNode, ...] = ()
            if body is not None and not recursive and not repeated:
                opened.add(name)
                children = starts(body, (*ancestors, name))
            out.append(TreeNode(
                type_name=name, handle=node.label, resolved=node.resolved,
                created_in=node.created_in, original=original, sequencer=node.sequencer,
                macro=node.macro, location=node.location, via=via, context=context,
                origin=origin(name) or "", found=body is not None, repeated=repeated,
                recursive=recursive, children=children,
            ))
        return tuple(out)

    children = starts(root, (root_name,))
    return SequenceTree(root=root.name, method=root.method, children=children,
                        applied=tuple(certain), truncated=truncated)


#: What a sequence's own ``start`` argument can be, to run on the sequencer the
#: sequence itself runs on.
_OWN_SEQUENCER = ("", "m_sequencer", "get_sequencer()", "p_sequencer", "this.m_sequencer",
                  "this.p_sequencer")


def resolve_sequencers(tree: SequenceTree, components) -> SequenceTree:
    """*tree* with each start's sequencer found in *components*, the stitched
    UVM tree (:class:`~..svdb.uvm_tree.UvmTree`) built from the tree's root.

    A start in the root component names a handle path from it
    (``env.agt.sqr``), followed child by child, or through a handle a
    component holds (a virtual sequencer's, :data:`~.uvm.LINK_HANDLE`).  A
    start inside a sequence runs where that sequence runs: ``m_sequencer``
    (or no sequencer, as `` `uvm_do `` passes) is its own sequencer, and
    ``p_sequencer.x`` a handle path from it.  Anything else --- a handle
    fetched from ``config_db``, a function's result --- is left unresolved.
    """
    if components is None or components.root is None or tree.method == SEQUENCE_BODY:
        return tree
    by_path = {n.path: n for n in components.nodes}
    held = {(l.source.path, l.source.port): l.target.path for l in components.links
            if l.kind == "handle" and l.state == "ok" and l.source.port and not l.target.port}

    def follow(start, parts):
        current = start
        for part in parts:
            bare = part.split("[", 1)[0]
            child = next((by_path[c] for c in current.children
                          if c in by_path and by_path[c].handle == bare), None)
            if child is None:
                target = held.get((current.path, bare))
                child = by_path.get(target) if target else None
            if child is None:
                return None
            current = child
        return current

    def resolve(nodes, here, in_sequence):
        out = []
        for n in nodes:
            text = "".join((n.sequencer or "").split())
            found = None
            if in_sequence:
                if here is not None:
                    if text in _OWN_SEQUENCER:
                        found = here
                    else:
                        for prefix in ("p_sequencer.", "this.p_sequencer."):
                            if text.startswith(prefix):
                                found = follow(here, text[len(prefix):].split("."))
            elif text:
                found = follow(components.root, text.removeprefix("this.").split("."))
            out.append(dataclasses.replace(
                n, sequencer_path=found.path if found else "",
                sequencer_type=_bare(found.type) if found else "",
                children=resolve(n.children, found, True),
            ))
        return tuple(out)

    return dataclasses.replace(tree, children=resolve(tree.children, None, False))


def _walk_context(nodes, via: tuple[str, ...] = (), context: tuple[str, ...] = ()):
    """``(node, calls, context)`` for every node, in source order; *context* is
    the loops, decision arms and fork branches around the node."""
    for node in nodes:
        yield node, via, context
        if node.kind == ACT_CALL:
            yield from _walk_context(node.children, (*via, node.label), context)
        elif node.kind == ACT_LOOP:
            yield from _walk_context(node.children, via, (*context, node.label))
        elif node.kind in (ACT_DECISION, ACT_FORK):
            for branch in node.children:
                if node.kind == ACT_DECISION:
                    text = f"{node.label}: {branch.label}" if node.label else branch.label
                else:
                    join = "" if node.join == JOIN_ALL else f" (join_{node.join})"
                    text = f"fork{join}: {branch.label}"
                if branch.kind == ACT_BRANCH:
                    yield branch, via, context
                    yield from _walk_context(branch.children, via, (*context, text))
                else:
                    yield from _walk_context([branch], via, context)
        else:
            yield from _walk_context(node.children, via, context)


@dataclass(frozen=True)
class SequenceUser:
    """One behavioural task that depends on a sequence."""

    #: The class whose task it is.
    root: str = ""
    method: str = ""
    #: Sub-sequence levels from the task to the sequence: 1 when it starts it.
    depth: int = 1
    #: True for a component's task phase (a test's ``run_phase``), False for a
    #: sequence's ``body()``.
    component: bool = False


@dataclass(frozen=True)
class SequenceUsers:
    """The reverse of the catalogs: everything that depends on one sequence."""

    name: str = ""
    #: Every start of it, from any task, deduplicated.
    sites: tuple[CatalogSite, ...] = ()
    #: Every task whose catalog lists it: component tasks first, then by depth.
    users: tuple[SequenceUser, ...] = ()
    #: Factory overrides that put it in place of another sequence.
    replaces: tuple[UvmOverride, ...] = ()

    @property
    def components(self) -> list[SequenceUser]:
        return [u for u in self.users if u.component]

    @property
    def sequences(self) -> list[SequenceUser]:
        return [u for u in self.users if not u.component]


def build_users(
    name: str,
    tasks: Iterable[UvmSequence],
    catalog_of: Callable[[UvmSequence], SequenceCatalog],
    overrides: Iterable[UvmOverride] = (),
) -> SequenceUsers:
    """Everything that depends on sequence *name*, from the catalog of every
    task in *tasks* (*catalog_of* builds one).  Read off the catalogs, so a
    task that reaches *name* only through a factory override it registers is
    a user, exactly as its catalog lists *name*.
    """
    bare = _bare(name)
    sites: list[CatalogSite] = []
    seen: set[tuple] = set()
    users: list[SequenceUser] = []
    for task in tasks:
        if not task.overridden:
            continue
        entry = catalog_of(task).entry(bare)
        if entry is None:
            continue
        users.append(SequenceUser(root=task.name, method=task.method, depth=entry.depth,
                                  component=task.method != SEQUENCE_BODY))
        for site in entry.sites:
            key = (site.started_by, site.method, site.handle, site.location)
            if key not in seen:
                seen.add(key)
                sites.append(site)
    users.sort(key=lambda u: (not u.component, u.depth, u.root, u.method))
    return SequenceUsers(name=bare, sites=tuple(sites), users=tuple(users),
                         replaces=tuple(o for o in overrides if _bare(o.replacement) == bare))


def applied_overrides(root: UvmSequence, overrides: Iterable[UvmOverride]) -> list[UvmOverride]:
    """The factory type overrides certain to be in force while *root* runs.

    Those registered, unconditionally, by the root component's class or one of
    its base classes; for a type overridden twice, the later one, unless it
    passed ``replace=0``.  None for a sequence's ``body()``: which test runs
    it, and so which overrides are registered, is not the sequence's to say.
    """
    if root.method == SEQUENCE_BODY:
        return []
    chain = {_bare(n) for n in root.chain} | {_bare(root.name)}
    chosen: dict[str, UvmOverride] = {}
    for o in overrides:
        if o.kind != OVERRIDE_TYPE or o.conditional or _bare(o.owner) not in chain:
            continue
        if not o.original or not o.replacement:
            continue
        if o.replace or _bare(o.original) not in chosen:
            chosen[_bare(o.original)] = o
    return list(chosen.values())


def users_of(provider, name: str) -> SequenceUsers:
    """:func:`build_users` over a provider's :meth:`tasks`, with its overrides."""
    overrides = overrides_of(provider)
    return build_users(name, provider.tasks(),
                       lambda task: build_catalog(task, provider.sequence, overrides=overrides),
                       overrides)


def overrides_of(provider) -> list[UvmOverride]:
    """A provider's factory overrides; none when they cannot be scanned."""
    try:
        return list(provider.overrides().overrides)
    except Exception:  # noqa: BLE001
        return []


def _bare(name: str) -> str:
    return (name or "").split("::")[-1]


def _final(replace: dict[str, str], name: str) -> str:
    """Follow a chain of type overrides (a → b, b → c) to its end."""
    seen = {name}
    while name in replace and replace[name] not in seen:
        name = replace[name]
        seen.add(name)
    return name


def _walk_calls(nodes, via: tuple[str, ...] = ()):
    """``(node, calls it is inside)`` for every node, in source order."""
    for node in nodes:
        yield node, via
        inner = (*via, node.label) if node.kind == ACT_CALL else via
        yield from _walk_calls(node.children, inner)


def _items(task: UvmSequence) -> list[str]:
    out: list[str] = []
    for node in task.walk():
        if node.kind == ACT_ITEM and node.type_name and node.type_name not in out:
            out.append(node.type_name)
    return out


def _reaches(edges: dict[str, set[str]], start: str, target: str) -> bool:
    """Whether *target* is reachable from *start* in one or more steps."""
    seen: set[str] = set()
    stack = list(edges.get(start, ()))
    while stack:
        name = stack.pop()
        if name == target:
            return True
        if name in seen:
            continue
        seen.add(name)
        stack.extend(edges.get(name, ()))
    return False
