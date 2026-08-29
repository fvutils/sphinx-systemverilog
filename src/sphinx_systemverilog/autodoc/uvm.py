"""UVM testbench directives.

``sv:uvm-tree`` is the testbench counterpart to ``sv:instance-tree``, and it
deliberately reuses that module's rendering rather than growing a parallel one:
the same text-tree shape, the same cross-referenced type names, the same
literal-block handling.  What differs is what the tree is *about*, and the
caveats that come with it.

An RTL instance tree is a fact the compiler produced.  A UVM tree is a reading
of ``build_phase`` statements, so three things that never arise for RTL have to
be visible in the output:

* a component may be **conditional** --- built only if some expression is true;
* a component may be built an **unknown number of times**, because a loop bound
  is not constant-foldable;
* a component's type may be **opaque** or **unresolved**, and those two are not
  the same thing (see :mod:`~sphinx_systemverilog.model.uvm`).

Every one of them is rendered inline on the node and summarized under the tree.
A view that quietly dropped any of them would read as completeness.

``sv:uvm-config`` answers the other structural question --- what the testbench
*configures* --- and carries the same obligation for the same reason: what it
cannot pair, it counts and says so.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from sphinx.ext.graphviz import graphviz
from sphinx.util import logging

from ..model.uvm import (
    OVERRIDE_INST,
    SEQUENCE_BASE,
    STATE_OK,
    STATE_OPAQUE,
    STATE_UNRESOLVED,
)
from .structure import _TREE_RAWSOURCE, _build_table, _type_ref
from .uvm_activity import build_activity_dot
from .uvm_diagram import (
    TIERS,
    build_schematic,
    build_schematic_dot,
    supports_newrank,
)

logger = logging.getLogger(__name__)

#: Stated on every testbench view.  The single most important sentence in the
#: feature: everything here is a claim about source, never about a run.
UVM_SCOPE_NOTE = (
    "Hierarchy as written in build_phase — not a simulation trace. "
    "Factory overrides, config-driven counts and dynamically named "
    "components are reported as such rather than resolved."
)

#: The same obligation, worded for a view that is about accesses rather than
#: containment.  "Hierarchy" would be the wrong noun on a config table, and a
#: scope note a reader has to reinterpret is one they stop reading.
UVM_CONFIG_SCOPE_NOTE = (
    "Accesses as written in source — not a simulation trace. Which components "
    "a setting actually reaches depends on run-time hierarchical paths and on "
    "any factory override in effect, neither of which is resolved here."
)

#: And once more for the activity diagram.  Every other view here is a static
#: reading of something dynamic; this one is a picture of control flow, which
#: really is what the source says.  What it still cannot know is *which way*
#: the flow went, so that is the sentence it carries.
UVM_SEQUENCE_SCOPE_NOTE = (
    "Control flow as written in body() — not a simulation trace. Which branch "
    "a decision takes, how many times a loop runs and which fork branch "
    "finishes first are properties of a run, and none of them are resolved "
    "here."
)

#: And once more for the schematic, which is about *wiring* rather than either
#: containment or configuration.  The diagram's specific hazard is that a
#: picture reads as authoritative in a way a table does not, so the caveat it
#: carries is the one about what a connection here is: a line of source.
UVM_SCHEMATIC_SCOPE_NOTE = (
    "Connections as written in connect_phase — not a simulation trace, and "
    "one level deep. A component built conditionally, or reached through a "
    "factory override, is drawn as the source describes it rather than as a "
    "run would resolve it."
)

_TEE = "├── "
_ELBOW = "└── "
_PIPE = "│   "
_BLANK = "    "

#: Folded sibling names are listed rather than counted, up to this many.
_MAX_FOLDED_NAMES = 4


class _UvmDirective(Directive):
    """Shared plumbing: resolve the index, then the (lazily extracted) tree."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = False
    has_content = False

    #: Human-readable directive name used in warnings.
    what = "UVM directive"

    def _requested_root(self) -> str:
        return self.arguments[0].strip().split("::")[-1] if self.arguments else ""

    def _provider(self):
        """Return the live :class:`UvmProvider`, or ``None`` after warning."""
        env = self.state.document.settings.env
        index = getattr(env, "sv_index", None)
        if index is None:
            return None

        provider = getattr(index, "uvm_provider", None)
        if provider is None:
            # The index was unpickled from Sphinx's environment, so the live
            # compilation is gone.  Degrade with an actionable warning rather
            # than crashing a build that may not even be about this page.
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: the elaborated testbench is not "
                    "available in this process, so %s cannot render; a full "
                    "rebuild (sphinx-build -E) will restore it",
                    self.what, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
        return provider

    def _resolve(self):
        """Return the :class:`UvmStructure`, or ``None`` after warning."""
        env = self.state.document.settings.env
        provider = self._provider()
        if provider is None:
            return None

        # The one place the testbench extraction is paid for.
        structure = provider.get(self._requested_root())
        if not structure.root:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s found no UVM test to document; "
                    "no run_test(\"...\") call was found in any top module. Name "
                    "a root explicitly or set sv_uvm_root",
                    self.what, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return None
        if structure.root not in structure.children:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s cannot find UVM component %r",
                    self.what, structure.root, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return None
        return structure

    def _note(self, text: str, extra_class: str = "") -> nodes.paragraph:
        classes = ["sv-structure-note"]
        if extra_class:
            classes.append(extra_class)
        para = nodes.paragraph(classes=classes)
        para += nodes.emphasis("", text)
        return para


class SvUvmTree(_UvmDirective):
    """``.. sv:uvm-tree:: my_test`` -> the component hierarchy build_phase builds.

    The argument is optional: with none, the root is auto-detected from a
    ``run_test("...")`` call, which is right for the overwhelmingly common case
    of one testbench per project.
    """

    what = "UVM tree"
    option_spec = {
        "depth": directives.nonnegative_int,
        "collapse": directives.flag,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        structure = self._resolve()
        if structure is None:
            return []
        env = self.state.document.settings.env

        depth = self.options.get("depth", env.config.sv_uvm_tree_depth)

        block = nodes.literal_block(_TREE_RAWSOURCE, classes=["sv-uvm-tree"])
        block += _type_ref(structure.root)
        block += nodes.Text("\n")

        # Shares the config_db walk, so a page with a tree and a config table
        # pays for one scan. A factory override is not optional information:
        # without it the tree names a type the simulation may never build.
        overrides = self._provider().overrides()

        state = _RenderState()
        self._render_children(
            block, structure, structure.root, prefix="", depth=depth, level=1,
            collapse="collapse" in self.options, state=state,
            seen=(structure.root,), overrides=overrides,
        )

        return [block] + self._notes(structure, state, depth, overrides)

    # -- rendering ------------------------------------------------------------

    def _render_children(
        self, block: nodes.Element, structure, type_name: str, prefix: str,
        depth: int, level: int, collapse: bool, state: "_RenderState",
        seen: tuple[str, ...], overrides,
    ) -> None:
        children = structure.children_of(type_name)
        if not children:
            return
        if level > depth:
            state.record_elision(structure, children, seen)
            return

        groups = (
            _collapse_siblings(children)
            if collapse
            else [(child, [_handle_of(child)]) for child in children]
        )
        # Align the type column across siblings; the eye compares siblings, and
        # a ragged tree is much harder to scan than an aligned one.
        width = max(len(_folded_label(names)) for _, names in groups)

        for position, (child, names) in enumerate(groups):
            last = position == len(groups) - 1
            block += nodes.Text(prefix + (_ELBOW if last else _TEE))
            applied = overrides.for_type(child.type_name.split("#", 1)[0])
            _append_component_line(block, child, names, width, applied)
            state.count(child)
            state.overridden.extend(applied)

            if child.state != STATE_OK:
                continue
            child_prefix = prefix + (_BLANK if last else _PIPE)
            if child.type_name in seen:
                # A mutually-recursive build_phase is legal to write.
                block += nodes.Text(child_prefix + "└── (recursive)\n")
                continue
            self._render_children(
                block, structure, child.type_name, child_prefix,
                depth, level + 1, collapse, state,
                seen + (child.type_name,), overrides,
            )

    # -- what the tree could not say ------------------------------------------

    def _notes(
        self, structure, state: "_RenderState", depth: int, overrides=None
    ) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        if state.overridden:
            out.append(self._note(
                f"{len(state.overridden)} component(s) above are affected by a "
                "factory override, shown as [overridden → type]. The tree still "
                "names the type its create call names, because whether an "
                "override applies is decided at run time — by whether its "
                "statement executed, by any later override, and for an inst "
                "override by a hierarchical path that does not exist until "
                "elaboration."
            ))

        broken = overrides.broken if overrides is not None else []
        if broken:
            names = ", ".join(sorted({n for o in broken for n in o.unknown}))
            out.append(self._note(
                f"{len(broken)} factory override(s) name a type that is not in "
                f"the parsed sources ({names}). The by-name forms take strings, "
                "so a typo compiles, elaborates and simulates — and the override "
                "silently never applies.",
                extra_class="sv-uvm-unresolved",
            ))

        if structure.truncated:
            out.append(self._note(
                f"The walk stopped after {structure.component_count} component "
                "type(s) (sv_uvm_max_components); this view is incomplete."
            ))

        if state.elided_levels:
            out.append(self._note(
                f"{state.elided_levels} deeper level(s) containing "
                f"{state.elided_components} component(s) not shown — raise "
                f":depth: (currently {depth})."
            ))

        if state.unresolved:
            names = ", ".join(sorted({c.type_name for c in state.unresolved}))
            out.append(self._note(
                f"{len(state.unresolved)} component(s) could not be resolved "
                f"({names}). Their types are not present in the parsed sources, "
                "so nothing below them is known. This usually means a generated "
                "or vendor package was not available when the docs were built.",
                extra_class="sv-uvm-unresolved",
            ))

        if state.opaque:
            out.append(self._note(
                f"{len(state.opaque)} component(s) shown as boundaries and not "
                "expanded (sv_uvm_blackbox / sv_uvm_blackbox_bases, plus UVM "
                "library types)."
            ))

        if len(structure.root_candidates) > 1:
            others = ", ".join(
                name for name in structure.root_candidates if name != structure.root
            )
            out.append(self._note(
                f"This project contains more than one test; showing "
                f"{structure.root}. Others: {others}. Name one as the directive "
                "argument to choose."
            ))

        out.append(self._note(UVM_SCOPE_NOTE))
        return out


class _RenderState:
    """Everything the tree must report but cannot show inline."""

    def __init__(self) -> None:
        self.unresolved: list[Any] = []
        self.opaque: list[Any] = []
        self.overridden: list[Any] = []
        self.elided_levels = 0
        self.elided_components = 0

    def count(self, child) -> None:
        if child.state == STATE_UNRESOLVED:
            self.unresolved.append(child)
        elif child.state == STATE_OPAQUE:
            self.opaque.append(child)

    def record_elision(self, structure, children, seen: tuple[str, ...]) -> None:
        """Count what the depth limit hid, so the tree can say how much."""
        deepest = 0
        stack = [(children, 1, seen)]
        while stack:
            batch, level, path = stack.pop()
            deepest = max(deepest, level)
            for child in batch:
                self.elided_components += 1
                if child.state != STATE_OK or child.type_name in path:
                    continue
                grandchildren = structure.children_of(child.type_name)
                if grandchildren:
                    stack.append(
                        (grandchildren, level + 1, path + (child.type_name,))
                    )
        self.elided_levels = max(self.elided_levels, deepest)


# -- line rendering -----------------------------------------------------------


def _handle_of(child) -> str:
    """The name to show on the left of the colon."""
    return child.handle or child.inst_name or "?"


def _collapse_siblings(children) -> list[tuple[Any, list[str]]]:
    """Fold siblings that differ only in name, keeping source order.

    ``agt_a`` and ``agt_b`` --- same type, same caveats --- are one line. The
    fold is keyed on everything *except* the name, so two agents built under
    different conditions never merge into one line that misrepresents both.
    """
    out: list[tuple[Any, list[str]]] = []
    positions: dict[tuple, int] = {}
    for child in children:
        key = (
            child.type_name, child.state, child.conditional,
            child.multiplicity, child.created_by,
        )
        if key in positions:
            out[positions[key]][1].append(_handle_of(child))
        else:
            positions[key] = len(out)
            out.append((child, [_handle_of(child)]))
    return out


def _folded_label(names: list[str]) -> str:
    if len(names) <= _MAX_FOLDED_NAMES:
        return ", ".join(names)
    head = ", ".join(names[:_MAX_FOLDED_NAMES])
    return f"{head}, … +{len(names) - _MAX_FOLDED_NAMES}"


def _append_component_line(
    block: nodes.Element, child, names: list[str], width: int,
    overrides: list | None = None,
) -> None:
    """``agt_a, agt_b : my_agent   (×N)  [conditional]  [overridden → fast_drv]``

    The override annotation is appended, never substituted. A tree that quietly
    printed ``fast_drv`` here would be *more* wrong than the un-annotated one:
    the source says ``my_agent``, and which type a run builds depends on whether
    the override statement executed, on whether a later one replaced it, and --
    for an inst override -- on a hierarchical path that does not exist until
    elaboration. Showing both is the only honest rendering.
    """
    block += nodes.Text(f"{_folded_label(names).ljust(width)} : ")
    block += _type_ref(child.type_name.split("#", 1)[0])
    # A specialization's parameters are part of what the reader sees in source,
    # but only the bare name is a linkable object.
    if "#" in child.type_name:
        block += nodes.Text(child.type_name[child.type_name.index("#"):])

    if child.multiplicity != "1":
        block += nodes.Text(f"   (×{child.multiplicity})")
    if child.conditional:
        block += nodes.Text("  [conditional]")
    if child.state != STATE_OK:
        block += nodes.Text(f"  [{child.state}]")
    for override in overrides or ():
        block += nodes.Text("  [overridden → ")
        block += _type_ref(override.replacement)
        suffix = ""
        if override.replacement in override.unknown:
            # A by-name override naming a type that does not exist. Marked here
            # as well as counted below, because a reader scanning the tree for
            # what affects *this* component should not have to cross-check the
            # note to find out that this one never fires.
            suffix += " — no such type"
        if override.kind == OVERRIDE_INST:
            path = "(computed)" if override.inst_path is None else override.inst_path
            suffix += f" under {path}"
        if override.conditional:
            suffix += " conditionally"
        block += nodes.Text(f"{suffix}]")
    block += nodes.Text("\n")


class SvUvmConfig(_UvmDirective):
    """``.. sv:uvm-config::`` -> what the testbench configures, and who reads it.

    The table is the ordinary half.  The interesting half is what sits under
    it: a ``set`` whose field name no ``get`` could ever match is almost always
    a typo, and a typo'd ``config_db`` field is invisible --- it compiles, it
    simulates, and the component silently keeps its default.  Nothing at run
    time reports it, which is exactly why reporting it here is worth doing.

    The optional argument is a glob on the setting component's name, for a page
    that documents one agent rather than the whole testbench.
    """

    what = "UVM config table"
    option_spec = {
        "orphans": directives.flag,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        provider = self._provider()
        if provider is None:
            return []

        # The one place the config_db scan is paid for.  Note this does *not*
        # elaborate the component hierarchy: a page with only a config table
        # never walks a single build_phase for the tree.
        config = provider.config()
        pattern = self.arguments[0].strip() if self.arguments else ""
        rows = [
            row for row in config.rows()
            if (not pattern or fnmatchcase(row.access.owner, pattern))
            and (row.orphan or "orphans" not in self.options)
        ]

        if not rows and not config.accesses:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s found no uvm_config_db accesses "
                    "in the parsed sources",
                    self.what, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []

        self._warn_orphans(config, env)
        table = _build_table(
            ["Setter", "Scope", "Field", "Type", "Value", "Consumers"],
            [_config_row(row) for row in rows],
            classes=["sv-uvm-config"],
        )
        return [table] + self._notes(config, rows, pattern)

    def _warn_orphans(self, config, env) -> None:
        """Emit build warnings for orphans, only when asked to.

        Off by default on purpose.  Adopting this extension should never turn a
        green documentation build red because of a testbench smell the reader
        did not ask about; the finding is always *rendered*, and promoting it to
        a warning is a decision a project makes for itself.
        """
        if not env.config.sv_uvm_warn_orphans:
            return
        for access in config.orphan_sets:
            logger.warning(
                "sphinx-systemverilog: uvm_config_db set of %r in %s is never "
                "read by any get; check the field name for a typo",
                access.field, access.where, type="systemverilog",
                location=(env.docname, self.lineno),
            )
        for access in config.orphan_gets:
            logger.warning(
                "sphinx-systemverilog: uvm_config_db get of %r in %s is never "
                "set by anything; the default will always be used",
                access.field, access.where, type="systemverilog",
                location=(env.docname, self.lineno),
            )

    def _notes(self, config, rows, pattern: str) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        orphans = [row for row in rows if row.orphan]
        if orphans:
            fields = ", ".join(sorted({str(row.access.field) for row in orphans}))
            out.append(self._note(
                f"{len(orphans)} setting(s) are read by nothing ({fields}). A "
                "config_db field name is a string: a typo compiles, simulates, "
                "and silently leaves the component on its default.",
                extra_class="sv-uvm-unresolved",
            ))

        if not pattern and config.orphan_gets:
            fields = ", ".join(sorted({str(a.field) for a in config.orphan_gets}))
            out.append(self._note(
                f"{len(config.orphan_gets)} field(s) are read but never set "
                f"({fields}); those components always use their defaults."
            ))

        if config.dynamic:
            out.append(self._note(
                f"{len(config.dynamic)} access(es) build their field name at "
                "run time and could not be paired, so the orphan analysis above "
                "is incomplete by that much."
            ))

        out.append(self._note(
            "Pairing is on the field name only, and matches globs in both "
            "directions. Scope is shown but takes no part in it: a set's full "
            "scope depends on the run-time path of its cntxt argument, so "
            "using it could only report matches that exist as orphans."
        ))
        out.append(self._note(UVM_CONFIG_SCOPE_NOTE))
        return out


def _config_row(row) -> list[nodes.Node]:
    access = row.access
    setter = nodes.inline()
    setter += nodes.literal(access.where, access.where)
    if access.conditional:
        setter += nodes.Text("  [conditional]")

    field_text = "(computed)" if access.field is None else access.field
    field_cell = nodes.inline()
    field_cell += nodes.literal(field_text, field_text)
    if row.orphan:
        field_cell += nodes.Text("  ← unread")

    consumers = nodes.inline()
    if row.consumers:
        for position, name in enumerate(row.consumers):
            if position:
                consumers += nodes.Text(", ")
            consumers += nodes.literal(name, name)
    else:
        consumers += nodes.emphasis(
            "", "(computed)" if access.dynamic else "(none)"
        )

    return [
        setter,
        nodes.literal(access.full_scope, access.full_scope),
        field_cell,
        _type_ref(access.type_name.split("#", 1)[0]),
        nodes.literal(access.value, access.value),
        consumers,
    ]


class SvUvmSchematic(_UvmDirective):
    """``.. sv:uvm-schematic:: my_env`` -> how the components are wired.

    The tree answers "what is built"; this answers "what is connected to what",
    which is the question a diagram is actually better at than text.  Agents are
    drawn as clusters holding their own components, everything else as a box
    with its TLM ports on it, and connections as edges that decorate the layout
    rather than dictating it.

    Single-level by design (decision D3).  A schematic that nested sub-envs
    would have to answer questions --- how to aggregate edges at a boundary,
    what a tier means two levels down --- that have no good answer yet, and
    depth is already served well by ``sv:uvm-tree``.
    """

    what = "UVM schematic"
    option_spec = {
        "tier": directives.unchanged,
        "order": directives.unchanged,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        structure = self._resolve()
        if structure is None:
            return []
        env = self.state.document.settings.env

        root = (
            self._requested_root() if self.arguments
            else _schematic_root(structure)
        )
        if not structure.children_of(root):
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s has nothing to draw for %r: its "
                    "build_phase creates no components",
                    self.what, root, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []

        schematic = build_schematic(
            structure, root,
            tiers=_parse_tiers(self, root),
            order=_parse_order(self.options.get("order", "")),
        )
        newrank = supports_newrank(getattr(env.config, "graphviz_dot", "dot"))

        node = graphviz()
        node["code"] = build_schematic_dot(schematic, newrank=newrank)
        node["options"] = {"docname": env.docname}
        node["alt"] = f"UVM schematic of {root}"
        return [node] + self._notes(schematic, root, newrank)

    def _notes(self, schematic, root: str, newrank: bool) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        if schematic.dropped:
            out.append(self._note(
                f"{len(schematic.dropped)} connection(s) reach outside this "
                f"single-level view of {root} and are not drawn: "
                + "; ".join(schematic.dropped) + ".",
                extra_class="sv-uvm-unresolved",
            ))

        if schematic.hidden_ports:
            out.append(self._note(
                f"{schematic.hidden_ports} TLM port(s) inherited from UVM are "
                "not shown, because nothing in this view connects to them. "
                "Ports declared by your own components are always shown."
            ))

        if any(edge[3] for edge in schematic.edges) or any(
            node.conditional for node in schematic.nodes
        ):
            out.append(self._note(
                "Dotted edges and components marked [conditional] are written "
                "under an if or case, so the source does not say they are "
                "always there."
            ))

        if not newrank:
            out.append(self._note(
                "The available Graphviz does not support newrank (2.30+), so "
                "the tier pinning was dropped from this diagram; the wiring is "
                "unchanged but the layout is less orderly."
            ))

        out.append(self._note(UVM_SCHEMATIC_SCOPE_NOTE))
        return out


def _schematic_root(structure) -> str:
    """The component a schematic is most useful *about*, from the tree root.

    A test is almost always a single box containing a single env, and drawing
    that is technically correct and completely useless.  So the default walks
    down while there is exactly one child, stopping at the first env or at the
    first component that actually branches --- which is the level where wiring
    exists to be shown.  Naming a root explicitly overrides all of this.
    """
    name = structure.root
    for _ in range(8):
        info = structure.type_of(name)
        if info is not None and info.tier == "env":
            return name
        children = structure.children_of(name)
        if len(children) != 1 or children[0].state != STATE_OK:
            return name
        name = children[0].type_name
    return name


def _parse_tiers(directive, root: str) -> dict[str, str]:
    """``:tier: sb=top, agt_a=bottom`` -> a mapping, warning on anything else.

    An unusable override is warned about rather than ignored: a reader who
    misspells a tier and sees the default layout has no way to tell that their
    request was silently dropped.
    """
    env = directive.state.document.settings.env
    out: dict[str, str] = {}
    for item in directive.options.get("tier", "").split(","):
        item = item.strip()
        if not item:
            continue
        name, _, tier = item.partition("=")
        if tier.strip() in TIERS:
            out[name.strip()] = tier.strip()
        else:
            logger.warning(
                "sphinx-systemverilog: UVM schematic of %r: :tier: entry %r is "
                "not <name>=<%s>", root, item, "|".join(TIERS),
                type="systemverilog",
                location=(env.docname, directive.lineno),
            )
    return out


def _parse_order(text: str) -> list[str]:
    return [name.strip() for name in text.split(",") if name.strip()]


class SvUvmSequence(_UvmDirective):
    """``.. sv:uvm-sequence:: main_seq`` -> ``body()`` as a UML activity diagram.

    The one view on this page that is not an approximation of something else.
    A component tree is a static reading of a dynamic hierarchy and a schematic
    is a static reading of dynamic wiring, but a sequence *is* a control-flow
    object, so an activity diagram is its natural shape rather than an imposed
    one.  What the diagram cannot say is which way a branch went, and that is a
    property of the run, not a limitation of the reading.

    The argument is required.  Every other UVM directive can default its root
    from ``run_test``; there is no equivalent for "the sequence", and picking
    one alphabetically would be a guess dressed as a default.
    """

    what = "UVM sequence diagram"
    required_arguments = 1
    option_spec = {
        "depth": directives.nonnegative_int,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        provider = self._provider()
        if provider is None:
            return []

        name = self._requested_root()
        sequence = provider.sequence(name)
        if sequence is None:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s cannot find a UVM sequence named "
                    "%r; the class is either absent from the parsed sources or "
                    "does not derive from %s",
                    self.what, name, SEQUENCE_BASE, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []

        if not sequence.overridden:
            # Not a failure, and not something to draw an empty box for: the
            # sequence really does inherit the library's empty `body()`.
            return [self._note(
                f"{name} does not define a body(); it inherits the empty one "
                f"from {sequence.declared_by}. There is nothing to draw."
            )]

        depth = max(1, self.options.get("depth", 1))
        code, diagram = build_activity_dot(
            sequence, self._subsequences(provider, sequence, depth), depth=depth
        )

        node = graphviz()
        node["code"] = code
        node["options"] = {"docname": env.docname}
        node["alt"] = f"UVM activity diagram of {name}"
        return [node] + self._notes(sequence, diagram)

    def _subsequences(self, provider, sequence, depth: int) -> dict:
        """Every sub-sequence reachable within *depth* levels, by type name.

        Collected breadth-first and bounded by the requested depth, so a
        sequence that starts itself --- a legitimate thing to write --- cannot
        turn one directive into an unbounded walk.
        """
        found: dict = {}
        frontier, level = [sequence], 1
        while frontier and level <= depth:
            nxt = []
            for item in frontier:
                for type_name in item.subsequences():
                    if type_name in found:
                        continue
                    resolved = provider.sequence(type_name)
                    found[type_name] = resolved
                    if resolved is not None:
                        nxt.append(resolved)
            frontier, level = nxt, level + 1
        return found

    def _notes(self, sequence, diagram) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        if diagram.unexpanded:
            para = self._note(
                f"{len(diagram.unexpanded)} sub-sequence(s) are drawn as a "
                "single step; raise :depth: to open them: "
            )
            para += _joined_refs(diagram.unexpanded)
            para += nodes.Text(".")
            out.append(para)

        if diagram.unresolved:
            out.append(self._note(
                f"{len(diagram.unresolved)} sub-sequence type(s) could not be "
                "resolved and are drawn by name only ("
                + ", ".join(diagram.unresolved)
                + "). Their bodies are not in the parsed sources.",
                extra_class="sv-uvm-unresolved",
            ))

        if sequence.macros:
            out.append(self._note(
                "Steps labelled with a macro name ("
                + ", ".join(f"`{macro}" for macro in sequence.macros)
                + ") were recovered from that macro's expansion. Each use is "
                "one step, however many statements it expands to."
            ))

        if sequence.other:
            out.append(self._note(
                f"{sequence.other} statement(s) in body() are not drawn. "
                "Reporting, assignment and randomization are not control flow, "
                "and a diagram of only the constructs it understands would be "
                "claiming the task is shorter than it is."
            ))

        out.append(self._note(UVM_SEQUENCE_SCOPE_NOTE))
        return out


class SvUvmBinding(_UvmDirective):
    """``.. sv:uvm-binding::`` -> the virtual-interface bridge, RTL to testbench.

    The view this whole extension is in a position to produce and most tools
    are not, because it elaborates *both* sides.  A virtual-interface binding
    is a join between two worlds through a string: a top module files an
    interface instance in ``uvm_config_db`` under a field name, and a component
    fetches it back by that name.  No compiler checks that the two agree, no
    tool that reads only the RTL can see the testbench end, and no tool that
    reads only the classes can see the RTL end.

    Three failures are therefore rendered rather than left to a simulation:
    a binding nothing reads, an interface handed over but wired to nothing, and
    a value that is a handle rather than an instance.  All three produce the
    same symptom at run time --- a null virtual interface, dereferenced
    hundreds of cycles in --- and none of them produce anything at compile time.

    The optional argument is a glob on the interface type, for a page that
    documents one interface rather than the whole bridge.
    """

    what = "UVM binding table"
    option_spec = {
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        provider = self._provider()
        if provider is None:
            return []

        # Costs one config_db scan plus a bounded look at each interface's own
        # scope.  In particular it does *not* walk the RTL hierarchy, and does
        # not walk a single build_phase.
        bridge = provider.bridge()
        pattern = self.arguments[0].strip() if self.arguments else ""
        bindings = [
            binding for binding in bridge.bindings
            if not pattern or fnmatchcase(binding.interface_type, pattern)
        ]

        if not bindings:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s found no virtual-interface "
                    "bindings%s; a uvm_config_db#(virtual ...)::set is what "
                    "this table is about",
                    self.what,
                    f" matching {pattern!r}" if pattern else "",
                    type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []

        table = _build_table(
            ["Set in", "Scope", "Field", "Interface", "RTL instance",
             "Connects to", "Read by"],
            [_binding_row(binding) for binding in bindings],
            classes=["sv-uvm-binding"],
        )
        return [table] + self._notes(bindings)

    def _notes(self, bindings) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        orphans = [b for b in bindings if b.orphan]
        if orphans:
            fields = ", ".join(sorted({str(b.field) for b in orphans}))
            out.append(self._note(
                f"{len(orphans)} binding(s) are read by no component "
                f"({fields}). Unlike an ordinary config_db miss, a virtual "
                "interface that never arrives has no usable default: the "
                "component holds null and fails at its first dereference.",
                extra_class="sv-uvm-unresolved",
            ))

        undriven = [b for b in bindings if b.undriven]
        if undriven:
            names = ", ".join(b.instance_path for b in undriven)
            out.append(self._note(
                f"{len(undriven)} interface instance(s) are handed to the "
                f"testbench but connect to no RTL in their own scope "
                f"({names}).",
                extra_class="sv-uvm-unresolved",
            ))

        unresolved = [b for b in bindings if not b.resolved]
        if unresolved:
            fields = ", ".join(str(b.field) for b in unresolved)
            out.append(self._note(
                f"{len(unresolved)} binding(s) pass a virtual-interface handle "
                f"rather than an interface instance ({fields}), so there is no "
                "RTL instance to name. The handle's own binding is the row "
                "above it, wherever that was set."
            ))

        out.append(self._note(
            "The RTL side is the instances declared in the same scope as the "
            "interface. An interface passed further down through a port "
            "reaches deeper modules too, and those are not listed."
        ))
        out.append(self._note(
            "Pairing is on the field name, matching globs in both directions, "
            "and on the interface type: uvm_config_db#(T) is keyed on T, so a "
            "get of a different interface cannot read this binding whatever "
            "the field is called. Scope takes no part in it — a set's full "
            "scope depends on the run-time path of its cntxt argument."
        ))
        return out


def _binding_row(binding) -> list[nodes.Node]:
    access = binding.set_access
    field_text = "(computed)" if binding.field is None else binding.field

    field_cell = nodes.inline()
    field_cell += nodes.literal(field_text, field_text)
    if binding.orphan:
        field_cell += nodes.Text("  ← unread")

    instance = nodes.inline()
    if binding.resolved:
        instance += nodes.literal(binding.instance_path, binding.instance_path)
    else:
        instance += nodes.emphasis("", f"(handle: {access.value})")

    connects = nodes.inline()
    if binding.drivers:
        for position, driver in enumerate(binding.drivers):
            if position:
                connects += nodes.Text(", ")
            # The instance path is the fact; the type name is what a
            # cross-reference can point at, so the row carries both.
            connects += nodes.literal(driver.path, driver.path)
            connects += nodes.Text(" : ")
            connects += _type_ref(driver.type_name)
    elif binding.resolved:
        connects += nodes.emphasis("", "(nothing)")
    else:
        connects += nodes.emphasis("", "(unknown)")

    readers = nodes.inline()
    if binding.consumers:
        for position, consumer in enumerate(dict.fromkeys(
            access_.where for access_ in binding.consumers
        )):
            if position:
                readers += nodes.Text(", ")
            readers += nodes.literal(consumer, consumer)
    else:
        readers += nodes.emphasis("", "(none)")

    return [
        nodes.literal(access.where, access.where),
        nodes.literal(access.full_scope, access.full_scope),
        field_cell,
        _type_ref(binding.interface_type),
        instance,
        connects,
        readers,
    ]


class SvUvmUsedBy(_UvmDirective):
    """``.. sv:uvm-used-by:: my_agent`` -> every component that builds this one.

    The inverse of :class:`SvUvmTree`, and the counterpart to ``sv:used-by``
    for RTL. On a component's own page it answers the question the tree cannot:
    a tree shows what a component builds, and a reader arriving at ``my_agent``
    wants to know who builds *it*, under what handle, and whether that happens
    unconditionally.

    A component built nowhere is a real and useful finding --- a class written,
    registered with the factory, and never instantiated --- so it is reported
    rather than rendered as an empty table.
    """

    what = "UVM used-by table"
    required_arguments = 1
    option_spec = {
        "optional": directives.flag,
        "root": directives.unchanged,
    }

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        provider = self._provider()
        if provider is None:
            return []

        name = self._requested_root()
        structure = provider.get(self.options.get("root", "").strip())
        if not structure.root:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: %s found no UVM test to document; "
                    "no run_test(\"...\") call was found in any top module",
                    self.what, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []

        sites = structure.built_by(name)
        if not sites:
            # Distinguishing the two cases matters: "nothing builds this" is a
            # finding about the testbench, "no such component" is a mistake in
            # the directive, and rendering the same thing for both would hide
            # the first behind the second.
            # Asked of the class index, not of the tree: a class that is never
            # built is absent from the tree for exactly the same reason a
            # misspelled name is, and the two are opposite findings.
            if not provider.knows(name):
                if "optional" not in self.options:
                    logger.warning(
                        "sphinx-systemverilog: %s cannot find UVM component %r "
                        "in the tree rooted at %s",
                        self.what, name, structure.root, type="systemverilog",
                        location=(env.docname, self.lineno),
                    )
                return []
            # The override note matters *most* here: "nothing builds this" is
            # only half the story for a class that exists precisely to stand in
            # for another one, and stopping at the first half would report a
            # deliberate override target as dead code.
            return [self._note(
                f"{name} is not built by name anywhere in the testbench rooted "
                f"at {structure.root}."
            )] + self._notes(structure, name, [])

        table = _build_table(
            ["Built by", "Handle", "How"],
            [_used_by_row(parent, child) for parent, child in sites],
            classes=["sv-uvm-used-by"],
        )
        return [table] + self._notes(structure, name, sites)

    def _notes(self, structure, name: str, sites) -> list[nodes.Node]:
        out: list[nodes.Node] = []

        conditional = [child for _, child in sites if child.conditional]
        if conditional:
            out.append(self._note(
                f"{len(conditional)} of these site(s) sit under an if or case, "
                "so this component may not be built at all."
            ))

        overrides = self._provider().overrides()
        replacing = [o for o in overrides.overrides if o.replacement == name]
        if replacing:
            originals = ", ".join(sorted({o.original for o in replacing}))
            out.append(self._note(
                f"{name} also stands in for {originals} through a factory "
                "override, so it may be built at sites that name a different "
                "type. Those sites are not listed here: whether the override "
                "applies is a run-time question."
            ))

        out.append(self._note(
            f"Sites in the testbench rooted at {structure.root}. A component "
            "built by a testbench this tree does not reach is not listed."
        ))
        out.append(self._note(UVM_SCOPE_NOTE))
        return out


def _used_by_row(parent: str, child) -> list[nodes.Node]:
    handle = nodes.inline()
    handle += nodes.literal(
        child.handle or child.inst_name or "?", child.handle or child.inst_name or "?"
    )
    if child.multiplicity != "1":
        handle += nodes.Text(f"  (×{child.multiplicity})")

    how = nodes.inline()
    how += nodes.Text(
        "factory" if child.created_by == "factory" else "new"
    )
    if child.conditional:
        how += nodes.Text("  [conditional]")

    return [_type_ref(parent), handle, how]


def _joined_refs(names: list[str]) -> list[nodes.Node]:
    """Type cross-references, comma-separated, for use inside a paragraph."""
    out: list[nodes.Node] = []
    for position, name in enumerate(names):
        if position:
            out.append(nodes.Text(", "))
        out.append(_type_ref(name))
    return out


UVM_DIRECTIVES = {
    "uvm-tree": SvUvmTree,
    "uvm-config": SvUvmConfig,
    "uvm-schematic": SvUvmSchematic,
    "uvm-sequence": SvUvmSequence,
    "uvm-binding": SvUvmBinding,
    "uvm-used-by": SvUvmUsedBy,
}
