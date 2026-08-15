"""Structural directives: instance tree, "instantiated by", parameter matrix.

These are the three views that only an *elaborated* design can produce, and that
a file-at-a-time documentation tool cannot: what a module is built from, what
builds it, and which parameter values it is actually used at.

All three read :class:`~sphinx_systemverilog.model.structure.DesignStructure`,
and all three are the reason it gets computed at all --- nothing else in the
extension touches the instance hierarchy.  A page with none of these directives
pays nothing.

Two conventions run through the whole module:

* **Nothing is elided silently.**  A truncated tree, a capped usage list, and a
  budget-truncated walk all say so, with a count.  A structural view that
  quietly stops short reads as completeness, which is worse than being absent.
* **Scope is stated.**  Every view is derived from the sources this project
  parses, so "not instantiated" means "not instantiated *within the documented
  sources*" --- a distinction that matters for a reusable IP block.
"""

from __future__ import annotations

from typing import Any, Iterable

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from sphinx import addnodes
from sphinx.util import logging

logger = logging.getLogger(__name__)

#: Wording used wherever absence is reported.  Kept in one place because it is
#: a claim about scope, and an inconsistent claim is a misleading one.
SCOPE_NOTE = "within the documented sources"

_TEE = "├── "        # |--
_ELBOW = "└── "      # `--
_PIPE = "│   "                 # |
_BLANK = "    "

#: Placeholder ``rawsource`` for the tree's literal block.
#:
#: This is load-bearing, not cosmetic.  Sphinx's ``apply_source_workaround``
#: fills in an empty ``rawsource`` with ``node.astext()``, and the HTML writer
#: then treats ``rawsource == astext()`` as "this is a code block", highlights
#: the text and **discards every child node** -- silently deleting all of the
#: cross-references in the tree.  Any non-empty value that differs from the
#: rendered text keeps the node on the parsed-literal path, where children
#: survive.  It is never itself rendered.
_TREE_RAWSOURCE = "<sv:instance-tree>"


class _StructureDirective(Directive):
    """Shared plumbing: resolve the index, then the (lazily walked) structure."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False

    #: Human-readable directive name used in warnings.
    what = "structural directive"

    def _target(self) -> str:
        # Accept a qualified name for symmetry with the auto* directives, but
        # module and interface definition names are never package-qualified.
        return self.arguments[0].strip().split("::")[-1]

    def _resolve(self):
        """Return ``(structure, target)``, or ``None`` after warning.

        A target the index has never heard of is an authoring error and warns.
        A target that exists but has nothing structural to say is *not* --- a
        module that instantiates nothing, or that nothing instantiates, is a
        perfectly ordinary module, and each directive says so in prose.
        """
        env = self.state.document.settings.env
        target = self._target()
        index = getattr(env, "sv_index", None)
        if index is None:
            return None
        if index.get(target) is None and "optional" not in self.options:
            logger.warning(
                "sphinx-systemverilog: %s cannot find SystemVerilog object %r",
                self.what, target, type="systemverilog",
                location=(env.docname, self.lineno),
            )
            return None

        # The one place the hierarchy walk is paid for.
        structure = getattr(index, "structure", None)
        if structure is None:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: the elaborated design is not "
                    "available in this process, so %s cannot render %r; a full "
                    "rebuild (sphinx-build -E) will restore it",
                    self.what, target, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return None
        return structure, target

    def _note(self, text: str) -> nodes.paragraph:
        para = nodes.paragraph(classes=["sv-structure-note"])
        para += nodes.emphasis("", text)
        return para

    def _truncation_note(self, structure) -> list[nodes.Node]:
        if not structure.truncated:
            return []
        return [self._note(
            f"The hierarchy walk stopped after {structure.instance_count} "
            "instances (sv_structure_max_instances); this view is incomplete. "
            "Narrow sv_structure_tops or raise the limit."
        )]


def _type_ref(type_name: str) -> nodes.Node:
    """A cross-reference to a module/interface definition, by bare name.

    Uses the generic ``obj`` role: a design mixes modules and interfaces, and an
    unresolved target degrades to plain text rather than warning --- a tree
    routinely names types that no page documents.
    """
    ref = addnodes.pending_xref(
        "", nodes.literal(type_name, type_name, classes=["sv-type"]),
        refdomain="sv", reftype="obj", reftarget=type_name,
        refexplicit=False, refwarn=False,
    )
    return ref


def _source_ref(env: Any, location: Any) -> nodes.Node | None:
    """A ``[source]`` link for an instantiation site, if viewcode is enabled."""
    if location is None or not getattr(location, "is_valid", False):
        return None
    if not getattr(env.config, "sv_viewcode", True):
        return None
    from .. import viewcode

    # Register the line so a highlighted listing page is generated for the file
    # even when nothing else on it is documented.
    viewcode.record(env, location.file, location.line, "")
    return viewcode.make_source_node(env, location.file, location.line)


# -- instance tree ------------------------------------------------------------


class SvInstanceTree(_StructureDirective):
    """``.. sv:instance-tree:: soc`` -> the elaborated instance hierarchy.

    Text by default rather than Graphviz: a text tree stays readable at depth,
    needs no ``dot`` installed, is picked up by Sphinx's full-text search, is
    diffable in review, and lets every type name be a cross-reference.
    ``:diagram:`` opts into the graph for shallow views where a picture helps.
    """

    what = "instance tree"
    option_spec = {
        "depth": directives.nonnegative_int,
        "collapse": directives.flag,
        "diagram": directives.flag,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        resolved = self._resolve()
        if resolved is None:
            return []
        structure, target = resolved
        env = self.state.document.settings.env

        if target not in structure.edges:
            if "optional" in self.options:
                return []
            return [self._note(f"Instantiates nothing {SCOPE_NOTE}.")]

        if "diagram" in self.options:
            return self._diagram(env, structure, target)

        depth = self.options.get("depth", env.config.sv_instance_tree_depth)
        collapse = "collapse" in self.options

        block = nodes.literal_block(
            _TREE_RAWSOURCE, classes=["sv-instance-tree"]
        )
        block += _type_ref(target)
        block += nodes.Text("\n")
        elided = _Elision()
        self._render_children(
            block, structure, target, self._params_for(structure, target),
            prefix="", depth=depth, level=1, collapse=collapse, elided=elided,
            seen=(target,),
        )

        out: list[nodes.Node] = [block]
        out.extend(self._truncation_note(structure))
        if elided.levels:
            out.append(self._note(
                f"{elided.levels} deeper level(s) containing {elided.instances} "
                f"instance(s) not shown — raise :depth: (currently {depth})."
            ))
        return out

    def _params_for(self, structure, target: str):
        """Pick which elaboration of *target* to root the tree at.

        A top module has exactly one.  A mid-level module documented on its own
        page may have several; rooting at the first keeps the tree honest (it is
        a real elaboration) and the parameter values shown on each node make
        which one it is unambiguous.
        """
        options = structure.elaborations_of(target)
        return options[0] if options else ()

    def _render_children(
        self, block: nodes.Element, structure, type_name: str, params,
        prefix: str, depth: int, level: int, collapse: bool,
        elided: "_Elision", seen: tuple[str, ...],
    ) -> None:
        children = structure.children_of_elaboration(type_name, params)
        if not children:
            return
        if level > depth:
            elided.record(structure, children, seen)
            return

        if collapse:
            groups = _collapse_siblings(children)
        else:
            groups = [(c, [c.label]) for c in children]
        # Align the type column across siblings; a ragged tree is much harder to
        # scan than an aligned one, and siblings are what the eye compares.
        width = max(len(_folded_label(names)) for _, names in groups)
        for position, (child, names) in enumerate(groups):
            last = position == len(groups) - 1
            block += nodes.Text(prefix + (_ELBOW if last else _TEE))
            _append_instance_line(block, child, names, width)

            # A module cannot instantiate itself, but a generate-guarded chain
            # can revisit a type; stop rather than draw an infinite tree.
            if child.type_name in seen:
                block += nodes.Text(
                    prefix + (_BLANK if last else _PIPE) + "└── "
                    "(recursive)\n"
                )
                continue
            self._render_children(
                block, structure, child.type_name, child.params,
                prefix + (_BLANK if last else _PIPE),
                depth, level + 1, collapse, elided, seen + (child.type_name,),
            )

    def _diagram(self, env, structure, target: str) -> list[nodes.Node]:
        from sphinx.ext.graphviz import graphviz

        from .diagrams import build_instance_dot

        node = graphviz()
        node["code"] = build_instance_dot(structure.edges, target)
        node["options"] = {"docname": env.docname}
        node["alt"] = f"Instance diagram of {target}"
        return [node] + self._truncation_note(structure)


class _Elision:
    """Counts what a depth limit hid, so the tree can say so."""

    def __init__(self) -> None:
        self.levels = 0
        self.instances = 0

    def record(self, structure, children, seen: tuple[str, ...]) -> None:
        depth_below = 0
        stack = [(children, 1, seen)]
        while stack:
            batch, level, path = stack.pop()
            depth_below = max(depth_below, level)
            for child in batch:
                self.instances += child.total_count
                if child.type_name in path:
                    continue
                grandchildren = structure.children_of_elaboration(
                    child.type_name, child.params
                )
                if grandchildren:
                    stack.append(
                        (grandchildren, level + 1, path + (child.type_name,))
                    )
        self.levels = max(self.levels, depth_below)


#: Folded sibling names are listed rather than counted, up to this many; beyond
#: it the list itself becomes the noise it was meant to remove.
_MAX_FOLDED_NAMES = 4


def _collapse_siblings(children) -> list[tuple[Any, list[str]]]:
    """Fold structurally identical siblings, keeping source order.

    ``u_m1`` and ``u_m2`` --- same type, same parameters, same generate path ---
    are one line.  Only their names differ, so the fold is keyed on everything
    else and the names are carried along: ``u_m1, u_m2 : mid #(W=8)`` says more
    than ``u_m1 (×2)`` for the same width.
    """
    out: list[tuple[Any, list[str]]] = []
    positions: dict[tuple, int] = {}
    for child in children:
        key = (child.type_name, child.params, child.generate_path)
        if key in positions:
            out[positions[key]][1].append(child.label)
        else:
            positions[key] = len(out)
            out.append((child, [child.label]))
    return out


def _folded_label(names: list[str]) -> str:
    if len(names) <= _MAX_FOLDED_NAMES:
        return ", ".join(names)
    head = ", ".join(names[:_MAX_FOLDED_NAMES])
    return f"{head}, … +{len(names) - _MAX_FOLDED_NAMES}"


def _append_instance_line(
    block: nodes.Element, instance, names: list[str] | None = None, width: int = 0
) -> None:
    """``u_m1, u_m2 : mid #(W=8)   (×2)``"""
    names = names or [instance.label]
    block += nodes.Text(f"{_folded_label(names).ljust(width)} : ")
    block += _type_ref(instance.type_name)
    if instance.params:
        block += nodes.Text(f" {instance.param_text}")

    total = instance.total_count * len(names)
    if total > 1:
        block += nodes.Text(f"   (×{total})")
    block += nodes.Text("\n")


# -- instantiated by ----------------------------------------------------------


class SvUsedBy(_StructureDirective):
    """``.. sv:used-by:: leaf`` -> every site that instantiates a module.

    The highest-value structural view per line of code: it answers the question
    an engineer actually asks of an unfamiliar block --- "what uses this, and
    can I change it?" --- and no file-at-a-time tool can answer it.
    """

    what = "used-by list"
    option_spec = {
        "limit": directives.nonnegative_int,
        "optional": directives.flag,
    }

    def run(self) -> list[nodes.Node]:
        resolved = self._resolve()
        if resolved is None:
            return []
        structure, target = resolved
        env = self.state.document.settings.env

        sites = structure.sites_for(target)
        if not sites:
            if "optional" in self.options:
                return []
            return [self._note(f"Not instantiated {SCOPE_NOTE}.")]

        limit = self.options.get("limit", env.config.sv_used_by_limit)
        shown = sites[:limit] if limit else sites

        bullets = nodes.bullet_list(classes=["sv-used-by"])
        for site in shown:
            bullets += self._site_item(env, site)

        container = nodes.container(classes=["sv-used-by-container"])
        container += bullets
        out: list[nodes.Node] = [container]

        hidden = len(sites) - len(shown)
        if hidden > 0:
            out.append(self._note(
                f"{hidden} further instantiation site(s) not shown of "
                f"{len(sites)} total — raise :limit: or sv_used_by_limit."
            ))
        else:
            out.append(self._note(
                f"{len(sites)} instantiation site(s) {SCOPE_NOTE}."
            ))
        out.extend(self._truncation_note(structure))
        return out

    def _site_item(self, env, site) -> nodes.list_item:
        item = nodes.list_item()
        para = nodes.paragraph()
        para += nodes.literal(site.hier_path, site.hier_path)
        para += nodes.Text(" — ")
        para += _type_ref(site.parent_type)
        if site.instance.params:
            para += nodes.Text(f" {site.instance.param_text}")
        # Only the array multiplicity belongs here.  Generate iterations are
        # listed as separate sites, so folding their count in as well would
        # report four instances four times over.
        if site.instance.array_count > 1:
            para += nodes.Text(f"  (×{site.instance.array_count})")
        source = _source_ref(env, site.instance.location)
        if source is not None:
            para += nodes.Text(" ")
            para += source
        item += para
        return item


# -- parameterization matrix --------------------------------------------------


class SvParameterMatrix(_StructureDirective):
    """``.. sv:parameter-matrix:: leaf`` -> the values a module is used at.

    Distinct from the module's declared defaults, which is the point: a
    parameter's default tells you what happens if nobody overrides it, while
    this tells you what the design actually does.  Only elaboration knows.
    """

    what = "parameter matrix"
    option_spec = {"optional": directives.flag}

    def run(self) -> list[nodes.Node]:
        resolved = self._resolve()
        if resolved is None:
            return []
        structure, target = resolved

        usage = structure.param_usage(target)
        if not usage:
            if "optional" in self.options:
                return []
            return [self._note(
                f"No elaborated parameter values: {target} is either not "
                f"instantiated {SCOPE_NOTE} or takes no parameters."
            )]

        table = _build_table(
            ["Parameter", "Value", "Instances", "Example site"],
            list(_matrix_rows(usage)),
            classes=["sv-parameter-matrix"],
        )
        return [table, self._note(f"Values observed {SCOPE_NOTE}.")]


def _matrix_rows(usage: dict) -> Iterable[list[nodes.Node]]:
    for param, values in usage.items():
        for position, (value, paths) in enumerate(
            sorted(values.items(), key=lambda kv: -len(kv[1]))
        ):
            yield [
                nodes.literal(param, param) if position == 0 else nodes.Text(""),
                nodes.literal(value, value),
                nodes.Text(str(len(paths))),
                nodes.literal(paths[0], paths[0]),
            ]


def _build_table(
    headers: list[str], rows: list[list[nodes.Node]], classes: list[str]
) -> nodes.table:
    table = nodes.table(classes=classes)
    group = nodes.tgroup(cols=len(headers))
    table += group
    for _ in headers:
        group += nodes.colspec(colwidth=1)

    head = nodes.thead()
    group += head
    head += _row([nodes.Text(h) for h in headers])

    body = nodes.tbody()
    group += body
    for row in rows:
        body += _row(row)
    return table


def _row(cells: list[nodes.Node]) -> nodes.row:
    row = nodes.row()
    for cell in cells:
        entry = nodes.entry()
        para = nodes.paragraph()
        para += cell
        entry += para
        row += entry
    return row


STRUCTURE_DIRECTIVES = {
    "instance-tree": SvInstanceTree,
    "used-by": SvUsedBy,
    "parameter-matrix": SvParameterMatrix,
}
