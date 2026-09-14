"""UVM testbench structure: the component hierarchy, computed on demand.

This is the testbench analogue of :mod:`~sphinx_systemverilog.model.structure`,
and it deliberately mirrors that module's shape --- same lazy provider contract,
same picklable-data boundary --- because the two answer the same kind of
question about different halves of a project.

The difference is where the hierarchy *lives*.  An RTL hierarchy is elaborated
by the compiler: slang hands it over, and the walk is a traversal.  A UVM
hierarchy is not elaborated by anything at compile time; it exists only as
statements inside ``build_phase`` that would, if run, call the factory.  So this
module reads those statements and reports **what the source says will be
built** --- which is a claim about the code, never about a simulation.

That distinction drives the one rule this module will not bend.  A component
whose type cannot be resolved --- because its package was not parsed, or was
never generated --- must still appear.  Three states are modelled explicitly:

``ok``
    The type resolved and the walk descended into it.
``opaque``
    A deliberate boundary (see ``sv_uvm_blackbox``).  The node is real; its
    contents were not looked at.
``unresolved``
    The type did not resolve.  The node is real and its declared type name is
    reported, but nothing below it is known.

The alternative --- dropping what cannot be resolved --- produces a tree that
looks complete and is not, which is the one failure mode a documentation tool
must not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Any, Iterable, Iterator

from .locations import resolve_location
from .objects import SourceRef

#: Default ceiling on components visited during a testbench walk.  Mirrors
#: ``DEFAULT_MAX_INSTANCES``; exceeding it sets :attr:`UvmStructure.truncated`.
DEFAULT_MAX_COMPONENTS = 5000

#: Ceiling on component-hierarchy depth.  A testbench is naturally shallow
#: (``test -> env -> agent -> driver`` is 4), so this is generous; it exists to
#: terminate a mutually-recursive ``build_phase``, which is legal to write.
MAX_DEPTH = 32

#: Node states.  See the module docstring --- these are the whole point.
STATE_OK = "ok"
STATE_OPAQUE = "opaque"
STATE_UNRESOLVED = "unresolved"

#: Node kinds.  A TLM port is deliberately **not** a component: real UVM
#: declares ``uvm_port_base #(IF) extends IF``, where ``IF`` derives from
#: ``uvm_void``, so a port holds an internal component proxy rather than being
#: one.  Ports therefore never appear in a component tree read from
#: ``build_phase``, which is correct --- but they are exactly what the schematic
#: is made of, so the classification is kept for reading declared member types.
KIND_COMPONENT = "component"
KIND_PORT = "port"

#: How the created type is named in source, for :attr:`UvmChild.created_by`.
BY_FACTORY = "factory"
BY_NEW = "new"

#: Base classes that place a component in a schematic tier (§7.4).  Searched
#: along the *base chain*, nearest ancestor first, so the most specific base a
#: class actually derives from is what decides --- a class extending
#: ``uvm_sequencer`` is a sequencer, not the ``uvm_component`` it also is.
_TIER_BY_BASE = {
    "uvm_sequencer": "sequencer",
    "uvm_sequencer_base": "sequencer",
    "uvm_scoreboard": "analysis",
    "uvm_subscriber": "analysis",
    "uvm_driver": "driver",
    "uvm_monitor": "monitor",
    "uvm_agent": "agent",
    "uvm_env": "env",
    "uvm_test": "test",
}

#: Prefix identifying a library type.  The walk always stops at these, whatever
#: the user configures: `uvm_component`'s own internals are noise in a document
#: about *your* testbench.  Matching on the naming convention rather than on the
#: declaring package is deliberate --- it works identically against real UVM,
#: the test stub, and a vendor library that follows the same convention.
_LIBRARY_PREFIX = "uvm_"

#: What slang stringifies an unresolvable type to.  This is the sentinel the
#: whole unresolved-node mechanism hangs on.
_ERROR_TYPE = "<error>"

#: Default base classes to stop at, referenced by ``config.py`` so the shipped
#: default and the library default cannot drift apart.  A register model is here
#: because it is the thing most often generated rather than written, and so the
#: thing most often absent when documentation is built.
#:
#: ``None`` means "use this"; an empty list means "stop at nothing".
DEFAULT_BLACKBOX_BASES = ("uvm_reg_block",)

#: Macros whose *content* is registration boilerplate rather than API, matched
#: (as ``fnmatch`` globs, against every name in a member's expansion chain) by
#: ``sv_ignore_macro_content``.  Referenced by ``config.py`` so the shipped
#: default and this list cannot drift apart, and re-exported from the package
#: root so a project can extend rather than restate it::
#:
#:     from sphinx_systemverilog import UVM_BOILERPLATE_MACROS
#:     sv_ignore_macro_content = [*UVM_BOILERPLATE_MACROS, "my_reg_field_decl"]
#:
#: Globs rather than exact names because the utils family has a dozen spellings
#: (``_begin``, ``_param_``, ``_end``) and enumerating them is a list that goes
#: stale with the next UVM release.  Everything here declares members whose
#: prose would be identical on every class in the testbench --- ``get_type``,
#: ``create``, ``get_type_name``, the field-automation hooks --- which is the
#: test for adding to it.
UVM_BOILERPLATE_MACROS = (
    "uvm_*_utils",
    "uvm_*_utils_begin",
    "uvm_field_*",
    "uvm_*_imp_decl",
)

#: Classes whose static ``set``/``get`` are configuration-database accesses.
#: Matched against the *lexical* path of the called subroutine
#: (``mini_uvm_pkg::uvm_config_db::set``), so a specialization's parameters do
#: not have to be parsed and a user's own ``set`` cannot be mistaken for one.
#:
#: ``uvm_resource_db`` is deliberately absent: its ``set`` takes its arguments
#: in a different order, so treating the two as interchangeable would report
#: scopes and fields swapped.
CONFIG_DB_CLASSES = ("uvm_config_db",)

#: The two halves of a configuration access.
ACTION_SET = "set"
ACTION_GET = "get"

#: The base class every TLM port, export and imp derives from.  Used both to
#: tell a port apart from a component in a declared member list, and --- via
#: the *lexical* path of ``uvm_port_base::connect`` --- to tell a TLM
#: connection apart from the many other methods called ``connect``.
PORT_BASE = "uvm_port_base"

#: The method UVM connects components in.  Scanning only this one is a
#: deliberate narrowing: a ``connect`` **call** is unambiguous wherever it is
#: written, but a component-handle *assignment* is only wiring by convention,
#: and that convention is exactly "it happens in ``connect_phase``".  Reading
#: assignments from arbitrary methods would turn every ``m_parent = parent`` in
#: a constructor into an edge.
CONNECT_PHASE = "connect_phase"

#: How a port is named at its end of a connection.  Taken from the port type's
#: own name rather than from anything structural, because that suffix *is* the
#: convention --- real UVM has no other marker of a port's direction.  Checked
#: longest-first so ``uvm_seq_item_pull_export`` is not read as a ``_port``.
_PORT_ROLES = (("_export", "export"), ("_imp", "imp"), ("_port", "port"))

#: What kind of thing flows along a connection.  Only used to colour and label
#: an edge; nothing behavioural hangs on it.
LINK_ANALYSIS = "analysis"
LINK_SEQ_ITEM = "seq_item"
LINK_TLM = "tlm"
#: Not a TLM connection at all: a component handle assigned to another
#: component's handle, which is how a virtual sequencer is wired.  A walker
#: that only looked at ``connect`` calls would draw a virtual sequencer with no
#: edges whatsoever, which is the one component whose whole purpose is edges.
LINK_HANDLE = "handle"

#: Argument positions in ``uvm_config_db#(T)::set/get(cntxt, inst_name,
#: field_name, value)``.  Both halves share the signature, which is why one
#: extractor serves both.
_ARG_CNTXT, _ARG_SCOPE, _ARG_FIELD, _ARG_VALUE = 0, 1, 2, 3


# -- factory overrides -------------------------------------------------------
#
# The one construct in UVM that makes a component tree *lie*.  `build_phase`
# says `my_driver::type_id::create(...)`, the extraction reads `my_driver`, and
# the simulation builds something else entirely.  Nothing in the agent's own
# source hints at it: the override is written somewhere else, usually a test.
#
# Which is why these are **annotated, never resolved** (plan Risk 2).  An
# override is applied at run time, may sit under an `if`, and an *inst*
# override is keyed on a hierarchical path that does not exist until the run.
# Rewriting a tree node to the override's type would replace one confident
# wrong answer with another.

#: A type override replaces a type everywhere; an inst override replaces it
#: only under a matching hierarchical path.
OVERRIDE_TYPE = "type"
OVERRIDE_INST = "inst"

#: ``(declaring class, method) -> (kind, original arg, override arg, path arg)``.
#:
#: Positions are read **per method** rather than uniformly, because UVM's own
#: argument orders disagree: the `uvm_component` inst form takes the path
#: *first* and the `uvm_factory` inst form takes it *last*.  A single
#: "path is argument N" rule would report the two swapped, and both compile.
#:
#: The registry forms have no original argument at all --- the type being
#: replaced is the specialization's own ``Tname``, which is the same trick
#: :func:`registry_type_name` uses for ``create``.
_OVERRIDE_SIGNATURES: dict[tuple[str, str], tuple[str, int | None, int, int | None]] = {
    ("uvm_component", "set_type_override_by_type"): (OVERRIDE_TYPE, 0, 1, None),
    ("uvm_component", "set_type_override"):         (OVERRIDE_TYPE, 0, 1, None),
    ("uvm_component", "set_inst_override_by_type"): (OVERRIDE_INST, 1, 2, 0),
    ("uvm_component", "set_inst_override"):         (OVERRIDE_INST, 1, 2, 0),
    ("uvm_factory", "set_type_override_by_type"):   (OVERRIDE_TYPE, 0, 1, None),
    ("uvm_factory", "set_type_override_by_name"):   (OVERRIDE_TYPE, 0, 1, None),
    ("uvm_factory", "set_inst_override_by_type"):   (OVERRIDE_INST, 0, 1, 2),
    ("uvm_factory", "set_inst_override_by_name"):   (OVERRIDE_INST, 0, 1, 2),
    ("uvm_component_registry", "set_type_override"): (OVERRIDE_TYPE, None, 0, None),
    ("uvm_component_registry", "set_inst_override"): (OVERRIDE_INST, None, 0, 1),
    ("uvm_object_registry", "set_type_override"):    (OVERRIDE_TYPE, None, 0, None),
    ("uvm_object_registry", "set_inst_override"):    (OVERRIDE_INST, None, 0, 1),
}

#: The accessor every registered class gets from ``uvm_*_utils``.  Its
#: *lexical path* names the class it was expanded into, which is how
#: ``fast_driver::get_type()`` gives up ``fast_driver``.
_GET_TYPE = "get_type"


# -- sequences ---------------------------------------------------------------
#
# A sequence differs from everything above it in this module in one way that
# shapes the whole extraction: a component's structure is a *set* of facts
# (these children, these ports, these connections) while a sequence's structure
# is an *order*.  ``body()`` elaborates with its control flow intact, and every
# construct in it maps onto exactly one UML activity element, so the model here
# is a tree that mirrors the statement tree rather than a flat list.

#: The class that declares ``body``, ``start``, ``start_item`` and
#: ``finish_item``.  Used as the *lexical* discriminator, exactly as
#: :data:`PORT_BASE` is for connections: a testbench is full of methods called
#: ``start``, and only the ones declared here run a sequence.
SEQUENCE_BASE = "uvm_sequence_base"

#: The base of a transaction object.  What separates ``seq.start(seqr)`` --- a
#: sub-sequence, which can be a cross-reference to its own diagram --- from
#: ``start_item(it)``, which is a single transaction and the end of the road.
SEQUENCE_ITEM_BASE = "uvm_sequence_item"

#: The one method rendered.  Scope discipline, and the same narrowing
#: :data:`CONNECT_PHASE` applies: ``pre_body``/``post_body`` and the reactive
#: hooks are real, and drawing them would turn one diagram into five.
SEQUENCE_BODY = "body"

#: Methods on :data:`SEQUENCE_BASE` that begin something worth drawing, and the
#: node kind each produces.  ``finish_item`` is deliberately absent: it is the
#: back half of the transaction ``start_item`` already drew.
_START_METHODS = {"start": "sequence", "start_item": "item"}
_ABSORBED_METHODS = ("finish_item",)

#: Activity node kinds.
ACT_ACTION = "action"        # a plain step
ACT_SEQUENCE = "sequence"    # a sub-sequence being started
ACT_ITEM = "item"            # a single transaction
ACT_DECISION = "decision"    # an `if` or a `case`
ACT_BRANCH = "branch"        # one arm of a decision or one fork branch
ACT_FORK = "fork"            # `fork ... join[_any|_none]`
ACT_LOOP = "loop"            # any of the six loop statements
ACT_DELAY = "delay"          # a `#` time control

#: Join semantics, read from ``StatementBlockKind`` rather than guessed.
JOIN_ALL, JOIN_ANY, JOIN_NONE = "all", "any", "none"

#: How each loop statement is labelled, and which attribute holds the
#: expression that controls it.  ``forever`` has none, which is the point.
_LOOP_LABELS = (
    ("RepeatLoop", "repeat", "count"),
    ("ForeverLoop", "forever", ""),
    ("WhileLoop", "while", "cond"),
    ("DoWhileLoop", "do while", "cond"),
    ("ForLoop", "for", "stopExpr"),
    ("ForeachLoop", "foreach", ""),
)


def _type_name(type_symbol: Any) -> str:
    """A display name for a type: ``my_agent``, ``uvm_analysis_port#(my_item)``."""
    if type_symbol is None:
        return ""
    name = getattr(type_symbol, "name", "") or ""
    text = str(type_symbol)
    # A specialization stringifies with its parameters, which is more
    # informative than the bare name and is what a reader sees in source.
    return text if name and text.startswith(name) else (name or text)


def base_chain(type_symbol: Any) -> list[str]:
    """Names of *type_symbol* and every class it derives from, most-derived first.

    Terminates on a cycle rather than trusting the input: slang will not hand
    one over, but this walk also runs against half-elaborated code.
    """
    chain: list[str] = []
    seen: set[int] = set()
    current = type_symbol
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = getattr(current, "name", "")
        if not name:
            break
        chain.append(name)
        current = getattr(current, "baseClass", None)
    return chain


def classify(chain: list[str]) -> tuple[str, str]:
    """``(kind, tier)`` for a class, given its base chain.

    ``kind`` is :data:`KIND_COMPONENT` or :data:`KIND_PORT`; ``tier`` is the
    §7.4 schematic tier, or ``""`` for a component the taxonomy does not place.
    """
    kind = KIND_PORT if PORT_BASE in chain else KIND_COMPONENT
    for name in chain:
        tier = _TIER_BY_BASE.get(name)
        if tier:
            return kind, tier
    return kind, ""


def is_component(chain: list[str]) -> bool:
    """True when a class derives from ``uvm_component``."""
    return "uvm_component" in chain


def is_port(chain: list[str]) -> bool:
    """True when a class derives from ``uvm_port_base``."""
    return PORT_BASE in chain


def is_sequence(chain: list[str]) -> bool:
    """True when a class derives from ``uvm_sequence_base``."""
    return SEQUENCE_BASE in chain


def is_sequence_item(chain: list[str]) -> bool:
    """True when a class is a transaction and *not* a sequence.

    Order matters: every sequence is also a ``uvm_sequence_item``, so asking
    this question the other way round classifies every sequence as an item.
    """
    return SEQUENCE_ITEM_BASE in chain and not is_sequence(chain)


#: What a UVM class *is*, for the badge on its own documentation page.
#: Ordered: the first match wins, and the order encodes the one place a naive
#: reading goes wrong --- every sequence is also a ``uvm_sequence_item``, so
#: the sequence test has to come first.  ``uvm_object`` is last because it is
#: the base of everything above it and so says nothing on its own.
_UVM_ROLES = (
    (SEQUENCE_BASE, "sequence"),
    (SEQUENCE_ITEM_BASE, "sequence item"),
    (PORT_BASE, "TLM port"),
    ("uvm_component", "component"),
    ("uvm_object", "object"),
)


#: The standard phases, in the order UVM runs them.
#:
#: Ordered by *execution* rather than alphabetically or by source position,
#: because that is the order that answers the question a reader has: what does
#: this component do, and when. A component that builds in ``build_phase`` and
#: drives in ``run_phase`` reads correctly in this order and confusingly in
#: any other.
#:
#: The run-time schedule (``reset``/``configure``/``main``/``shutdown``) is
#: included because a component that uses it uses it *instead of* ``run_phase``,
#: and a list that omitted it would report such a component as doing nothing.
UVM_PHASES = (
    "build_phase",
    "connect_phase",
    "end_of_elaboration_phase",
    "start_of_simulation_phase",
    "run_phase",
    "pre_reset_phase",
    "reset_phase",
    "post_reset_phase",
    "pre_configure_phase",
    "configure_phase",
    "post_configure_phase",
    "pre_main_phase",
    "main_phase",
    "post_main_phase",
    "pre_shutdown_phase",
    "shutdown_phase",
    "post_shutdown_phase",
    "extract_phase",
    "check_phase",
    "report_phase",
    "final_phase",
)

_PHASE_ORDER = {name: position for position, name in enumerate(UVM_PHASES)}


def phase_inventory(names: Iterable[str]) -> list[str]:
    """The standard phases among *names*, in the order UVM runs them.

    A component inherits every phase method and overrides two or three, so the
    useful fact is which ones it *overrode* --- and the caller supplies only
    the class's own members, never the inherited ones, for exactly that reason.
    """
    found = {name for name in names if name in _PHASE_ORDER}
    return sorted(found, key=_PHASE_ORDER.__getitem__)


#: The library's own classes, and what deriving from one makes you.
#:
#: Needed because a project indexes *its own* sources, not UVM's: a chain walk
#: over `extends` names in the index reaches ``uvm_agent`` and stops, because
#: ``uvm_agent`` is not an object in that index and never will be. Only the
#: name is in hand, so the name has to be enough.
#:
#: Found by building this project's own documentation, where exactly that
#: happens. The chain walk works perfectly against a test fixture that compiles
#: the library into the same index and produces nothing at all in a real one.
#:
#: Same knowledge and same shape as :data:`_TIER_BY_BASE`, which the schematic
#: has relied on since U3; kept separate because a tier is about *layout* and a
#: role is about *identity*, and the two lists genuinely differ --- a sequence
#: has no tier and ``uvm_component`` has no tier either.
_LIBRARY_ROLES = {
    "uvm_sequence": "sequence",
    "uvm_sequence_base": "sequence",
    "uvm_sequence_item": "sequence item",
    "uvm_transaction": "sequence item",
    "uvm_port_base": "TLM port",
    "uvm_agent": "component",
    "uvm_env": "component",
    "uvm_test": "component",
    "uvm_driver": "component",
    "uvm_monitor": "component",
    "uvm_scoreboard": "component",
    "uvm_subscriber": "component",
    "uvm_sequencer": "component",
    "uvm_sequencer_base": "component",
    "uvm_component": "component",
    "uvm_object": "object",
}


def uvm_role(chain: list[str]) -> str:
    """What a class *is* in UVM terms, or ``""`` for a class that is nothing.

    A one-word answer to the question a reader arriving on a class page asks
    first, and one they otherwise have to reconstruct by following ``extends``
    up three or four levels into the library.

    Answered in two passes, and the second is the one that does the work in
    practice. The first looks for a *root* base --- right when the whole chain
    is in hand. The second consults :data:`_LIBRARY_ROLES`, because a real
    project's index contains its own classes and not UVM's, so a chain walk
    reaches ``uvm_agent`` and can go no further.

    ``""`` is a real answer: a plain SystemVerilog class that never touches UVM
    gets no badge rather than a misleading one.
    """
    for base, role in _UVM_ROLES:
        if base in chain:
            return role
    for name in chain:
        role = _LIBRARY_ROLES.get(name)
        if role:
            return role
    return ""


def classify_port(chain: list[str]) -> tuple[str, str]:
    """``(role, link)`` for a port type, given its base chain.

    Both come from *names*, and deliberately so.  UVM records a port's
    direction nowhere structural --- ``uvm_analysis_port`` and
    ``uvm_analysis_export`` have the same shape and differ only in what they are
    called --- so the naming convention is the only signal there is.  The whole
    chain is searched rather than just the leaf, so a user's
    ``my_analysis_port extends uvm_analysis_port`` still reads as one.
    """
    role, link = "port", LINK_TLM
    for name in chain:
        for suffix, candidate in _PORT_ROLES:
            if name.endswith(suffix):
                role = candidate
                break
        else:
            continue
        break
    for name in chain:
        if "analysis" in name:
            link = LINK_ANALYSIS
            break
        if "seq_item" in name:
            link = LINK_SEQ_ITEM
            break
    return role, link


def registry_type_name(call: Any) -> str | None:
    """The type a ``type_id::create`` call constructs, or ``None``.

    The obvious approach --- read the call's return type --- does not work.  A
    ``create`` call reports the *generic* ``uvm_component_registry::T``, which
    names nothing.  The created type is instead carried by the registry's
    ``Tname`` string parameter, so the specialization the subroutine was found
    in is what has to be inspected::

        my_agent::type_id::create("agt", this)
        └─ subroutine "create"
           └─ parentScope = uvm_component_registry#(my_agent, "my_agent")
              └─ Parameter Tname = "my_agent"

    Returns ``None`` for any call that is not a factory create, so callers can
    use it as the test for one.
    """
    subroutine = getattr(call, "subroutine", None)
    if getattr(subroutine, "name", None) != "create":
        return None
    scope = getattr(subroutine, "parentScope", None)
    if scope is None:
        return None
    try:
        members = list(scope)
    except TypeError:
        return None
    for member in members:
        if getattr(member, "name", "") != "Tname":
            continue
        value = getattr(member, "value", None)
        if value is None:
            return None
        # ConstantValue renders a string with its quotes; the name is inside.
        return str(value).strip('"') or None
    return None


@dataclass
class UvmStructure:
    """The extracted testbench component hierarchy.

    Plain, picklable data holding no pyslang references, matching the isolation
    boundary the rest of ``model`` observes.
    """

    #: Type name of the root component (``my_test``), or ``""`` if unresolved.
    root: str = ""
    #: How the root was determined: ``"config"``, ``"run_test"`` or ``""``.
    root_origin: str = ""
    #: Component type name -> the children its ``build_phase`` creates.
    children: dict[str, list["UvmChild"]] = field(default_factory=dict)
    #: Component type name -> what is known about the type itself.
    types: dict[str, "UvmType"] = field(default_factory=dict)
    #: Component type name -> the connections its ``connect_phase`` makes.
    connections: dict[str, list["UvmConnection"]] = field(default_factory=dict)
    #: Distinct component types visited by the walk.
    component_count: int = 0
    #: True when the walk hit the budget or depth ceiling.
    truncated: bool = False
    #: Root candidates found when auto-detection saw more than one ``run_test``.
    #: Reported rather than silently picking the first.
    root_candidates: tuple[str, ...] = ()

    def children_of(self, type_name: str) -> list["UvmChild"]:
        return self.children.get(type_name, [])

    def type_of(self, type_name: str) -> "UvmType | None":
        return self.types.get(type_name)

    def connections_of(self, type_name: str) -> list["UvmConnection"]:
        return self.connections.get(type_name, [])

    def built_by(self, type_name: str) -> list[tuple[str, "UvmChild"]]:
        """``(parent type, the creation site)`` for every place *type_name* is built.

        The inverse of :meth:`children_of`, and the question a reader on a
        component's own page actually has: not "what does this build" --- they
        can see that --- but "who builds *me*, and under what name".

        Derived rather than stored, so the two can never disagree. Cheap: the
        containment map is a few dozen entries even for a large testbench,
        because it is keyed on component *types* rather than on instances.
        """
        return [
            (parent, child)
            for parent, children in self.children.items()
            for child in children
            if child.type_name.split("#", 1)[0] == type_name
        ]

    @property
    def unresolved(self) -> list["UvmChild"]:
        """Every unresolved node in the tree.  Never empty by accident."""
        return [
            child
            for children in self.children.values()
            for child in children
            if child.state == STATE_UNRESOLVED
        ]

    @property
    def opaque(self) -> list["UvmChild"]:
        """Every deliberately black-boxed node."""
        return [
            child
            for children in self.children.values()
            for child in children
            if child.state == STATE_OPAQUE
        ]


@dataclass(frozen=True)
class UvmPort:
    """One TLM port, export or imp *declared* by a component type.

    Read from the declared member list rather than from a creation site, which
    is not merely convenient: a port is constructed with ``new`` inside the
    constructor as often as in ``build_phase``, and a schematic wants the ports
    a component *has*, which is a property of the type either way.
    """

    name: str = ""
    #: Full type as written, including specialization: ``uvm_analysis_port#(t)``.
    type_name: str = ""
    #: ``"port"``, ``"export"`` or ``"imp"``, from the type-name suffix.
    role: str = "port"
    #: :data:`LINK_ANALYSIS`, :data:`LINK_SEQ_ITEM` or :data:`LINK_TLM`.
    link: str = LINK_TLM
    #: Class that declares it, which is not always the class that has it.
    declared_by: str = ""

    @property
    def library(self) -> bool:
        """True when this port comes from UVM rather than from the user's code.

        Real ``uvm_driver`` hands every driver three ports --- ``seq_item_port``
        is the one anybody connects, and ``seq_item_prod_if`` and ``rsp_port``
        are plumbing.  The stub's driver has none, so this distinction does not
        exist there at all; it was found by the corpus gate, which is what that
        gate is for.
        """
        return self.declared_by.startswith(_LIBRARY_PREFIX)


@dataclass(frozen=True)
class UvmType:
    """What is known about one component *type*, independent of any use of it."""

    name: str = ""
    #: Base-class names, most-derived first, starting with :attr:`name`.
    chain: tuple[str, ...] = ()
    #: :data:`KIND_COMPONENT` or :data:`KIND_PORT`.
    kind: str = KIND_COMPONENT
    #: §7.4 schematic tier, or ``""`` when the taxonomy does not place it.
    tier: str = ""
    #: TLM ports this type declares, in declaration order.
    ports: tuple[UvmPort, ...] = ()
    location: SourceRef | None = None

    def port(self, name: str) -> UvmPort | None:
        return next((p for p in self.ports if p.name == name), None)


@dataclass(frozen=True)
class UvmEndpoint:
    """One end of a connection, as a chain of handles from the writing class.

    ``agt_a.mon.ap.connect(...)`` written in ``tlm_env`` gives
    ``path=("agt_a", "mon")`` and ``port="ap"``.  The path is relative because
    that is all the source says: ``tlm_env`` may itself be instantiated
    anywhere, and prefixing a guessed absolute path would be inventing one.
    """

    #: Component handles, outermost first.  Empty when the endpoint is ``this``.
    path: tuple[str, ...] = ()
    #: Port name, or ``""`` when the endpoint is a component rather than a port.
    port: str = ""
    #: Declared type of whatever the chain ends at.
    type_name: str = ""
    #: True when the chain ends at a ``uvm_component`` rather than a port.
    component: bool = False
    #: :data:`LINK_ANALYSIS`/:data:`LINK_SEQ_ITEM`/:data:`LINK_TLM` for a port.
    link: str = LINK_TLM

    @property
    def text(self) -> str:
        """``agt_a.mon.ap`` --- the endpoint as it reads in source."""
        parts = [*self.path, *([self.port] if self.port else [])]
        return ".".join(parts) or "this"


@dataclass(frozen=True)
class UvmConnection:
    """One connection written in a ``connect_phase``.

    Direction is source-to-sink as written: for a ``connect`` call the source is
    the port the method was invoked on, and for a handle assignment the source
    is the left-hand side --- a virtual sequencer's handle is assigned *from*
    the real sequencer, and the stimulus then flows the way the assignment
    reads.
    """

    #: Component type whose ``connect_phase`` this was written in.
    owner: str = ""
    source: UvmEndpoint = field(default_factory=UvmEndpoint)
    target: UvmEndpoint = field(default_factory=UvmEndpoint)
    #: One of the ``LINK_*`` constants.
    kind: str = LINK_TLM
    #: True when the connection sits under an ``if``/``case`` and may not happen.
    conditional: bool = False
    location: SourceRef | None = None


@dataclass(frozen=True)
class UvmActivity:
    """One node in a sequence's activity tree.

    Nested rather than flat.  A flat node-and-edge list would have to invent
    identity for every node and re-derive nesting to know which branch a step
    belongs to; the statement tree already carries that, so the model keeps it
    and the emitter flattens once, where the flattening is the job.
    """

    #: One of the ``ACT_*`` constants.
    kind: str = ACT_ACTION
    #: What to write in the node: a handle name, a loop's controlling
    #: expression, a delay, a branch label.
    label: str = ""
    #: For :data:`ACT_SEQUENCE` and :data:`ACT_ITEM`, the type being run ---
    #: which is what makes a sub-sequence node a cross-reference.
    type_name: str = ""
    #: For :data:`ACT_FORK`, one of the ``JOIN_*`` constants.
    join: str = ""
    #: Name of the macro this node was recovered from, when it came from one.
    #: Kept because a reader looking for ``start_item`` in the source will find
    #: `` `uvm_do `` instead, and the diagram should say so.
    macro: str = ""
    #: Branches of a decision or fork; the body of a loop.
    children: tuple["UvmActivity", ...] = ()
    location: SourceRef | None = None

    def walk(self) -> "Iterator[UvmActivity]":
        """This node and every node beneath it, in source order."""
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class UvmSequence:
    """One sequence's ``body()``, as an activity tree.

    ``other`` is not bookkeeping.  A ``body()`` is mostly *not* control flow ---
    reporting, assignment, randomization --- and a diagram that silently drew
    only the four constructs it understands would be claiming the task is four
    steps long.  Counting the rest is what makes the claim honest, and it is the
    same rule the schematic applies to library ports.
    """

    #: The sequence class asked for.
    name: str = ""
    #: Its base chain, outermost first, for classification and display.
    chain: tuple[str, ...] = ()
    #: Top-level activity nodes, in source order.
    body: tuple[UvmActivity, ...] = ()
    #: Class the ``body()`` that was read is declared on.  Usually *name*; a
    #: sequence may legitimately inherit a real body from a user base class.
    declared_by: str = ""
    #: False when the only ``body()`` in the chain is the library's empty one.
    overridden: bool = False
    #: Statements in ``body()`` that are not activity nodes.
    other: int = 0
    #: Macros whose expansion was collapsed, by name, in first-seen order.
    macros: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.body

    def walk(self) -> "Iterator[UvmActivity]":
        for node in self.body:
            yield from node.walk()

    def subsequences(self) -> list[str]:
        """Sub-sequence type names, deduplicated, in first-seen order."""
        found: list[str] = []
        for node in self.walk():
            if node.kind == ACT_SEQUENCE and node.type_name:
                if node.type_name not in found:
                    found.append(node.type_name)
        return found


@dataclass(frozen=True)
class UvmChild:
    """One component-creation *site* as written inside a ``build_phase``.

    A site is a line of source, not a runtime component: a create inside a loop
    is written once and would build many, so it is reported once with a
    multiplicity.
    """

    #: Handle assigned to (``agt_a``), or ``""`` when the site has no LHS.
    handle: str = ""
    #: Instance name string passed to the factory, or ``None`` when it is
    #: computed (``$sformatf(...)``) and therefore not knowable statically.
    inst_name: str | None = None
    #: Type being created (``my_agent``); for an unresolved node this is the
    #: *declared* type recovered from source.
    type_name: str = ""
    #: ``"factory"`` (``type_id::create``) or ``"new"`` (direct construction).
    created_by: str = "factory"
    #: True when the site sits under an ``if``/``case`` and may not run.
    conditional: bool = False
    #: ``"1"`` for a plain site, ``"N"`` for one inside a loop.  Never a
    #: fabricated integer: loop trip counts are not constant-foldable here.
    multiplicity: str = "1"
    #: One of :data:`STATE_OK`, :data:`STATE_OPAQUE`, :data:`STATE_UNRESOLVED`.
    state: str = STATE_OK
    #: :data:`KIND_COMPONENT` or :data:`KIND_PORT`.
    kind: str = KIND_COMPONENT
    location: SourceRef | None = None

    @property
    def label(self) -> str:
        """``agt_a : my_agent``, with the site's caveats appended."""
        name = self.handle or self.inst_name or "?"
        text = f"{name} : {self.type_name}"
        if self.multiplicity != "1":
            text += f"  (x{self.multiplicity})"
        if self.conditional:
            text += "  [conditional]"
        if self.state != STATE_OK:
            text += f"  [{self.state}]"
        return text


@dataclass(frozen=True)
class UvmConfigAccess:
    """One ``uvm_config_db#(T)::set`` or ``::get`` as written in source."""

    #: :data:`ACTION_SET` or :data:`ACTION_GET`.
    action: str = ACTION_SET
    #: The ``T`` of the specialization: ``int``, ``string``, ``cfg_if``.
    type_name: str = ""
    #: Class or module the call is written in (``cfg_agent``, ``cfg_tb_top``).
    owner: str = ""
    #: Method or block it sits in (``build_phase``), or ``""`` in a module.
    method: str = ""
    #: Source text of the ``cntxt`` argument: ``this``, ``null``, a path.
    cntxt: str = ""
    #: ``inst_name`` literal, or ``None`` when it is computed.
    scope: str | None = None
    #: ``field_name`` literal, or ``None`` when it is computed.
    field: str | None = None
    #: For a ``set``, the value expression as written.  For a ``get``, the
    #: variable the value is read into.
    value: str = ""
    #: True when ``T`` is a virtual interface --- the RTL bridge (§8.2), and
    #: the only specialization whose value can name an elaborated instance.
    virtual_interface: bool = False
    #: Elaborated hierarchical path of the value when it *is* an instance
    #: (``cfg_tb_top.u_if``), and ``""`` when it is any other expression.
    #:
    #: Empty is a real answer rather than a failure, and the distinction
    #: matters for exactly one shape: ``set(this, "*", "vif", vif)`` passes a
    #: virtual-interface *handle* on, so there is no RTL instance to name.
    #: Recorded here rather than recovered later because the symbol is in hand
    #: at extraction and gone afterwards.
    value_path: str = ""
    #: True when the access sits under an ``if``/``case`` and may not run.
    conditional: bool = False
    location: SourceRef | None = None

    @property
    def dynamic(self) -> bool:
        """True when the field name is computed and so cannot be paired."""
        return self.field is None

    @property
    def where(self) -> str:
        """``cfg_driver.build_phase``, or just the owner outside a method."""
        return f"{self.owner}.{self.method}" if self.method else self.owner

    @property
    def full_scope(self) -> str:
        """``cntxt`` and ``inst_name`` as UVM would join them, for display."""
        scope = "*" if self.scope is None else self.scope
        if self.cntxt in ("", "null"):
            return scope or "(none)"
        return f"{self.cntxt}.{scope}" if scope else self.cntxt


@dataclass(frozen=True)
class UvmConfigRow:
    """One ``set`` and everything that might read it."""

    access: UvmConfigAccess
    #: ``owner.method`` of every ``get`` whose field could match.
    consumers: tuple[str, ...] = ()
    #: True when no ``get`` with a literal field name could read this.
    orphan: bool = False


def field_matches(left: str | None, right: str | None) -> bool:
    """Could a ``set`` of field *left* be read by a ``get`` of field *right*?

    Glob-aware in **both** directions, because UVM lets either side be a
    pattern: a ``set`` of ``"n_*"`` reaches a ``get`` of ``"n_items"``, and a
    ``get`` of ``"n_*"`` reads a ``set`` of ``"n_items"``.

    A computed field name (``None``) matches nothing.  That is the one place
    this analysis is deliberately *not* maximally conservative, and the reason
    is that the conservative answer is useless: a single ``get`` with a computed
    name could in principle read anything, so pairing against it would clear
    every orphan in the project and the view would never report anything.
    Computed accesses are instead excluded from pairing and **counted**, so a
    reader is told the result is partial rather than shown a clean table that
    quietly is not.
    """
    if left is None or right is None:
        return False
    return fnmatchcase(left, right) or fnmatchcase(right, left)


@dataclass
class UvmConfig:
    """Every configuration-database access in the project, and their pairing.

    Pairing is on the **field name only**.  Scope is reported but takes no part
    in it, because the full scope of a ``set`` is ``{cntxt, ".", inst_name}``
    and ``cntxt``'s hierarchical path is a run-time fact --- ``this`` inside
    ``cfg_agent`` is a different string in every testbench that instantiates it.
    Bringing scope into the match could only ever *narrow* it, and a narrower
    match produces more orphans, so leaving it out is the direction that cannot
    invent a bug that is not there.
    """

    accesses: list[UvmConfigAccess] = field(default_factory=list)

    @property
    def sets(self) -> list[UvmConfigAccess]:
        return [a for a in self.accesses if a.action == ACTION_SET]

    @property
    def gets(self) -> list[UvmConfigAccess]:
        return [a for a in self.accesses if a.action == ACTION_GET]

    @property
    def dynamic(self) -> list[UvmConfigAccess]:
        """Accesses whose field name is computed, and so cannot be paired."""
        return [a for a in self.accesses if a.dynamic]

    def rows(self) -> list[UvmConfigRow]:
        """Every ``set``, with the ``get``s that could read it."""
        gets = self.gets
        rows: list[UvmConfigRow] = []
        for access in self.sets:
            consumers = tuple(
                dict.fromkeys(  # de-duplicate, preserving source order
                    get.where
                    for get in gets
                    if field_matches(access.field, get.field)
                )
            )
            rows.append(
                UvmConfigRow(
                    access=access,
                    consumers=consumers,
                    orphan=not consumers and not access.dynamic,
                )
            )
        return rows

    @property
    def orphan_sets(self) -> list[UvmConfigAccess]:
        """``set``s nothing reads --- the typo'd field name, the silent bug."""
        return [row.access for row in self.rows() if row.orphan]

    @property
    def orphan_gets(self) -> list[UvmConfigAccess]:
        """``get``s nothing writes: the component keeps its default forever."""
        sets = self.sets
        return [
            get
            for get in self.gets
            if not get.dynamic
            and not any(field_matches(s.field, get.field) for s in sets)
        ]


@dataclass(frozen=True)
class UvmOverride:
    """One factory override as written in source.

    Deliberately *not* applied to anything.  The tree reports the type its
    ``create`` call names and carries this alongside as an annotation, because
    every way of resolving it would be a claim about a run: the override may be
    conditional, it may be replaced by a later one, and an inst override matches
    a hierarchical path that does not exist until the simulation elaborates.
    """

    #: Type being replaced.
    original: str = ""
    #: Type replacing it.
    replacement: str = ""
    #: :data:`OVERRIDE_TYPE` or :data:`OVERRIDE_INST`.
    kind: str = OVERRIDE_TYPE
    #: For an inst override, the path pattern as written; ``None`` when that
    #: path is computed.  Always ``""`` for a type override.
    inst_path: str | None = ""
    #: Class or module the call is written in.
    owner: str = ""
    #: Method it sits in, or ``""`` outside one.
    method: str = ""
    #: True when the override sits under an ``if``/``case`` and may not run.
    conditional: bool = False
    #: Names in this override that match no class in the parsed sources.  The
    #: by-name forms take strings, so a typo compiles and silently never
    #: applies; this is the only place that can be noticed.
    unknown: tuple[str, ...] = ()
    location: SourceRef | None = None

    @property
    def where(self) -> str:
        """``ovr_test.build_phase``, or just the owner outside a method."""
        return f"{self.owner}.{self.method}" if self.method else self.owner

    @property
    def label(self) -> str:
        """``→ fast_driver``, with the site's caveats appended."""
        text = f"→ {self.replacement or '?'}"
        if self.kind == OVERRIDE_INST:
            path = "(computed)" if self.inst_path is None else self.inst_path
            text += f" under {path}"
        if self.conditional:
            text += " [conditional]"
        return text


@dataclass
class UvmOverrides:
    """Every factory override in the project."""

    overrides: list[UvmOverride] = field(default_factory=list)

    def for_type(self, type_name: str) -> list[UvmOverride]:
        """Overrides that replace *type_name*.

        Matched on the original type's name only.  An inst override is included
        even though its path may not match the node being annotated: the path
        is a run-time fact, and dropping the annotation would hide a real
        possibility to avoid an uncertain one.
        """
        return [o for o in self.overrides if o.original == type_name]

    @property
    def broken(self) -> list[UvmOverride]:
        """Overrides naming a type that does not exist: the silent typo."""
        return [o for o in self.overrides if o.unknown]

    @property
    def replaced_types(self) -> list[str]:
        """Distinct original type names, in first-seen order."""
        return list(dict.fromkeys(o.original for o in self.overrides if o.original))


@dataclass(frozen=True)
class UvmInterfaceDriver:
    """One RTL instance whose interface port connects to a bound interface.

    "Driver" in the RTL sense --- the module on the other end of the wire ---
    not :class:`uvm_driver`.  The name is unfortunate and it is the one the
    hardware means.
    """

    #: Hierarchical path of the connected instance (``tb_top.u_dut``).
    path: str = ""
    #: Definition name being instantiated (``bridge_dut``), which is what a
    #: cross-reference can point at.
    type_name: str = ""
    #: Port on that instance the interface arrives at (``bus``).
    port: str = ""


@dataclass(frozen=True)
class UvmBinding:
    """One virtual-interface handoff: RTL instance -> ``config_db`` -> component.

    The whole feature exists because this handoff is invisible to every tool
    that looks at one side.  A top module writes an interface instance into the
    database under a string; a component reads it back by that string.  Nothing
    checks that the two strings agree, nothing checks that the interface is
    wired to anything, and both failures show up as a null-handle dereference
    thousands of cycles into a run.
    """

    #: Interface definition name (``bridge_if``), from the specialization's ``T``.
    interface_type: str = ""
    #: Field name the interface is filed under, or ``None`` when computed.
    field: str | None = None
    #: The ``set`` as written.  A plain default rather than a ``field()``
    #: factory because the ``field`` attribute above shadows the name.
    set_access: UvmConfigAccess = UvmConfigAccess()
    #: Elaborated path of the interface instance, or ``""`` when the value was
    #: not an instance.  See :attr:`UvmConfigAccess.value_path`.
    instance_path: str = ""
    #: RTL instances the interface reaches, in declaration order.
    drivers: tuple[UvmInterfaceDriver, ...] = ()
    #: Every ``get`` of a virtual interface whose field could match.
    consumers: tuple[UvmConfigAccess, ...] = ()

    @property
    def resolved(self) -> bool:
        """True when the ``set`` named an elaborated interface instance."""
        return bool(self.instance_path)

    @property
    def instance_name(self) -> str:
        """Just the instance (``u_bus``), for a table that already has scope."""
        return self.instance_path.rsplit(".", 1)[-1] if self.instance_path else ""

    @property
    def orphan(self) -> bool:
        """True when nothing reads this binding: the null-handle bug."""
        return not self.consumers and not self.set_access.dynamic

    @property
    def undriven(self) -> bool:
        """True when the interface resolved but reaches no RTL instance."""
        return self.resolved and not self.drivers


@dataclass
class UvmBridge:
    """Every virtual-interface binding in the project.

    Derived entirely from :class:`UvmConfig` plus a bounded look at the scope
    each interface instance is declared in, so it costs one config scan and no
    hierarchy walk.
    """

    bindings: list[UvmBinding] = field(default_factory=list)

    @property
    def unresolved(self) -> list[UvmBinding]:
        """Bindings whose value is a handle rather than an instance."""
        return [b for b in self.bindings if not b.resolved]

    @property
    def undriven(self) -> list[UvmBinding]:
        return [b for b in self.bindings if b.undriven]

    @property
    def orphans(self) -> list[UvmBinding]:
        return [b for b in self.bindings if b.orphan]


@dataclass
class _Site:
    """A creation site *plus* the pyslang symbol needed to recurse into it.

    Exists purely so the symbol has somewhere to live during the walk without
    ending up in :class:`UvmChild`, which must stay free of pyslang references
    to remain picklable.  :meth:`to_child` is the boundary.
    """

    handle: str = ""
    inst_name: str | None = None
    type_name: str = ""
    created_by: str = BY_FACTORY
    conditional: bool = False
    multiplicity: str = "1"
    state: str = STATE_OK
    kind: str = KIND_COMPONENT
    location: SourceRef | None = None
    symbol: Any = None

    def to_child(self) -> UvmChild:
        return UvmChild(
            handle=self.handle,
            inst_name=self.inst_name,
            type_name=self.type_name,
            created_by=self.created_by,
            conditional=self.conditional,
            multiplicity=self.multiplicity,
            state=self.state,
            kind=self.kind,
            location=self.location,
        )


class _WalkState:
    """Shared budget across one walk.  Mirrors ``structure._WalkState``."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.visited = 0
        self.truncated = False

    def take(self) -> bool:
        """Claim one component, or report exhaustion."""
        if self.visited >= self.budget:
            self.truncated = True
            return False
        self.visited += 1
        return True


class UvmProvider:
    """Holds the live ``Compilation`` and extracts the hierarchy lazily.

    Created during ``build_index`` but **never called there**.  Only a UVM
    directive may call :meth:`get`; :attr:`computed` exists so that contract can
    be asserted by a test rather than merely documented.

    The same pickling constraint as ``StructureProvider`` applies, and for the
    same reason: this object holds a pyslang ``Compilation``, so
    :class:`~sphinx_systemverilog.model.index.SvIndex` drops it in
    ``__getstate__``.
    """

    def __init__(
        self,
        compilation: Any,
        source_manager: Any = None,
        root: str = "",
        blackbox: Iterable[str] | None = None,
        blackbox_bases: Iterable[str] | None = None,
        max_components: int = DEFAULT_MAX_COMPONENTS,
    ) -> None:
        self._compilation = compilation
        self._source_manager = source_manager
        #: Explicit root component type name; empty means auto-detect.
        self._root = root
        self._blackbox = list(blackbox or [])
        # `None` means "unspecified, use the default"; `[]` means "stop at
        # nothing".  The two are genuinely different requests.
        self._blackbox_bases = list(
            DEFAULT_BLACKBOX_BASES if blackbox_bases is None else blackbox_bases
        )
        self._max_components = max_components or DEFAULT_MAX_COMPONENTS
        #: Extracted structures by requested root; ``""`` is the configured one.
        #: A project may hold several testbenches, and a page may document more
        #: than one, so the memo is per root rather than a single slot.
        self._structures: dict[str, UvmStructure] = {}
        #: Number of walks performed; asserted by the lazy-extraction test.
        self.walk_count = 0
        #: One expression scan's results --- ``config_db`` accesses *and*
        #: factory overrides; ``None`` until first asked for.  Separate from
        #: the hierarchy memo because the two are independent walks: a page
        #: with only a config table must not pay for a tree.
        self._calls: _CallSink | None = None
        #: Views onto that scan, memoized so callers can key on identity.
        self._config: UvmConfig | None = None
        self._overrides: UvmOverrides | None = None
        #: Number of expression scans performed; asserted by the laziness
        #: tests.  Named for ``config`` because that is what it was when the
        #: contract was written, and the contract has not changed: overrides
        #: ride the same walk and add no scan of their own.
        self.config_walk_count = 0
        #: Extracted sequence bodies by class name.  Per sequence rather than
        #: one scan, because a page draws one sequence and reading every
        #: ``body()`` in a UVM project would be a walk nobody asked for.
        self._sequences: dict[str, UvmSequence | None] = {}
        #: Number of ``body()`` walks performed; asserted by the same test.
        self.sequence_walk_count = 0
        #: Extracted virtual-interface bindings; ``None`` until first asked for.
        self._bridge: UvmBridge | None = None
        #: Number of bridge scans performed; asserted by the same test.
        self.bridge_walk_count = 0

    @property
    def computed(self) -> bool:
        """True once a hierarchy has actually been extracted."""
        return bool(self._structures)

    @property
    def config_computed(self) -> bool:
        """True once the expression scan has actually run."""
        return self._calls is not None

    def get(self, root: str = "") -> UvmStructure:
        """Return the testbench structure, extracting it on first call.

        *root* overrides ``sv_uvm_root`` for one caller --- a directive naming
        its own root --- without disturbing the memo for any other.
        """
        if root not in self._structures:
            self.walk_count += 1
            self._structures[root] = self._walk(root)
        return self._structures[root]

    def _scanned(self) -> "_CallSink":
        """Run the shared expression scan once, and remember it."""
        if self._calls is None:
            self.config_walk_count += 1
            self._calls = self._scan_calls()
        return self._calls

    def config(self) -> UvmConfig:
        """Every ``config_db`` access in the project, scanned on first call.

        The same object every call, not merely an equal one: callers memoize
        against it.
        """
        if self._config is None:
            self._config = UvmConfig(accesses=self._scanned().accesses)
        return self._config

    def knows(self, name: str) -> bool:
        """True when *name* is a class in the parsed sources.

        Distinct from "appears in the tree", and the distinction is the whole
        point: a class registered with the factory and never instantiated is
        absent from a :class:`UvmStructure` for the same reason a misspelled
        name is. One is a finding about the testbench and the other is a
        mistake in a directive, and only the class index can tell them apart.
        """
        try:
            return (name or "").split("::")[-1] in self._class_index()
        except Exception:
            return False

    def overrides(self) -> UvmOverrides:
        """Every factory override in the project, scanned on first call.

        Shares the ``config_db`` walk, so asking for both costs one scan and
        asking for either costs the same as asking for the other.
        """
        if self._overrides is None:
            self._overrides = UvmOverrides(overrides=self._scanned().overrides)
        return self._overrides

    def bridge(self) -> UvmBridge:
        """Every virtual-interface binding, resolved on first call.

        Built on top of :meth:`config`, so a page showing both pays for one
        scan.  The extra work over that scan is bounded by the number of
        virtual-interface ``set``s, and for each one by the number of instances
        declared beside the interface --- never by the size of the design.
        """
        if self._bridge is None:
            self.bridge_walk_count += 1
            self._bridge = self._scan_bridge()
        return self._bridge

    def sequence(self, name: str) -> UvmSequence | None:
        """Return one sequence's ``body()`` as an activity tree.

        ``None`` when *name* names nothing, or names a class that is not a
        sequence --- those are different mistakes from a sequence with an empty
        body, which returns a :class:`UvmSequence` that says so.
        """
        key = (name or "").strip().split("::")[-1]
        if key not in self._sequences:
            self.sequence_walk_count += 1
            self._sequences[key] = self._walk_sequence(key)
        return self._sequences[key]

    # -- the walk -------------------------------------------------------------

    def _walk(self, requested_root: str = "") -> UvmStructure:
        structure = UvmStructure()
        try:
            classes = self._class_index()
        except Exception:
            return structure

        root_name, origin, candidates = self._resolve_root(requested_root)
        structure.root = root_name
        structure.root_origin = origin
        structure.root_candidates = candidates
        if not root_name or root_name not in classes:
            return structure

        state = _WalkState(self._max_components)
        self._descend(root_name, classes[root_name], classes, structure, state, 0)
        structure.component_count = state.visited
        structure.truncated = state.truncated
        return structure

    # -- symbol discovery -----------------------------------------------------

    def _class_index(self) -> dict[str, Any]:
        """Every named class in the project, by bare name.

        Only used to resolve the *root*, which arrives as a string --- from
        ``sv_uvm_root`` or from a ``run_test`` argument --- and so has no symbol
        attached.  Everywhere else the walk carries type symbols directly, which
        sidesteps name ambiguity entirely.
        """
        found: dict[str, Any] = {}
        for symbol in self._iter_classes():
            name = getattr(symbol, "name", "")
            # First definition wins, so a later same-named class in another
            # package cannot displace one already found.
            if name:
                found.setdefault(name, symbol)
        return found

    def _iter_classes(self) -> Iterable[Any]:
        """Every class in the project, in declaration order, without folding.

        The config scan wants them all --- two same-named classes in different
        packages each hold their own accesses --- while :meth:`_class_index`
        folds them to resolve a root name.  Both read from here so the two can
        never disagree about what "every class" means.
        """
        from pyslang.ast import SymbolKind

        def scan(scope: Any) -> Iterable[Any]:
            try:
                members = list(scope)
            except TypeError:
                return
            for member in members:
                if getattr(member, "kind", None) == SymbolKind.ClassType:
                    yield member

        for unit in self._compilation.getCompilationUnits():
            yield from scan(unit)
        for package in self._compilation.getPackages():
            if getattr(package, "name", "") != "std":
                yield from scan(package)

    def _resolve_root(
        self, requested: str = ""
    ) -> tuple[str, str, tuple[str, ...]]:
        """``(root, origin, candidates)``, in precedence order.

        A directive's own argument beats ``sv_uvm_root``, which beats
        auto-detection --- most specific request wins.
        """
        if requested:
            return requested, "directive", ()
        if self._root:
            return self._root, "config", ()
        candidates = self._run_test_names()
        if not candidates:
            return "", "", ()
        # More than one `run_test` means more than one testbench in the project,
        # which is normal.  Take the first for a default view but report them
        # all, so a directive can say "you probably meant to name one".
        return candidates[0], "run_test", tuple(candidates)

    def _run_test_names(self) -> list[str]:
        """Test names passed to ``run_test(...)`` in any top module."""
        from pyslang.ast import ProceduralBlockKind, SymbolKind

        names: list[str] = []
        try:
            tops = list(self._compilation.getRoot().topInstances)
        except Exception:
            return names

        for top in tops:
            body = getattr(top, "body", None)
            if body is None:
                continue
            try:
                members = list(body)
            except TypeError:
                continue
            for member in members:
                if getattr(member, "kind", None) != SymbolKind.ProceduralBlock:
                    continue
                if getattr(member, "procedureKind", None) not in (
                    ProceduralBlockKind.Initial,
                    ProceduralBlockKind.AlwaysComb,
                ):
                    continue
                for call in _calls_named(getattr(member, "body", None), "run_test"):
                    name = _string_argument(call, 0)
                    if name and name not in names:
                        names.append(name)
        return names

    # -- the descent ----------------------------------------------------------

    def _descend(
        self,
        type_name: str,
        type_symbol: Any,
        classes: dict[str, Any],
        structure: UvmStructure,
        state: "_WalkState",
        depth: int,
    ) -> None:
        """Record what *type_symbol*'s ``build_phase`` builds, then recurse.

        Memoized by type name: a testbench that instantiates two agents of the
        same type describes that type once.  That also terminates cycles, which
        a mutually-recursive ``build_phase`` can legally create.
        """
        if type_name in structure.children:
            return
        if depth >= MAX_DEPTH or not state.take():
            structure.truncated = True
            return

        structure.types.setdefault(type_name, self._describe(type_name, type_symbol))
        structure.connections.setdefault(
            type_name, self._connections_of(type_name, type_symbol)
        )
        sites = self._children_of(type_symbol)
        # The pyslang symbol stays on `_Site` and stops here: what goes into the
        # structure is plain data, which is what makes the structure picklable.
        structure.children[type_name] = [site.to_child() for site in sites]

        for site in sites:
            if site.state != STATE_OK or site.symbol is None:
                continue
            self._descend(
                site.type_name, site.symbol, classes, structure, state, depth + 1
            )

    def _describe(self, type_name: str, type_symbol: Any) -> UvmType:
        chain = base_chain(type_symbol)
        kind, tier = classify(chain)
        return UvmType(
            name=type_name,
            chain=tuple(chain),
            kind=kind,
            tier=tier,
            ports=tuple(self._ports_of(type_symbol)),
            location=resolve_location(
                self._source_manager, getattr(type_symbol, "location", None)
            ),
        )

    def _ports_of(self, type_symbol: Any) -> list[UvmPort]:
        """TLM ports declared by this class and by everything it derives from.

        Inherited ports count.  ``uvm_subscriber`` declares ``analysis_export``
        and a user's coverage collector connects to it without redeclaring
        anything, so a schematic reading only the leaf class would draw an edge
        arriving at a port the diagram says does not exist.
        """
        from pyslang.ast import SymbolKind

        found: list[UvmPort] = []
        seen: set[str] = set()
        current = type_symbol
        for _ in range(MAX_DEPTH):
            if current is None:
                break
            try:
                members = list(current)
            except TypeError:
                break
            for member in members:
                if getattr(member, "kind", None) != SymbolKind.ClassProperty:
                    continue
                name = getattr(member, "name", "")
                if not name or name in seen:
                    continue
                port_type = _class_symbol(getattr(member, "type", None))
                chain = base_chain(port_type)
                if not is_port(chain):
                    continue
                role, link = classify_port(chain)
                seen.add(name)
                found.append(
                    UvmPort(
                        name=name,
                        type_name=_type_name(getattr(member, "type", None)),
                        role=role,
                        link=link,
                        declared_by=getattr(current, "name", ""),
                    )
                )
            current = getattr(current, "baseClass", None)
        return found

    # -- connect_phase --------------------------------------------------------

    def _connections_of(self, type_name: str, type_symbol: Any) -> list[UvmConnection]:
        """Every connection written in this class's ``connect_phase``."""
        from pyslang.ast import SymbolKind

        try:
            members = list(type_symbol)
        except TypeError:
            return []

        found: list[UvmConnection] = []
        for member in members:
            if getattr(member, "kind", None) != SymbolKind.Subroutine:
                continue
            if getattr(member, "name", "") != CONNECT_PHASE:
                continue
            self._collect_connections(
                getattr(member, "body", None), found, type_name, conditional=False
            )
        return found

    def _collect_connections(
        self, stmt: Any, out: list[UvmConnection], owner: str,
        conditional: bool, depth: int = 0,
    ) -> None:
        """Walk statements for ``connect`` calls and handle assignments.

        Statement-level rather than expression-level, unlike the ``config_db``
        scan: a connection is a whole statement in every idiom UVM has, so there
        is no equivalent of the ``if (!...get(...))`` problem to solve here.
        The conditional context is still carried down, because an agent that
        wires its driver only ``if (is_active)`` really may not wire it.
        """
        from pyslang.ast import StatementKind

        if stmt is None or depth > 64:
            return
        kind = getattr(stmt, "kind", None)

        if kind == StatementKind.ExpressionStatement:
            connection = self._connection(
                getattr(stmt, "expr", None), owner, conditional
            )
            if connection is not None:
                out.append(connection)
            return

        if kind == StatementKind.Conditional:
            for branch in ("ifTrue", "ifFalse"):
                self._collect_connections(
                    getattr(stmt, branch, None), out, owner, True, depth + 1
                )
            return

        if kind == StatementKind.Case:
            for item in _case_bodies(stmt):
                self._collect_connections(item, out, owner, True, depth + 1)
            return

        if kind in _loop_kinds():
            self._collect_connections(
                getattr(stmt, "body", None), out, owner, conditional, depth + 1
            )
            return

        for attr in ("list", "body", "statements"):
            value = getattr(stmt, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._collect_connections(
                        item, out, owner, conditional, depth + 1
                    )
            elif value is not None and hasattr(value, "kind"):
                self._collect_connections(value, out, owner, conditional, depth + 1)

    def _connection(
        self, expr: Any, owner: str, conditional: bool
    ) -> UvmConnection | None:
        from pyslang.ast import ExpressionKind

        expr = _unwrap(expr)
        kind = getattr(expr, "kind", None)

        if kind == ExpressionKind.Call:
            if not _is_port_connect(expr):
                return None
            source = _endpoint(getattr(expr, "thisClass", None))
            target = _endpoint(_argument(expr, 0))
            if source is None or target is None:
                return None
            return UvmConnection(
                owner=owner,
                source=source,
                target=target,
                kind=_link_kind(source, target),
                conditional=conditional,
                location=_location_of(self._source_manager, expr),
            )

        if kind == ExpressionKind.Assignment:
            source = _endpoint(getattr(expr, "left", None))
            target = _endpoint(getattr(expr, "right", None))
            # Both ends must be *components*, which is what separates wiring a
            # virtual sequencer from the ordinary assignments any method makes.
            if source is None or target is None or source.port or target.port:
                return None
            if not (source.component and target.component):
                return None
            return UvmConnection(
                owner=owner,
                source=source,
                target=target,
                kind=LINK_HANDLE,
                conditional=conditional,
                location=_location_of(self._source_manager, expr),
            )
        return None

    # -- body() ---------------------------------------------------------------

    def _walk_sequence(self, name: str) -> UvmSequence | None:
        try:
            classes = self._class_index()
        except Exception:
            return None
        symbol = classes.get(name)
        if symbol is None:
            return None
        chain = base_chain(_class_symbol(symbol))
        if not is_sequence(chain):
            return None

        subroutine, declared_by = self._body_subroutine(symbol)
        overridden = bool(subroutine) and not declared_by.startswith(_LIBRARY_PREFIX)
        state = _ActivityState()
        body: list[UvmActivity] = []
        if overridden:
            body = self._activity_list(
                _statements(getattr(subroutine, "body", None)), state, 0
            )
        return UvmSequence(
            name=name,
            chain=tuple(chain),
            body=tuple(body),
            declared_by=declared_by,
            overridden=overridden,
            other=state.other,
            macros=tuple(state.macros),
        )

    def _body_subroutine(self, symbol: Any) -> tuple[Any, str]:
        """The nearest ``body()`` in the chain, and the class declaring it.

        Walked rather than looked up on the class itself, because a sequence
        that does not override ``body()`` still *has* one --- the library's
        empty stub --- and the two cases have to be told apart to say "this
        sequence does not define a body" instead of drawing an empty diagram.
        """
        from pyslang.ast import SymbolKind

        current = symbol
        for _ in range(MAX_DEPTH):
            if current is None:
                break
            try:
                members = list(current)
            except TypeError:
                members = []
            for member in members:
                if getattr(member, "kind", None) != SymbolKind.Subroutine:
                    continue
                if getattr(member, "name", "") == SEQUENCE_BODY:
                    return member, getattr(current, "name", "") or ""
            current = _class_symbol(getattr(current, "baseClass", None))
        return None, ""

    def _activity_list(
        self, statements: list, state: "_ActivityState", depth: int,
        macro: str = "",
    ) -> list[UvmActivity]:
        """Walk one statement list, collapsing macro expansions on the way.

        Consecutive statements that came from the same macro invocation are one
        line of source and become one node.  Grouping by *invocation* rather
        than by macro name matters: two adjacent `` `uvm_do `` calls are two
        transactions, and merging them would silently halve the diagram.
        """
        if depth > 32:
            return []
        out: list[UvmActivity] = []
        groups: list[tuple[Any, list]] = []
        for stmt in statements:
            key = None if macro else _macro_key(self._source_manager, stmt)
            if key is not None and groups and groups[-1][0] == key:
                groups[-1][1].append(stmt)
            else:
                groups.append((key, [stmt]))

        for key, group in groups:
            if key is None:
                for stmt in group:
                    out.extend(self._activity(stmt, state, depth, macro))
                continue
            node = self._macro_node(key[0], group, state, depth)
            if node is None:
                # One line of source that produced nothing worth drawing ---
                # `uvm_info` and its relatives.  Counted once, not once per
                # statement it happens to expand to.
                state.other += 1
                continue
            out.append(node)
            # Recorded only when the macro actually produced a node, because
            # the name is reported to the reader as a label they will look for
            # in the diagram.  It is also the *innermost* macro, which for
            # `` `uvm_info `` is UVM's internal ``uvm_report_begin`` --- a name
            # the user never wrote and would not recognize.  Nothing that draws
            # nothing is named.
            if key[0] not in state.macros:
                state.macros.append(key[0])
        return out

    def _macro_node(
        self, name: str, group: list, state: "_ActivityState", depth: int
    ) -> UvmActivity | None:
        """Collapse one macro invocation to the single node it means.

        The expansion is walked into a *throwaway* state so its internals never
        reach the ``other`` count, then searched for the one node that carries
        meaning.  Library-typed candidates lose to user-typed ones, which is
        what picks ``SEQ_OR_ITEM`` over the ``uvm_sequence_base __seq`` local
        that real `` `uvm_do `` declares alongside it.
        """
        inner = _ActivityState(types=dict(state.types))
        produced: list[UvmActivity] = []
        for stmt in group:
            produced.extend(self._activity(stmt, inner, depth, macro=name))
        state.types.update(inner.types)

        candidates = [
            node
            for root in produced
            for node in root.walk()
            if node.kind in (ACT_SEQUENCE, ACT_ITEM)
        ]
        if not candidates:
            return None
        for node in candidates:
            if not node.type_name.startswith(_LIBRARY_PREFIX):
                return node
        return candidates[0]

    def _activity(
        self, stmt: Any, state: "_ActivityState", depth: int, macro: str = ""
    ) -> list[UvmActivity]:
        from pyslang.ast import StatementKind

        if stmt is None or depth > 32:
            return []
        kind = getattr(stmt, "kind", None)

        if kind == StatementKind.List:
            return self._activity_list(_statements(stmt), state, depth, macro)

        if kind == StatementKind.Block:
            return self._block(stmt, state, depth, macro)

        if kind == StatementKind.Conditional:
            return [self._decision(stmt, state, depth, macro)]

        if kind == StatementKind.Case:
            return [self._case(stmt, state, depth, macro)]

        if kind in _loop_kinds():
            return [self._loop(stmt, state, depth, macro)]

        if kind == StatementKind.Timed:
            timing = getattr(stmt, "timing", None)
            text = _expression_text(getattr(timing, "expr", None))
            node = UvmActivity(
                kind=ACT_DELAY, label=f"#{text}" if text else "#",
                macro=macro, location=_location_of(self._source_manager, stmt),
            )
            # `#10 foo();` is a delay *and* a statement.  Both are drawn.
            return [node, *self._activity(
                getattr(stmt, "stmt", None), state, depth + 1, macro
            )]

        if kind == StatementKind.DisableFork:
            return [UvmActivity(
                kind=ACT_ACTION, label="disable fork", macro=macro,
                location=_location_of(self._source_manager, stmt),
            )]

        if kind == StatementKind.ExpressionStatement:
            return self._activity_expression(
                getattr(stmt, "expr", None), state, macro
            )

        if kind in _absorbed_statement_kinds():
            # Declarations and `;` are not steps and are not omissions either.
            return []

        state.other += 1
        return []

    def _block(
        self, stmt: Any, state: "_ActivityState", depth: int, macro: str
    ) -> list[UvmActivity]:
        from pyslang.ast import StatementBlockKind

        block_kind = getattr(stmt, "blockKind", None)
        joins = {
            StatementBlockKind.JoinAll: JOIN_ALL,
            StatementBlockKind.JoinAny: JOIN_ANY,
            StatementBlockKind.JoinNone: JOIN_NONE,
        }
        join = joins.get(block_kind)
        body = getattr(stmt, "body", None)
        if join is None:
            # A plain `begin ... end`, named or not, is a scoping device rather
            # than a step; it is walked through without drawing a box.
            return self._activity(body, state, depth + 1, macro)

        branches = []
        for position, item in enumerate(_statements(body), start=1):
            branches.append(UvmActivity(
                kind=ACT_BRANCH,
                label=_block_name(item) or f"branch {position}",
                children=tuple(self._activity(item, state, depth + 1, macro)),
                location=_location_of(self._source_manager, item),
            ))
        return [UvmActivity(
            kind=ACT_FORK, label="fork", join=join, macro=macro,
            children=tuple(branches),
            location=_location_of(self._source_manager, stmt),
        )]

    def _decision(
        self, stmt: Any, state: "_ActivityState", depth: int, macro: str
    ) -> UvmActivity:
        branches = []
        for attr, label in (("ifTrue", "yes"), ("ifFalse", "no")):
            branch = getattr(stmt, attr, None)
            if branch is None:
                continue
            branches.append(UvmActivity(
                kind=ACT_BRANCH, label=label,
                children=tuple(self._activity(branch, state, depth + 1, macro)),
                location=_location_of(self._source_manager, branch),
            ))
        return UvmActivity(
            kind=ACT_DECISION, label=_condition_text(stmt), macro=macro,
            children=tuple(branches),
            location=_location_of(self._source_manager, stmt),
        )

    def _case(
        self, stmt: Any, state: "_ActivityState", depth: int, macro: str
    ) -> UvmActivity:
        branches = []
        for label, body in _case_arms(stmt):
            branches.append(UvmActivity(
                kind=ACT_BRANCH, label=label,
                children=tuple(self._activity(body, state, depth + 1, macro)),
                location=_location_of(self._source_manager, body),
            ))
        return UvmActivity(
            kind=ACT_DECISION, label=_expression_text(getattr(stmt, "expr", None)),
            macro=macro, children=tuple(branches),
            location=_location_of(self._source_manager, stmt),
        )

    def _loop(
        self, stmt: Any, state: "_ActivityState", depth: int, macro: str
    ) -> UvmActivity:
        name = str(getattr(stmt, "kind", "")).rsplit(".", 1)[-1]
        label, attr = "loop", ""
        for candidate, text, control in _LOOP_LABELS:
            if candidate == name:
                label, attr = text, control
                break
        control_text = _expression_text(getattr(stmt, attr, None)) if attr else ""
        if control_text:
            label = f"{label} ({control_text})"
        return UvmActivity(
            kind=ACT_LOOP, label=label, macro=macro,
            children=tuple(self._activity(
                getattr(stmt, "body", None), state, depth + 1, macro
            )),
            location=_location_of(self._source_manager, stmt),
        )

    def _activity_expression(
        self, expr: Any, state: "_ActivityState", macro: str
    ) -> list[UvmActivity]:
        from pyslang.ast import ExpressionKind

        expr = _unwrap(expr)
        kind = getattr(expr, "kind", None)

        if kind == ExpressionKind.Assignment:
            # A create is not a step; it establishes what a handle holds, which
            # is what lets the *start* node name a type more precise than the
            # handle's declaration.
            handle = _handle_name(getattr(expr, "left", None))
            value = _unwrap(getattr(expr, "right", None))
            type_name = registry_type_name(value) if value is not None else None
            if type_name is None and getattr(value, "kind", None) == \
                    ExpressionKind.NewClass:
                type_name = _type_name(getattr(value, "type", None))
            if handle and type_name:
                state.types[handle] = type_name
                return []
            state.other += 1
            return []

        if kind != ExpressionKind.Call:
            state.other += 1
            return []

        owner, method = _subroutine_owner(expr)
        if owner != SEQUENCE_BASE:
            state.other += 1
            return []
        if method in _ABSORBED_METHODS:
            # The back half of a transaction `start_item` already drew.
            return []
        node_kind = _START_METHODS.get(method)
        if node_kind is None:
            state.other += 1
            return []

        target = _unwrap(
            getattr(expr, "thisClass", None) if method == "start"
            else _argument(expr, 0)
        )
        handle = _handle_name(target)
        chain = base_chain(_class_symbol(getattr(target, "type", None)))
        if is_sequence(chain):
            node_kind = ACT_SEQUENCE
        elif is_sequence_item(chain):
            node_kind = ACT_ITEM
        else:
            state.other += 1
            return []
        type_name = state.types.get(handle) or (chain[0] if chain else "")
        return [UvmActivity(
            kind=node_kind, label=handle, type_name=type_name, macro=macro,
            location=_location_of(self._source_manager, expr),
        )]

    def _children_of(self, type_symbol: Any) -> list["_Site"]:
        """Every component this class's ``build_phase`` builds.

        Two sources, and both are needed:

        * **creation sites** in ``build_phase`` --- the ordinary case;
        * **unresolved members**, which do *not* appear as creation sites at
          all.  When a type cannot be resolved, slang discards the whole
          statement that used it, so the create simply is not in the AST.  A
          walk that only reads ``build_phase`` therefore reports a shortened
          tree that looks complete.  Scanning the class's own properties for
          the ``<error>`` type is what recovers those nodes.
        """
        sites = self._creation_sites(type_symbol)
        built = {site.handle for site in sites if site.handle}
        return sites + self._unresolved_members(type_symbol, built)

    def _creation_sites(self, type_symbol: Any) -> list["_Site"]:
        from pyslang.ast import SymbolKind

        try:
            members = list(type_symbol)
        except TypeError:
            return []

        sites: list[_Site] = []
        for member in members:
            if getattr(member, "kind", None) != SymbolKind.Subroutine:
                continue
            if getattr(member, "name", "") != "build_phase":
                continue
            self._visit_statement(
                getattr(member, "body", None), sites, conditional=False, in_loop=False
            )
        return sites

    def _visit_statement(
        self, stmt: Any, sites: list["_Site"], conditional: bool, in_loop: bool,
        depth: int = 0,
    ) -> None:
        """Walk statements, carrying the conditional/loop context down.

        The context is the point.  A create under an ``if`` is a create that
        *may* happen, and a create in a loop happens an unknown number of times;
        reporting either as a plain child would be a claim the source does not
        make.
        """
        from pyslang.ast import StatementKind

        if stmt is None or depth > 64:
            return
        kind = getattr(stmt, "kind", None)

        if kind == StatementKind.ExpressionStatement:
            site = self._site_from_expression(
                getattr(stmt, "expr", None), conditional, in_loop
            )
            if site is not None:
                sites.append(site)
            return

        if kind == StatementKind.Conditional:
            for branch in ("ifTrue", "ifFalse"):
                self._visit_statement(
                    getattr(stmt, branch, None), sites, True, in_loop, depth + 1
                )
            return

        if kind in _loop_kinds():
            self._visit_statement(
                getattr(stmt, "body", None), sites, conditional, True, depth + 1
            )
            return

        if kind == StatementKind.Case:
            # Every arm is conditional, including the default: reaching it
            # depends on a value the walk cannot know.
            for item in _case_bodies(stmt):
                self._visit_statement(item, sites, True, in_loop, depth + 1)
            return

        for attr in ("list", "body", "statements"):
            value = getattr(stmt, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._visit_statement(
                        item, sites, conditional, in_loop, depth + 1
                    )
            elif value is not None and hasattr(value, "kind"):
                self._visit_statement(value, sites, conditional, in_loop, depth + 1)

    def _site_from_expression(
        self, expr: Any, conditional: bool, in_loop: bool
    ) -> "_Site | None":
        from pyslang.ast import ExpressionKind

        if expr is None:
            return None

        handle = ""
        value = expr
        if getattr(expr, "kind", None) == ExpressionKind.Assignment:
            handle = _handle_name(getattr(expr, "left", None))
            value = getattr(expr, "right", None)
        value = _unwrap(value)
        if value is None:
            return None

        kind = getattr(value, "kind", None)
        if kind == ExpressionKind.Call:
            type_name = registry_type_name(value)
            if type_name is None:
                return None
            symbol = _registry_type_symbol(value)
            inst_name = _string_argument(value, 0)
            created_by = BY_FACTORY
        elif kind == ExpressionKind.NewClass:
            symbol = getattr(value, "type", None)
            type_name = _type_name(symbol)
            if not type_name:
                return None
            # The arguments hang off the constructor call, not off `new` itself.
            inst_name = _string_argument(getattr(value, "constructorCall", None), 0)
            created_by = BY_NEW
        else:
            return None

        chain = base_chain(symbol)
        if not is_component(chain):
            return None

        node_kind, _tier = classify(chain)
        state, symbol = self._boundary(type_name, chain, symbol)
        return _Site(
            handle=handle,
            inst_name=inst_name,
            type_name=type_name,
            created_by=created_by,
            conditional=conditional,
            multiplicity="N" if in_loop else "1",
            state=state,
            kind=node_kind,
            location=_location_of(self._source_manager, value),
            symbol=symbol,
        )

    def _boundary(
        self, type_name: str, chain: list[str], symbol: Any
    ) -> tuple[str, Any]:
        """Decide whether the walk stops at this type.

        Returns ``(state, symbol)`` where a ``None`` symbol means "do not
        descend".  The node itself is always kept: a boundary is a statement
        about how far the tool looked, not about what exists.
        """
        bare = type_name.split("#", 1)[0]

        if any(fnmatchcase(bare, pattern) for pattern in self._blackbox):
            return STATE_OPAQUE, None
        if any(base in chain for base in self._blackbox_bases):
            return STATE_OPAQUE, None
        # Always-on library stop.  `chain[0]` is the type itself: deriving from
        # a `uvm_` base is normal and must not make a user's component opaque.
        if bare.startswith(_LIBRARY_PREFIX):
            return STATE_OPAQUE, None
        return STATE_OK, symbol

    def _unresolved_members(
        self, type_symbol: Any, built: set[str]
    ) -> list["_Site"]:
        """Class properties whose type did not resolve.

        These never reach ``build_phase``: slang discards a statement built on
        an unknown type, so the create disappears from the AST while the
        declaration survives with an ``<error>`` type.  Recovering the declared
        type name needs one CST hop --- the member's own syntax node is just the
        declarator (``ral``), and the type sits on its parent data-declaration.
        """
        from pyslang.ast import SymbolKind

        try:
            members = list(type_symbol)
        except TypeError:
            return []

        found: list[_Site] = []
        for member in members:
            if getattr(member, "kind", None) != SymbolKind.ClassProperty:
                continue
            name = getattr(member, "name", "")
            if not name or name in built:
                continue
            if str(getattr(member, "type", "")) != _ERROR_TYPE:
                continue
            found.append(
                _Site(
                    handle=name,
                    inst_name=None,
                    type_name=_declared_type_text(member) or "<unknown>",
                    created_by="",
                    state=STATE_UNRESOLVED,
                    location=resolve_location(
                        self._source_manager, getattr(member, "location", None)
                    ),
                    symbol=None,
                )
            )
        return found

    # -- the call scan --------------------------------------------------------

    def _scan_calls(self) -> "_CallSink":
        """Every ``config_db`` access and factory override in the project.

        Project-wide rather than rooted at a test, and deliberately so on both
        counts: the access that binds a virtual interface is written in a *top
        module* outside any component, and an override is written wherever the
        author felt like writing it --- usually a test, sometimes a top module,
        never in the component it affects.

        One walk for both.  Descending into if-conditions and ``void'(...)`` is
        the difficult part and it is identical either way, so a page showing an
        annotated tree and a config table pays for one scan rather than two.
        """
        from pyslang.ast import SymbolKind

        sink = _CallSink()
        try:
            classes = list(self._iter_classes())
        except Exception:
            return sink

        for class_symbol in classes:
            owner = getattr(class_symbol, "name", "")
            # The library configures itself --- `uvm_component::set_config_object`
            # calls `config_db::set`, `uvm_sequencer_base` reads its own knobs.
            # Those are real accesses and they are not this document's subject;
            # reporting them would bury the handful a reader actually wrote.
            # Same rule and same reasoning as the tree's library boundary.
            #
            # Not merely an optimization: against real UVM these are invisible
            # anyway, because slang does not elaborate the bodies of methods
            # nothing calls.  Relying on that would be relying on an accident
            # of elaboration, so the rule is stated here instead.
            if owner.startswith(_LIBRARY_PREFIX):
                continue
            try:
                members = list(class_symbol)
            except TypeError:
                continue
            for member in members:
                if getattr(member, "kind", None) != SymbolKind.Subroutine:
                    continue
                self._collect_config(
                    getattr(member, "body", None),
                    sink,
                    owner,
                    getattr(member, "name", ""),
                )

        for owner, block in self._iter_module_blocks():
            self._collect_config(block, sink, owner, "")

        # Resolved once, at the end, rather than per call: the class index is
        # the same for all of them, and a by-name override that names nothing
        # is the only finding here the compiler cannot make.
        sink.overrides[:] = [
            replace(o, unknown=self._unknown_types(o)) for o in sink.overrides
        ]
        return sink

    def _unknown_types(self, override: UvmOverride) -> tuple[str, ...]:
        """Type names in *override* that match no class in the sources.

        Only the by-name forms can produce one --- a `T::get_type()` argument
        would not have compiled if `T` did not exist. That is exactly why the
        by-name forms are worth reporting: `set_type_override("a", "b")` with a
        typo in either string compiles, elaborates, simulates, and silently
        never applies.
        """
        try:
            known = self._class_index()
        except Exception:
            return ()
        return tuple(
            name for name in (override.original, override.replacement)
            if name and name not in known
        )

    def _iter_module_blocks(self) -> Iterable[tuple[str, Any]]:
        """``(module name, statement)`` for every procedural block in a top."""
        from pyslang.ast import SymbolKind

        try:
            tops = list(self._compilation.getRoot().topInstances)
        except Exception:
            return

        for top in tops:
            body = getattr(top, "body", None)
            if body is None:
                continue
            try:
                members = list(body)
            except TypeError:
                continue
            for member in members:
                if getattr(member, "kind", None) == SymbolKind.ProceduralBlock:
                    yield getattr(top, "name", ""), getattr(member, "body", None)

    def _collect_config(
        self,
        stmt: Any,
        sink: "_CallSink",
        owner: str,
        method: str,
        conditional: bool = False,
        depth: int = 0,
    ) -> None:
        """Walk statements for ``config_db`` calls, tracking conditionality.

        This walk is **expression-level**, not statement-level, and that is the
        whole difficulty.  The dominant way a UVM component reads configuration
        is::

            if (!uvm_config_db #(int)::get(this, "", "n_items", n_items))

        where the call is an ``if``-*condition*: a walker that only inspects
        ``ExpressionStatement`` sees a ``Conditional`` here and nothing at all
        inside it, and so reports every such component as reading nothing.
        Conditions, case selectors and loop bounds are therefore descended into
        alongside statement bodies.
        """
        from pyslang.ast import StatementKind

        if stmt is None or depth > 64:
            return
        kind = getattr(stmt, "kind", None)

        if kind == StatementKind.Conditional:
            # The condition itself runs unconditionally; the branches do not.
            for condition in getattr(stmt, "conditions", []) or []:
                self._config_calls(
                    getattr(condition, "expr", None), sink, owner, method, conditional
                )
            for branch in ("ifTrue", "ifFalse"):
                self._collect_config(
                    getattr(stmt, branch, None), sink, owner, method, True, depth + 1
                )
            return

        if kind == StatementKind.Case:
            self._config_calls(
                getattr(stmt, "expr", None), sink, owner, method, conditional
            )
            for item in _case_bodies(stmt):
                self._collect_config(item, sink, owner, method, True, depth + 1)
            return

        if kind == StatementKind.ExpressionStatement:
            # `void'(...::get(...))` arrives here directly: slang records the
            # void cast on the statement's syntax, not as a Conversion node.
            self._config_calls(
                getattr(stmt, "expr", None), sink, owner, method, conditional
            )
            return

        if kind in _loop_kinds():
            for attr in ("initializers", "stopExpr", "steps"):
                value = getattr(stmt, attr, None)
                for expr in value if isinstance(value, (list, tuple)) else [value]:
                    self._config_calls(expr, sink, owner, method, conditional)
            self._collect_config(
                getattr(stmt, "body", None), sink, owner, method, conditional, depth + 1
            )
            return

        for attr in ("list", "body", "statements", "expr", "initializer"):
            value = getattr(stmt, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._descend_config(
                        item, sink, owner, method, conditional, depth + 1
                    )
            elif value is not None:
                self._descend_config(value, sink, owner, method, conditional, depth + 1)

    def _descend_config(
        self, node: Any, sink: "_CallSink", owner: str, method: str,
        conditional: bool, depth: int,
    ) -> None:
        """Route a child to the statement or the expression walk."""
        from pyslang.ast import ExpressionKind

        kind = getattr(node, "kind", None)
        if isinstance(kind, ExpressionKind):
            self._config_calls(node, sink, owner, method, conditional)
        elif kind is not None:
            self._collect_config(node, sink, owner, method, conditional, depth)

    def _config_calls(
        self, expr: Any, sink: "_CallSink", owner: str, method: str,
        conditional: bool, depth: int = 0,
    ) -> None:
        """Find calls of interest anywhere inside one expression.

        Both a ``config_db`` access and a factory override are "an interesting
        call somewhere in an expression", and finding either is the same walk
        --- the hard part, descending into if-conditions and ``void'(...)``,
        is shared. They are collected in one pass rather than two so a page
        showing a tree with override annotations and a config table pays for
        one scan.
        """
        from pyslang.ast import ExpressionKind

        if expr is None or depth > 32:
            return
        if getattr(expr, "kind", None) == ExpressionKind.Call:
            access = self._config_access(expr, owner, method, conditional)
            if access is not None:
                sink.accesses.append(access)
            else:
                override = self._override(expr, owner, method, conditional)
                if override is not None:
                    sink.overrides.append(override)

        for attr in _EXPRESSION_ATTRS:
            value = getattr(expr, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._config_calls(
                        item, sink, owner, method, conditional, depth + 1
                    )
            elif value is not None and isinstance(
                getattr(value, "kind", None), ExpressionKind
            ):
                self._config_calls(value, sink, owner, method, conditional, depth + 1)

    def _config_access(
        self, call: Any, owner: str, method: str, conditional: bool
    ) -> UvmConfigAccess | None:
        from pyslang.ast import ExpressionKind

        action = config_db_action(call)
        if action is None:
            return None

        value_expr = _unwrap(_argument(call, _ARG_VALUE))
        if getattr(value_expr, "kind", None) == ExpressionKind.Assignment:
            # A `get` writes its result through an `inout` argument, which slang
            # models as an assignment; the variable being filled is on the left.
            value_expr = getattr(value_expr, "left", None)

        type_param = _type_parameter(call, "T")
        return UvmConfigAccess(
            action=action,
            type_name=_type_name(type_param),
            owner=owner,
            method=method,
            cntxt=_expression_text(_argument(call, _ARG_CNTXT)),
            scope=_string_argument(call, _ARG_SCOPE),
            field=_string_argument(call, _ARG_FIELD),
            value=_expression_text(value_expr),
            virtual_interface=bool(getattr(type_param, "isVirtualInterface", False)),
            value_path=_instance_path(getattr(value_expr, "symbol", None)),
            conditional=conditional,
            location=_location_of(self._source_manager, call),
        )

    # -- factory overrides ----------------------------------------------------

    def _override(
        self, call: Any, owner: str, method: str, conditional: bool
    ) -> UvmOverride | None:
        """One factory-override call, or ``None`` if this is not one.

        Discriminated by the *lexical* path, exactly as ``config_db`` and
        ``connect`` are, and for a sharper version of the same reason: there
        are four different declaring classes here (``uvm_component``,
        ``uvm_factory``, and both registries) and two of them declare a method
        with the *same name and a different signature*.
        ``uvm_component::set_type_override`` takes two strings;
        ``uvm_component_registry::set_type_override`` takes one wrapper. Keying
        on the name alone would read one as the other and report the override
        type as the type being overridden.
        """
        subroutine = getattr(call, "subroutine", None)
        parts = (getattr(subroutine, "lexicalPath", "") or "").split("::")
        if len(parts) < 2:
            return None
        signature = _OVERRIDE_SIGNATURES.get((parts[-2], parts[-1]))
        if signature is None:
            return None
        kind, original_arg, override_arg, path_arg = signature

        # The registry forms name no original: it is the specialization's own
        # `Tname`, the same parameter `create` is read from.
        original = (
            _registry_tname(subroutine) if original_arg is None
            else _override_type_name(_argument(call, original_arg))
        )
        replacement = _override_type_name(_argument(call, override_arg))
        if not original or not replacement:
            # Something in this call is not a form the extraction understands.
            # Half an override is worse than none: it would name a type as
            # replaced without saying what by.
            return None

        return UvmOverride(
            original=original,
            replacement=replacement,
            kind=kind,
            inst_path=(
                "" if path_arg is None else _string_argument(call, path_arg)
            ),
            owner=owner,
            method=method,
            conditional=conditional,
            location=_location_of(self._source_manager, call),
        )

    # -- the RTL bridge -------------------------------------------------------

    def _scan_bridge(self) -> UvmBridge:
        """Pair each virtual-interface ``set`` with its RTL and its readers.

        Pairing on the field name, exactly as :meth:`UvmConfig.rows` does and
        for the same reason: a ``set``'s full scope depends on the run-time
        path of its ``cntxt``.  Narrowing by scope could only ever turn real
        bindings into orphans.

        Consumers are restricted to ``get``s of *the same interface type*,
        which is a narrowing the config table cannot make and which the field
        name alone gets wrong.  ``uvm_config_db#(T)`` is keyed on ``T``: a
        ``get`` of ``virtual clk_if`` cannot read a ``set`` of
        ``virtual bus_if``, whatever the field is called.  Unlike scope, that
        is settled statically and certainly, so using it narrows without
        inventing anything --- and ``vif`` is a common enough field name that a
        project holding two testbenches pairs every one of them with every
        other without it.
        """
        config = self.config()
        gets = [get for get in config.gets if get.virtual_interface]

        bindings: list[UvmBinding] = []
        for access in config.sets:
            if not access.virtual_interface:
                continue
            bindings.append(
                UvmBinding(
                    interface_type=access.type_name,
                    field=access.field,
                    set_access=access,
                    instance_path=access.value_path,
                    drivers=self._interface_drivers(access.value_path),
                    consumers=tuple(
                        get for get in gets
                        if get.type_name == access.type_name
                        and field_matches(access.field, get.field)
                    ),
                )
            )
        return UvmBridge(bindings=bindings)

    def _interface_drivers(self, path: str) -> tuple[UvmInterfaceDriver, ...]:
        """RTL instances declared beside *path* that connect to it.

        **Scope, stated:** the instances in the interface's own declaring
        scope, and no others.  An interface passed further down through a port
        is reachable from a deeper module too, and following it would mean
        walking the whole hierarchy for a result that is usually the same one.
        The bound is reported in the rendered view rather than left implicit.
        """
        from pyslang.ast import SymbolKind

        body = self._declaring_scope(path)
        if body is None:
            return ()

        drivers: list[UvmInterfaceDriver] = []
        for member in body:
            if getattr(member, "kind", None) != SymbolKind.Instance:
                continue
            if str(getattr(member, "hierarchicalPath", "")) == path:
                continue
            for port, connected in _interface_connections(member):
                # Compared by hierarchical path rather than by symbol identity:
                # the path is a fact about the elaboration, whereas whether two
                # pyslang wrappers of the same C++ symbol compare equal is a
                # fact about the bindings.
                if connected != path:
                    continue
                drivers.append(
                    UvmInterfaceDriver(
                        path=str(getattr(member, "hierarchicalPath", "")),
                        type_name=str(
                            getattr(getattr(member, "definition", None), "name", "")
                        ),
                        port=str(getattr(port, "name", "")),
                    )
                )
        return tuple(drivers)

    def _declaring_scope(self, path: str) -> Any:
        """The instance body that declares the instance at *path*.

        Walks down the path rather than searching, so the cost is the depth of
        one hierarchical name and not the size of the design --- which is what
        keeps a binding table from paying for the hierarchy walk that
        ``StructureProvider`` exists to defer.
        """
        if not path:
            return None
        parts = path.split(".")
        try:
            tops = list(self._compilation.getRoot().topInstances)
        except Exception:
            return None

        current = next((t for t in tops if getattr(t, "name", "") == parts[0]), None)
        for name in parts[1:-1]:
            if current is None:
                return None
            current = _member_instance(getattr(current, "body", None), name)
        return getattr(current, "body", None) if current is not None else None


# -- pyslang helpers ----------------------------------------------------------
#
# Kept module-level and free of provider state so they can be unit-tested and
# reused by the later phases, which read the same expressions for different
# reasons.


@lru_cache(maxsize=1)
def _loop_kinds() -> tuple:
    """Statement kinds whose body runs an unknown number of times.

    Cached rather than module-level so importing ``model.uvm`` does not import
    pyslang, matching how the rest of ``model`` treats the boundary.
    """
    from pyslang.ast import StatementKind

    return (
        StatementKind.ForLoop,
        StatementKind.ForeachLoop,
        StatementKind.RepeatLoop,
        StatementKind.WhileLoop,
        StatementKind.DoWhileLoop,
        StatementKind.ForeverLoop,
    )


#: Expression attributes the config walk descends through.  A fixed list rather
#: than reflection over ``dir()``: it is what keeps the walk from wandering into
#: type symbols and back out into the whole compilation.
#:
#: Note there is deliberately **no visited-set** guarding this walk.  Identity
#: dedup by ``id()`` is unsafe against pyslang: each attribute access builds a
#: fresh Python wrapper, and once one is collected CPython reuses its address,
#: so an ``id()`` seen before may be a different node entirely.  A first attempt
#: at this walk did exactly that and silently dropped most of the accesses it
#: had already found.  Expression trees are acyclic, so a depth bound is both
#: sufficient and safe.
_EXPRESSION_ATTRS = (
    "left", "right", "operand", "arguments", "expr", "value", "conditions",
    "pred", "elements", "constructorCall", "selector",
)


@lru_cache(maxsize=1)
def _select_kinds() -> tuple:
    from pyslang.ast import ExpressionKind

    return (ExpressionKind.ElementSelect, ExpressionKind.RangeSelect)


@lru_cache(maxsize=1)
def _absorbed_statement_kinds() -> tuple:
    """Statement kinds that are neither an activity node nor an omission.

    A variable declaration is part of writing a task, not part of what the task
    does; counting it as "not shown" would report noise as loss.
    """
    from pyslang.ast import StatementKind

    return (
        StatementKind.VariableDeclaration,
        StatementKind.Empty,
    )


@dataclass
class _ActivityState:
    """Mutable accumulator threaded through one ``body()`` walk."""

    #: Statements that produced no node.
    other: int = 0
    #: Macro names collapsed, in first-seen order.
    macros: list[str] = field(default_factory=list)
    #: Handle name -> type created into it, from factory or ``new``.
    types: dict[str, str] = field(default_factory=dict)


def _statements(stmt: Any) -> list:
    """The child statements of a list or block, or ``[stmt]`` for a leaf."""
    if stmt is None:
        return []
    for attr in ("list", "statements"):
        value = getattr(stmt, attr, None)
        if isinstance(value, (list, tuple)):
            return [item for item in value if hasattr(item, "kind")]
    body = getattr(stmt, "body", None)
    if body is not None and hasattr(body, "kind") and body is not stmt:
        return _statements(body)
    return [stmt]


def _block_name(stmt: Any) -> str:
    """A named block's label (``begin : traffic``), or ``""``.

    Free human-authored branch names: engineers already name fork branches
    descriptively, so the diagram gets its labels out of the source instead of
    numbering them.
    """
    return getattr(getattr(stmt, "blockSymbol", None), "name", "") or ""


def _macro_key(source_manager: Any, stmt: Any) -> tuple[str, str, int] | None:
    """``(macro, file, line)`` when *stmt* came from a macro, else ``None``.

    The line is the *expansion* location --- where the macro was invoked --- so
    two adjacent invocations of the same macro get different keys and stay two
    nodes.  Not ``getFullyOriginalLoc``, which was the first attempt and is
    wrong here: it resolves a token back to where it was *written*, so every
    token of the macro body reports the same line in the macro's own header
    file and both invocations collapse into one.  Only tokens that came from
    the invocation's arguments report the call site, which is why the mistake
    survives a cursory test.
    """
    if source_manager is None:
        return None
    start = getattr(getattr(stmt, "sourceRange", None), "start", None)
    if start is None:
        return None
    try:
        if not source_manager.isMacroLoc(start):
            return None
        name = source_manager.getMacroName(start)
        if not name:
            return None
        origin = start
        for _ in range(MAX_DEPTH):
            if not source_manager.isMacroLoc(origin):
                break
            origin = source_manager.getExpansionLoc(origin)
        return (
            str(name),
            str(source_manager.getFileName(origin)),
            int(source_manager.getLineNumber(origin)),
        )
    except Exception:
        return None


def _subroutine_owner(call: Any) -> tuple[str, str]:
    """``(declaring class, method name)`` for a call, specialization stripped.

    The lexical path is the discriminator, for the same reason it is for
    ``connect``: a testbench is full of methods called ``start``, and only the
    one declared on ``uvm_sequence_base`` runs a sequence.
    """
    subroutine = getattr(call, "subroutine", None)
    name = getattr(subroutine, "name", "") or ""
    parts = (getattr(subroutine, "lexicalPath", "") or "").split("::")
    owner = parts[-2].split("#", 1)[0] if len(parts) >= 2 else ""
    return owner, name


def _condition_text(stmt: Any) -> str:
    """An ``if``'s condition, as written."""
    conditions = getattr(stmt, "conditions", None)
    if not isinstance(conditions, (list, tuple)):
        return ""
    parts = [
        _expression_text(getattr(item, "expr", None)) for item in conditions
    ]
    return " &&& ".join(part for part in parts if part)


def _case_arms(stmt: Any) -> list[tuple[str, Any]]:
    """``(label, body)`` for every arm of a case, including the default.

    Every arm is drawn, the default included: which one runs depends on a value
    the walk cannot know, so presenting any of them as the path would be an
    invention.
    """
    arms: list[tuple[str, Any]] = []
    for item in getattr(stmt, "items", None) or []:
        body = getattr(item, "stmt", None)
        if body is None:
            continue
        labels = [
            _expression_text(expr) for expr in getattr(item, "expressions", None) or []
        ]
        arms.append((", ".join(label for label in labels if label) or "case", body))
    default = getattr(stmt, "defaultCase", None)
    if default is not None:
        arms.append(("default", default))
    return arms


def _location_of(source_manager: Any, node: Any) -> SourceRef | None:
    """Resolve an expression's source range, or a symbol's location."""
    source_range = getattr(node, "sourceRange", None)
    start = getattr(source_range, "start", None)
    return resolve_location(source_manager, start if start is not None else node)


def _unwrap(expr: Any) -> Any:
    """Strip implicit conversions, which wrap almost every real expression."""
    from pyslang.ast import ExpressionKind

    seen = 0
    while expr is not None and seen < 16:
        if getattr(expr, "kind", None) != ExpressionKind.Conversion:
            return expr
        expr = getattr(expr, "operand", None)
        seen += 1
    return expr


def _handle_name(expr: Any) -> str:
    """The variable a create is assigned to: ``agt`` or ``extra[i]`` -> ``extra``."""
    from pyslang.ast import ExpressionKind

    expr = _unwrap(expr)
    for _ in range(8):
        if expr is None:
            return ""
        kind = getattr(expr, "kind", None)
        if kind == ExpressionKind.NamedValue:
            return getattr(getattr(expr, "symbol", None), "name", "") or ""
        if kind == ExpressionKind.MemberAccess:
            return getattr(getattr(expr, "member", None), "name", "") or ""
        if kind in _select_kinds():
            # An array element: the handle is the array itself.
            expr = _unwrap(getattr(expr, "value", None))
            continue
        return ""
    return ""


def _class_symbol(type_symbol: Any) -> Any:
    """The class behind a declared type, following an alias or specialization.

    A member declared ``uvm_analysis_port #(tlm_item) ap`` hands back a type
    whose ``baseClass`` is only reachable through ``canonicalType``; the raw
    symbol resolves the name but not the chain.
    """
    if type_symbol is None:
        return None
    return getattr(type_symbol, "canonicalType", None) or type_symbol


def _is_port_connect(call: Any) -> bool:
    """True for ``<port>.connect(<port>)`` and nothing else.

    Keyed on the *lexical* path of the called subroutine
    (``uvm_pkg::uvm_port_base::connect``), the same discriminator
    :func:`config_db_action` uses and for the same reason: a testbench is full
    of methods called ``connect``, and only the ones declared on
    ``uvm_port_base`` are TLM connections.
    """
    subroutine = getattr(call, "subroutine", None)
    if getattr(subroutine, "name", None) != "connect":
        return False
    parts = (getattr(subroutine, "lexicalPath", "") or "").split("::")
    return len(parts) >= 2 and parts[-2].split("#", 1)[0] == PORT_BASE


def _endpoint(expr: Any) -> UvmEndpoint | None:
    """Resolve a member-access chain to one end of a connection.

    ``agt_a.mon.ap`` becomes ``path=("agt_a", "mon"), port="ap"``.  Whether the
    last element is a port or a component is decided by its *type*, not by its
    name, so ``vseqr.seqr_a`` --- a sequencer handle, not a port --- comes back
    as a three-deep component path and is drawn as one.
    """
    from pyslang.ast import ExpressionKind

    expr = _unwrap(expr)
    if expr is None:
        return None

    names: list[str] = []
    node = expr
    for _ in range(16):
        if node is None:
            break
        kind = getattr(node, "kind", None)
        if kind == ExpressionKind.MemberAccess:
            name = getattr(getattr(node, "member", None), "name", "")
            if not name:
                return None
            names.append(name)
            node = _unwrap(getattr(node, "value", None))
            continue
        if kind == ExpressionKind.NamedValue:
            name = getattr(getattr(node, "symbol", None), "name", "")
            if name:
                names.append(name)
            break
        # `this`, a hierarchical reference, a call: stop and keep what resolved.
        break

    names.reverse()
    if names and names[0] == "this":
        # `this.ap.connect(...)` is the same endpoint as `ap.connect(...)`.
        names = names[1:]
    if not names:
        return None

    chain = base_chain(_class_symbol(getattr(expr, "type", None)))
    type_name = _type_name(getattr(expr, "type", None))
    if is_port(chain):
        # Only the link kind is wanted here; the role belongs to the port's
        # inventory entry, where a diagram reads it once per port rather than
        # once per edge.
        _role, link = classify_port(chain)
        return UvmEndpoint(
            path=tuple(names[:-1]), port=names[-1], type_name=type_name, link=link
        )
    return UvmEndpoint(
        path=tuple(names),
        type_name=type_name,
        component=is_component(chain),
    )


def _link_kind(source: UvmEndpoint, target: UvmEndpoint) -> str:
    """What flows along a connection, preferring whichever end knows.

    The two ends agree in every well-typed testbench.  When they do not ---
    which happens against the test stub, whose ``connect`` is typed against the
    common base so fixtures stay writable --- the source is the one that was
    written first and is taken as authoritative.
    """
    if source.link != LINK_TLM:
        return source.link
    return target.link


def _argument(call: Any, position: int) -> Any:
    """The *position*-th argument of a call, or ``None``."""
    try:
        arguments = list(getattr(call, "arguments", []) or [])
    except TypeError:
        return None
    return arguments[position] if position < len(arguments) else None


def _string_argument(call: Any, position: int) -> str | None:
    """A call argument's literal string value, or ``None`` if it is computed.

    ``None`` is a real answer, not a failure: ``$sformatf("agt_%0d", i)``
    produces a name that does not exist until the simulation runs, and
    inventing one would be a claim the source does not make.
    """
    from pyslang.ast import ExpressionKind

    argument = _unwrap(_argument(call, position))
    if getattr(argument, "kind", None) != ExpressionKind.StringLiteral:
        return None
    value = getattr(argument, "value", None)
    return str(value) if value is not None else None


@dataclass
class _CallSink:
    """What one pass of the expression walk collects.

    Exists so the walk threads a single parameter rather than one list per
    kind of finding, which is what keeps adding a third finding a change to
    the leaf and not to every method in the walk.
    """

    accesses: list[UvmConfigAccess] = field(default_factory=list)
    overrides: list[UvmOverride] = field(default_factory=list)


def _registry_tname(subroutine: Any) -> str | None:
    """The ``Tname`` of the registry specialization *subroutine* belongs to.

    The generalization of :func:`registry_type_name`, which asks the same
    question only of ``create``.  A registry-form override
    (``my_drv::type_id::set_type_override(...)``) names the type it replaces
    nowhere in its arguments --- it is the specialization itself.
    """
    scope = getattr(subroutine, "parentScope", None)
    if scope is None:
        return None
    try:
        members = list(scope)
    except TypeError:
        return None
    for member in members:
        if getattr(member, "name", "") != "Tname":
            continue
        value = getattr(member, "value", None)
        if value is None:
            return None
        return str(value).strip('"') or None
    return None


def _override_type_name(expr: Any) -> str | None:
    """The type named by a factory-override argument, in either form.

    Two spellings mean the same thing and neither is reducible to the other:

    * ``"fast_driver"`` --- a string literal, which is what the by-name forms
      take and what makes a typo in one invisible;
    * ``fast_driver::get_type()`` --- a call, whose *lexical path* names the
      class the ``uvm_*_utils`` macro expanded ``get_type`` into.

    The return type of that call is the ``type_id`` typedef, so reading it
    would give ``fast_driver::type_id`` rather than ``fast_driver``. The
    lexical path is the shorter and more direct answer.
    """
    from pyslang.ast import ExpressionKind

    expr = _unwrap(expr)
    kind = getattr(expr, "kind", None)
    if kind == ExpressionKind.StringLiteral:
        value = getattr(expr, "value", None)
        return str(value) if value else None
    if kind == ExpressionKind.Call:
        subroutine = getattr(expr, "subroutine", None)
        parts = (getattr(subroutine, "lexicalPath", "") or "").split("::")
        if len(parts) >= 2 and parts[-1] == _GET_TYPE:
            return parts[-2]
    return None


def _instance_path(symbol: Any) -> str:
    """Elaborated hierarchical path of *symbol*, if it is an instance at all.

    The one route from a ``config_db`` value back to RTL.  slang models an
    interface instance passed as an argument as an ``ArbitrarySymbolExpression``
    --- a node with no syntax of its own --- whose symbol carries the path the
    elaboration gave it.  Anything else (a variable, a literal, a call) is not
    an instance and yields ``""``.
    """
    from pyslang.ast import SymbolKind

    if getattr(symbol, "kind", None) != SymbolKind.Instance:
        return ""
    return str(getattr(symbol, "hierarchicalPath", "") or "")


def _member_instance(scope: Any, name: str) -> Any:
    """The instance named *name* directly inside *scope*, or ``None``."""
    from pyslang.ast import SymbolKind

    if scope is None:
        return None
    for member in scope:
        if (
            getattr(member, "kind", None) == SymbolKind.Instance
            and getattr(member, "name", "") == name
        ):
            return member
    return None


def _interface_connections(instance: Any) -> list[tuple[Any, str]]:
    """``(port, connected instance path)`` for each interface port of *instance*.

    A modport connection (``.bus(u_if.mon_mp)``) resolves to the interface
    *instance*, not to the modport, which is why one rule covers both forms.
    """
    from pyslang.ast import SymbolKind

    out: list[tuple[Any, str]] = []
    try:
        connections = list(getattr(instance, "portConnections", []) or [])
    except TypeError:
        return out

    for connection in connections:
        port = getattr(connection, "port", None)
        if getattr(port, "kind", None) != SymbolKind.InterfacePort:
            continue
        symbol = getattr(getattr(connection, "expression", None), "symbol", None)
        path = _instance_path(symbol)
        if path:
            out.append((port, path))
    return out


def _expression_text(expr: Any) -> str:
    """An expression as written in source, for display in a table.

    Falls back to a referenced symbol's name, which is what carries the answer
    for an ``ArbitrarySymbol`` --- how an RTL interface instance is passed to
    ``config_db::set`` --- because that node has no syntax of its own.
    """
    expr = _unwrap(expr)
    if expr is None:
        return ""
    syntax = getattr(expr, "syntax", None)
    if syntax is not None:
        text = " ".join(str(syntax).split())
        if text:
            return text
    return getattr(getattr(expr, "symbol", None), "name", "") or ""


def config_db_action(call: Any) -> str | None:
    """:data:`ACTION_SET`/:data:`ACTION_GET` for a ``config_db`` call, else ``None``.

    Identified by the subroutine's *lexical* path
    (``mini_uvm_pkg::uvm_config_db::set``) rather than by its name alone.  A
    testbench is full of methods called ``set`` and ``get``; the lexical path
    names the declaring class without the specialization parameters, so one
    comparison covers every ``uvm_config_db#(T)`` at once.
    """
    subroutine = getattr(call, "subroutine", None)
    action = getattr(subroutine, "name", None)
    if action not in (ACTION_SET, ACTION_GET):
        return None
    parts = (getattr(subroutine, "lexicalPath", "") or "").split("::")
    if len(parts) < 2 or parts[-2] not in CONFIG_DB_CLASSES:
        return None
    return action


def _type_parameter(call: Any, name: str) -> Any:
    """The type bound to parameter *name* on the called subroutine's class.

    The generic form of the trick :func:`registry_type_name` documents: a call
    into a parameterized class reaches its specialization through
    ``subroutine.parentScope``, and the bound types are ``TypeParameter``
    members of it.  ``uvm_component_registry#(T, Tname)`` and
    ``uvm_config_db#(T)`` are both read this way.
    """
    from pyslang.ast import SymbolKind

    subroutine = getattr(call, "subroutine", None)
    scope = getattr(subroutine, "parentScope", None)
    if scope is None:
        return None
    try:
        members = list(scope)
    except TypeError:
        return None
    for member in members:
        if getattr(member, "kind", None) != SymbolKind.TypeParameter:
            continue
        if getattr(member, "name", "") != name:
            continue
        return getattr(getattr(member, "targetType", None), "type", None)
    return None


def _registry_type_symbol(call: Any) -> Any:
    """The ``ClassType`` a ``type_id::create`` builds, via the registry's ``T``.

    Complements :func:`registry_type_name`: the name is what a reader sees, but
    the *symbol* is what the walk recurses into, and taking it from the
    specialization avoids resolving the name a second time --- which could pick
    a different class of the same name in another package.
    """
    return _type_parameter(call, "T")


def _declared_type_text(member: Any) -> str:
    """Recover a member's declared type name from the CST.

    Needed only for unresolved members, where the elaborated type is ``<error>``
    and so says nothing.  The member's own syntax node is just the declarator
    (``ral``); the type lives one hop up on the data-declaration that owns it.
    """
    syntax = getattr(member, "syntax", None)
    parent = getattr(syntax, "parent", None)
    declared = getattr(parent, "type", None)
    if declared is None:
        return ""
    return str(declared).strip()


def _case_bodies(stmt: Any) -> list:
    """Every arm of a case statement, including the default."""
    bodies = []
    for item in getattr(stmt, "items", []) or []:
        body = getattr(item, "stmt", None) or getattr(item, "statement", None)
        if body is not None:
            bodies.append(body)
    default = getattr(stmt, "defaultCase", None)
    if default is not None:
        bodies.append(default)
    return bodies


def _calls_named(stmt: Any, name: str, depth: int = 0) -> list:
    """Every call to a subroutine called *name* anywhere under *stmt*."""
    from pyslang.ast import ExpressionKind

    found: list = []
    if stmt is None or depth > 32:
        return found

    expr = getattr(stmt, "expr", None)
    expr = _unwrap(expr) if expr is not None else None
    if expr is not None and getattr(expr, "kind", None) == ExpressionKind.Call:
        if getattr(getattr(expr, "subroutine", None), "name", None) == name:
            found.append(expr)

    for attr in ("list", "body", "statements", "ifTrue", "ifFalse"):
        value = getattr(stmt, attr, None)
        if isinstance(value, (list, tuple)):
            for item in value:
                found.extend(_calls_named(item, name, depth + 1))
        elif value is not None and hasattr(value, "kind"):
            found.extend(_calls_named(value, name, depth + 1))
    return found
