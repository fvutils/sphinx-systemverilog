"""Design structure: the elaborated instance hierarchy, computed on demand.

A module's own declaration is the least interesting thing you can say about it.
Who instantiates it, with which parameters, under which generate branch --- that
exists only in the *elaborated* design, and reaching it means walking the
instance tree.

That walk is the expensive part of using pyslang (measured: ~0.7s for 5200
instances, against ~0ms for parse + ``getRoot()``), so this module exists to
keep it off the critical path.  :class:`StructureProvider` holds the live
``Compilation`` and walks it **at most once per process, and only when a
structural directive actually asks**.  Everything the walk produces
(:class:`DesignStructure` and friends) is plain, picklable data with no pyslang
references, matching the isolation boundary the rest of ``model`` observes.

Two consequences worth stating explicitly:

* The ``Compilation`` is *not* picklable, and Sphinx pickles whatever is stored
  on ``env``.  :class:`~sphinx_systemverilog.model.index.SvIndex` therefore drops
  its provider in ``__getstate__``; see :meth:`DesignStructure` consumers for the
  ``None`` path.
* Computed structure is a **cache**, never persisted state.  It is recomputed in
  the process that needs it, or not at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, NamedTuple

from .locations import resolve_location
from .objects import SourceRef

#: Default ceiling on instances visited during a hierarchy walk.  Exceeding it
#: stops the walk and sets :attr:`DesignStructure.truncated` rather than letting
#: a pathological generate loop hang the build.
DEFAULT_MAX_INSTANCES = 20000

#: Ceiling on hierarchy depth.  SystemVerilog forbids recursive module
#: instantiation, but generate-guarded recursion is legal and can be deep.
MAX_DEPTH = 64

#: Parameter values longer than this are shown by type rather than by value.
#: Modern parameterized RTL passes whole configuration structs as parameters ---
#: CVA6 passes a ``config_pkg::cva6_cfg_t``, which elaborates to a *17268-bit*
#: integer.  Printing that is worse than useless: it buries every other value on
#: the line and tells the reader nothing.
MAX_PARAM_VALUE_TEXT = 32

#: A type name we are willing to show in place of a value: a plain identifier,
#: optionally scope-qualified.  Slang qualifies package types with ``::``
#: (``config_pkg::cva6_cfg_t``) and module-local typedefs with ``.``
#: (``instr_tracer.interrupts_t``); both are useful names.
#:
#: Anything else is *not* more readable than the value it replaces, and is
#: deliberately excluded: an anonymous ``struct packed{...}`` says nothing, and
#: for an array type (``copro_issue_resp_t$[0:9]``) the head of the actual value
#: is more informative than the type, since it shows the elements.
_NAMED_TYPE = re.compile(r"^[A-Za-z_]\w*((::|\.)[A-Za-z_]\w*)*$")


class SvParam(NamedTuple):
    """One elaborated parameter: its name, its value, and its declared type.

    :attr:`value` is the identity --- two elaborations are the same one only if
    every value matches --- while :attr:`display` is what a reader should see.
    Keeping them separate is what lets a 17268-bit config struct render as
    ``cva6_cfg_t`` without merging two genuinely different configurations.
    """

    name: str
    #: Full value text as slang renders it.  Used for identity, not display.
    value: str
    #: Declared type, when slang reports one (``config_pkg::cva6_cfg_t``).
    type_name: str = ""

    @property
    def display(self) -> str:
        """The value if it is readable, otherwise its type, otherwise a stub."""
        if len(self.value) <= MAX_PARAM_VALUE_TEXT:
            return self.value
        if _NAMED_TYPE.match(self.type_name):
            return re.split(r"::|\.", self.type_name)[-1]
        return self.value[:MAX_PARAM_VALUE_TEXT - 1] + "…"


@dataclass(frozen=True)
class SvInstance:
    """One instantiation *site* as written inside a parent module.

    A *site* is a line of source, not an elaborated instance.  An instance array
    (``leaf u_l [3:0] (...)``) and a generate loop each elaborate to several
    instances but are written once, so both are reported once with a
    multiplicity; :attr:`total_count` is how many instances the site produced.

    :attr:`generate_path` is therefore collapsed here (``g_lp[*]``).  The real,
    per-iteration paths live on :class:`UsageSite`, which describes elaborated
    instances rather than source.
    """

    #: Instance name as written (``u_leaf``).
    inst_name: str
    #: Definition name being instantiated (``leaf``).
    type_name: str
    #: Enclosing generate blocks, outermost first (``("g_lp[*]",)``).
    generate_path: tuple[str, ...] = ()
    #: Declared array range as written (``"[3:0]"``), or ``None``.
    array_range: str | None = None
    #: Elements of the instance array; 1 for a plain instance.
    array_count: int = 1
    #: Product of the enclosing generate-loop iteration counts.
    generate_count: int = 1
    #: Elaborated parameter values, in declaration order.
    params: tuple[SvParam, ...] = ()
    location: SourceRef | None = None

    @property
    def path(self) -> str:
        """Instance name qualified by its generate path (``g_lp[*].u_g``)."""
        return ".".join((*self.generate_path, self.inst_name))

    @property
    def label(self) -> str:
        """Display label including array notation (``u_l[3:0]``)."""
        if self.array_range:
            return f"{self.path}{self.array_range}"
        return self.path

    @property
    def total_count(self) -> int:
        """Elaborated instances produced by this one site."""
        return self.array_count * self.generate_count

    @property
    def param_text(self) -> str:
        """``#(W=8, LANES=4)``, or ``""`` when the instance takes no overrides."""
        if not self.params:
            return ""
        inner = ", ".join(f"{p.name}={p.display}" for p in self.params)
        return f"#({inner})"


@dataclass(frozen=True)
class _GenStep:
    """One enclosing generate block during the walk (internal to the collector)."""

    name: str
    #: Iteration index for a for-generate; ``None`` for an if/case branch.
    index: int | None
    #: Number of iterations of the enclosing loop; 1 for a branch.
    count: int

    @property
    def label(self) -> str:
        """The real, per-iteration path element (``g_lp[2]``)."""
        return f"{self.name}[{self.index}]" if self.index is not None else self.name

    @property
    def collapsed(self) -> str:
        """The source-shaped path element (``g_lp[*]``)."""
        return f"{self.name}[*]" if self.index is not None else self.name


@dataclass(frozen=True)
class UsageSite:
    """Where a module is instantiated: the inverse of :attr:`DesignStructure.edges`.

    Unlike :class:`SvInstance`, which describes a line of source, a usage site
    describes one *elaborated* instance, so its path is concrete
    (``g_lp[2].u_g``, not ``g_lp[*].u_g``).
    """

    #: Definition name of the module containing the instantiation.
    parent_type: str
    #: The instantiation as written in that parent.
    instance: SvInstance
    #: Full hierarchical path of the *parent* (``soc.u_wide.g_wide.u_lane``).
    parent_path: str
    #: Concrete path of this instance within the parent (``g_lp[2].u_g``).
    elaborated_path: str = ""

    @property
    def hier_path(self) -> str:
        """Full hierarchical path of the instance itself."""
        return f"{self.parent_path}.{self.elaborated_path or self.instance.path}"


@dataclass
class DesignStructure:
    """The result of one hierarchy walk.  Plain data; no pyslang references."""

    #: Definition names of the elaborated top-level modules.
    tops: list[str] = field(default_factory=list)
    #: Parent definition name -> every instantiation site it contains, unioned
    #: across all of its elaborations.  This is the *type graph* view, which is
    #: what a module-to-module diagram wants.
    edges: dict[str, list[SvInstance]] = field(default_factory=dict)
    #: ``(definition name, parameter values)`` -> the sites that elaboration
    #: contains.  This is the *instance tree* view: ``cluster #(WIDE=0)`` and
    #: ``cluster #(WIDE=1)`` have genuinely different bodies, and a tree that
    #: showed the union of both would describe a design that does not exist.
    elaborations: dict[
        tuple[str, tuple[tuple[str, str], ...]], list[SvInstance]
    ] = field(default_factory=dict)
    #: Child definition name -> every place it is instantiated.
    used_by: dict[str, list[UsageSite]] = field(default_factory=dict)
    #: Instances visited by the walk, and the quantity the budget counts.
    #: Generate iterations count individually; instance-array elements count
    #: once, since only one element is walked.
    instance_count: int = 0
    #: True when the walk hit ``sv_structure_max_instances`` or the depth cap.
    truncated: bool = False

    def children_of(self, type_name: str) -> list[SvInstance]:
        """Every site in *type_name*, across all of its elaborations."""
        return self.edges.get(type_name, [])

    def children_of_elaboration(
        self, type_name: str, params: tuple[tuple[str, str], ...] = ()
    ) -> list[SvInstance]:
        """The sites in one specific elaboration of *type_name*.

        Falls back to the type-wide union when that exact parameterization was
        not elaborated, so a caller asking about an uninstantiated module still
        gets something rather than nothing.
        """
        key = (type_name, tuple(params))
        if key in self.elaborations:
            return self.elaborations[key]
        return self.edges.get(type_name, [])

    def elaborations_of(self, type_name: str) -> list[tuple[tuple[str, str], ...]]:
        """Distinct parameterizations of *type_name* that were elaborated."""
        return [params for (name, params) in self.elaborations if name == type_name]

    def sites_for(self, type_name: str) -> list[UsageSite]:
        return self.used_by.get(type_name, [])

    def param_usage(self, type_name: str) -> dict[str, dict[str, list[str]]]:
        """``{param: {value: [hierarchical paths]}}`` across every instantiation.

        Derived from :attr:`used_by` rather than stored separately, so the two
        can never disagree.  A module that is never instantiated within the
        documented sources yields ``{}`` --- there are no elaborated values to
        report, which is a different statement from "the module has no
        parameters".

        Values are grouped by their *identity*, then labelled for display. Those
        differ when a parameter is a configuration struct: two distinct configs
        both display as ``cva6_cfg_t``, and collapsing them would claim the
        design uses one configuration where it uses two. Where that happens the
        labels are numbered (``cva6_cfg_t #1``, ``cva6_cfg_t #2``) rather than
        merged.
        """
        by_identity: dict[str, dict[str, tuple[str, list[str]]]] = {}
        for site in self.sites_for(type_name):
            for param in site.instance.params:
                bucket = by_identity.setdefault(param.name, {})
                label, paths = bucket.setdefault(param.value, (param.display, []))
                paths.append(site.hier_path)

        out: dict[str, dict[str, list[str]]] = {}
        for param, values in by_identity.items():
            counts: dict[str, int] = {}
            for label, _ in values.values():
                counts[label] = counts.get(label, 0) + 1
            seen: dict[str, int] = {}
            rows: dict[str, list[str]] = {}
            for label, paths in values.values():
                if counts[label] > 1:
                    seen[label] = seen.get(label, 0) + 1
                    label = f"{label} #{seen[label]}"
                rows[label] = paths
            out[param] = rows
        return out

    def legacy_edges(self) -> dict[str, list[tuple[str, str]]]:
        """The pre-structure ``{parent: [(inst_name, child_type)]}`` shape."""
        return {
            parent: [(i.inst_name, i.type_name) for i in insts]
            for parent, insts in self.edges.items()
        }


class StructureProvider:
    """Holds the live ``Compilation`` and walks it lazily, at most once.

    The instance is created during ``build_index`` but *never called there*.
    Only a structural directive may call :meth:`get`; :attr:`computed` exists so
    that contract can be asserted by tests instead of merely documented.
    """

    def __init__(
        self,
        compilation: Any,
        source_manager: Any = None,
        tops: Iterable[str] | None = None,
        max_instances: int = DEFAULT_MAX_INSTANCES,
    ) -> None:
        self._compilation = compilation
        self._source_manager = source_manager
        #: Restrict the walk to these top-level module names (empty = all).
        self._tops = list(tops or [])
        self._max_instances = max_instances or DEFAULT_MAX_INSTANCES
        self._structure: DesignStructure | None = None
        #: Number of walks performed; asserted by the lazy-elaboration test.
        self.walk_count = 0

    @property
    def computed(self) -> bool:
        """True once the hierarchy has actually been walked."""
        return self._structure is not None

    def get(self) -> DesignStructure:
        """Return the design structure, walking the hierarchy on first call."""
        if self._structure is None:
            self.walk_count += 1
            self._structure = self._walk()
        return self._structure

    # -- the walk -------------------------------------------------------------

    def _walk(self) -> DesignStructure:
        from pyslang.ast import SymbolKind

        structure = DesignStructure()
        try:
            tops = list(self._compilation.getRoot().topInstances)
        except Exception:
            return structure
        if self._tops:
            wanted = set(self._tops)
            tops = [t for t in tops if _instance_type(t) in wanted or t.name in wanted]

        state = _WalkState(self._max_instances)
        for top in tops:
            type_name = _instance_type(top)
            if not type_name:
                continue
            structure.tops.append(type_name)
            self._descend(
                top, type_name, self._parameters(top), type_name,
                structure, state, SymbolKind, 0,
            )

        structure.instance_count = state.visited
        structure.truncated = state.truncated
        return structure

    def _descend(
        self,
        inst: Any,
        type_name: str,
        params: tuple[tuple[str, str], ...],
        hier_path: str,
        structure: DesignStructure,
        state: "_WalkState",
        SymbolKind: Any,
        depth: int,
    ) -> None:
        """Record every instantiation site inside *inst*, then recurse."""
        if depth >= MAX_DEPTH:
            state.truncated = True
            return
        body = getattr(inst, "body", None)
        if body is None:
            return
        # The same definition is re-walked at each elaboration rather than
        # cached by name: two elaborations of one module can genuinely differ,
        # most obviously when an if-generate branches on a parameter.
        elaboration = structure.elaborations.setdefault((type_name, params), [])
        for child, steps, array in self._instantiations(body, (), state, SymbolKind):
            if state.exhausted:
                structure.truncated = True
                return
            child_type = _instance_type(child)
            if not child_type:
                continue
            state.visited += 1
            record = self._make_instance(child, child_type, steps, array)
            _add_edge(structure.edges, type_name, record)
            _append_unique(elaboration, record)
            # Generate iterations are listed individually, so each carries its
            # concrete index.  An instance array is walked once, so its path
            # keeps the range: this one entry stands for all of its elements.
            leaf = record.inst_name + (record.array_range or "")
            real_path = ".".join((*(s.label for s in steps), leaf))
            structure.used_by.setdefault(child_type, []).append(
                UsageSite(
                    parent_type=type_name,
                    instance=record,
                    parent_path=hier_path,
                    elaborated_path=real_path,
                )
            )
            self._descend(
                child, child_type, record.params, f"{hier_path}.{real_path}",
                structure, state, SymbolKind, depth + 1,
            )

    def _instantiations(
        self, scope: Any, steps: tuple["_GenStep", ...], state: "_WalkState",
        SymbolKind: Any,
    ):
        """Yield ``(instance_symbol, generate_steps, array_symbol)`` for a body.

        Descends through generate blocks and instance arrays, which the previous
        implementation skipped entirely --- a module whose children all sit
        inside a ``generate`` reported no children at all, and an instance array
        reported none either.
        """
        try:
            members = list(scope)
        except TypeError:
            return
        for member in members:
            if state.exhausted:
                return
            kind = member.kind
            if kind == SymbolKind.Instance:
                yield member, steps, None
            elif kind == SymbolKind.InstanceArray:
                # Elements of an array share a parameterization and a body, so
                # one element describes them all; the count carries the rest.
                # Walking all N would multiply the cost of wide arrays for no
                # new information.
                element = _first_element(member)
                if element is not None:
                    yield element, steps, member
            elif kind == SymbolKind.GenerateBlockArray:
                entries = [
                    e for e in _members(member)
                    if e.kind == SymbolKind.GenerateBlock
                    and not getattr(e, "isUninstantiated", False)
                ]
                name = getattr(member, "name", "") or ""
                for entry in entries:
                    step = _GenStep(
                        name=name,
                        index=getattr(entry, "arrayIndex", None),
                        count=len(entries),
                    )
                    yield from self._instantiations(
                        entry, steps + (step,), state, SymbolKind
                    )
            elif kind == SymbolKind.GenerateBlock:
                # An if/case-generate branch that was *not* taken elaborates as
                # an uninstantiated block full of UninstantiatedDefSymbols;
                # reporting those would describe a design that does not exist.
                if getattr(member, "isUninstantiated", False):
                    continue
                name = getattr(member, "name", "") or getattr(
                    member, "externalName", ""
                ) or ""
                sub = steps + (_GenStep(name, None, 1),) if name else steps
                yield from self._instantiations(member, sub, state, SymbolKind)

    def _make_instance(
        self, sym: Any, type_name: str, steps: tuple["_GenStep", ...], array: Any
    ) -> SvInstance:
        inst_name = getattr(sym, "name", "") or ""
        array_range = None
        array_count = 1
        if array is not None:
            inst_name = array.name
            array_range = _range_text(array)
            array_count = _element_count(array)
        generate_count = 1
        for step in steps:
            generate_count *= max(step.count, 1)
        return SvInstance(
            inst_name=inst_name,
            type_name=type_name,
            generate_path=tuple(s.collapsed for s in steps),
            array_range=array_range,
            array_count=array_count,
            generate_count=generate_count,
            params=self._parameters(sym),
            location=resolve_location(
                self._source_manager, getattr(array or sym, "location", None)
            ),
        )

    def _parameters(self, sym: Any) -> tuple[SvParam, ...]:
        """Elaborated parameter values for one instance.

        These are the *resolved* values, so ``#(.W(BUS_W))`` reports ``W=32``,
        not ``W=BUS_W`` --- which is the question a reader of the docs is
        actually asking.

        The declared type is captured alongside the value because the value
        alone is not always readable: a struct parameter elaborates to one very
        wide integer, and its type name is the only useful thing to show.
        """
        from pyslang.ast import SymbolKind

        body = getattr(sym, "body", None)
        if body is None:
            return ()
        out: list[SvParam] = []
        for member in _members(body):
            if member.kind != SymbolKind.Parameter:
                continue
            try:
                value = str(member.value)
            except Exception:
                continue
            out.append(SvParam(member.name, value, _type_name(member)))
        return tuple(out)


class _WalkState:
    """Budget tracking shared across one walk."""

    def __init__(self, max_instances: int) -> None:
        self.visited = 0
        self.max_instances = max_instances
        self.truncated = False

    @property
    def exhausted(self) -> bool:
        if self.visited >= self.max_instances:
            self.truncated = True
            return True
        return False


# -- symbol helpers -----------------------------------------------------------


def _members(scope: Any) -> list[Any]:
    try:
        return list(scope)
    except TypeError:
        return []


def _instance_type(inst: Any) -> str | None:
    """The definition name behind an instance symbol."""
    body = getattr(inst, "body", None)
    if body is not None:
        defn = getattr(body, "definition", None)
        if defn is not None and getattr(defn, "name", ""):
            return defn.name
        if getattr(body, "name", ""):
            return body.name
    return getattr(inst, "name", None) or None


def _first_element(array: Any) -> Any | None:
    """The first elaborated element of an instance array.

    Elements of an array share a parameterization and a body, so one element
    describes them all; :attr:`SvInstance.array_count` carries the multiplicity.
    Walking all N would multiply the cost of wide arrays for no new information.
    """
    for member in _members(array):
        if getattr(member, "body", None) is not None:
            return member
    return None


def _type_name(sym: Any) -> str:
    """The declared type of a symbol, as text (``config_pkg::cva6_cfg_t``)."""
    try:
        return str(sym.type)
    except Exception:
        return ""


def _range_text(array: Any) -> str | None:
    try:
        text = str(array.range)
    except Exception:
        return None
    return text or None


def _element_count(array: Any) -> int:
    count = sum(1 for m in _members(array) if getattr(m, "body", None) is not None)
    return count or 1


def _add_edge(
    edges: dict[str, list[SvInstance]], parent: str, record: SvInstance
) -> None:
    """Append *record* unless an identical site is already recorded.

    The same module is often elaborated more than once (``cluster #(W=8)`` and
    ``cluster #(W=32)``).  Deduplicating on the whole record keeps genuinely
    distinct parameterizations visible while collapsing repeat elaborations of
    an identical one.
    """
    _append_unique(edges.setdefault(parent, []), record)


def _append_unique(bucket: list[SvInstance], record: SvInstance) -> None:
    if record not in bucket:
        bucket.append(record)
