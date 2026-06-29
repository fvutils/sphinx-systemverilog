"""The ``auto*`` directives (autosvclass, autosvpackage, ...).

Each directive resolves a qualified name against the project-wide
:class:`~sphinx_systemverilog.model.index.SvIndex`, renders it (and optionally
its members) to RST via :class:`SvDocumenter`, and nested-parses the result so
it flows through the ``sv`` domain.
"""

from __future__ import annotations

from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.statemachine import StringList
from sphinx.util import logging
from sphinx.util.nodes import nested_parse_with_titles

from .documenters import SvDocumenter

logger = logging.getLogger(__name__)


def _members_option(arg: str | None):
    """``:members:`` with no value -> True (all); with a list -> those names."""
    if arg is None or not arg.strip():
        return True
    return [a.strip() for a in arg.replace(",", " ").split() if a.strip()]


def _names_option(arg: str | None) -> list[str]:
    if not arg:
        return []
    return [a.strip() for a in arg.replace(",", " ").split() if a.strip()]


class AutoSvDirective(Directive):
    """Base for ``auto*`` directives.  Subclasses set :attr:`object_kind`."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {
        "members": _members_option,
        "undoc-members": directives.flag,
        "inherited-members": directives.flag,
        "exclude-members": _names_option,
        "member-order": lambda a: directives.choice(a, ("source", "alpha", "groups")),
        "doc-style": directives.unchanged,
        "recursive": directives.flag,
        "show-inheritance": directives.flag,
        # Skip silently (no warning) when the target is not in the index - used
        # to make a page render the same whether optional sources are present.
        "optional": directives.flag,
    }

    #: Restrict the resolved object to this kind (None = any).
    object_kind: str | None = None

    def run(self) -> list[nodes.Node]:
        env = self.state.document.settings.env
        app = env.app
        target = self.arguments[0].strip()

        index = getattr(env, "sv_index", None)
        if index is None:
            logger.warning(
                "sphinx-systemverilog: source index not built; "
                "is the extension configured with sv_source_dirs?",
                location=(env.docname, self.lineno),
            )
            return []

        obj = index.get(target)
        if obj is None:
            if "optional" not in self.options:
                logger.warning(
                    "sphinx-systemverilog: cannot find SystemVerilog object %r",
                    target, type="systemverilog",
                    location=(env.docname, self.lineno),
                )
            return []
        if self.object_kind and obj.kind != self.object_kind:
            logger.warning(
                "sphinx-systemverilog: %r is a %s, not a %s",
                target, obj.kind, self.object_kind, type="systemverilog",
                location=(env.docname, self.lineno),
            )

        options = self._resolve_options(env)
        default_style = self.options.get("doc-style") or env.config.sv_doc_style
        documenter = SvDocumenter(app, options, default_style, index=index)
        rst_lines = documenter.render(obj)

        container = nodes.section()
        container.document = self.state.document
        content = StringList(rst_lines, source="<autosv>")
        nested_parse_with_titles(self.state, content, container)
        return container.children

    def _resolve_options(self, env) -> dict[str, Any]:
        merged: dict[str, Any] = dict(env.config.sv_default_options or {})
        merged.update(self.options)
        # ``directives.flag`` stores None when present; normalize to True so
        # callers can test truthiness.
        for key in (
            "undoc-members", "inherited-members", "recursive", "show-inheritance",
        ):
            if key in merged and merged[key] is None:
                merged[key] = True
        return merged


class AutoSvPackageDirective(AutoSvDirective):
    object_kind = "package"


class AutoSvClassDirective(AutoSvDirective):
    object_kind = "class"


class AutoSvModuleDirective(AutoSvDirective):
    object_kind = "module"


class AutoSvFunctionDirective(AutoSvDirective):
    object_kind = "function"


class AutoSvTaskDirective(AutoSvDirective):
    object_kind = "task"


class AutoSvSummaryDirective(Directive):
    """``.. autosvsummary::`` -> document a whole subtree of the index.

    With no argument it documents every top-level object; ``:packages:`` /
    ``:kinds:`` / a name-glob argument narrow the scope ("parse wide, reference
    scope").  This is the project's Exhale-analog whole-tree front-end.
    """

    required_arguments = 0
    optional_arguments = 1          # an optional name glob
    final_argument_whitespace = False
    has_content = False
    option_spec = {
        "members": _members_option,
        "undoc-members": directives.flag,
        "member-order": lambda a: directives.choice(a, ("source", "alpha", "groups")),
        "packages": _names_option,
        "kinds": _names_option,
        "exclude": _names_option,
        "doc-style": directives.unchanged,
    }

    def run(self) -> list[nodes.Node]:
        import fnmatch

        env = self.state.document.settings.env
        app = env.app
        index = getattr(env, "sv_index", None)
        if index is None:
            logger.warning(
                "sphinx-systemverilog: source index not built", type="systemverilog",
                location=(env.docname, self.lineno),
            )
            return []

        glob = self.arguments[0].strip() if self.arguments else None
        packages = set(self.options.get("packages") or [])
        kinds = set(self.options.get("kinds") or [])
        exclude = set(self.options.get("exclude") or [])

        # Without a kind filter, document top-level roots (packages/modules);
        # with one, gather matching objects at any depth.
        if kinds:
            candidates = [o for root in index.roots for o in root.walk()
                          if o.kind in kinds]
        else:
            candidates = list(index.roots)

        roots = []
        for obj in candidates:
            qn = obj.qualified_name or obj.name
            if packages and not any(
                qn == p or qn.startswith(p + "::") for p in packages
            ):
                continue
            if obj.name in exclude:
                continue
            if glob and not fnmatch.fnmatch(obj.name, glob):
                continue
            roots.append(obj)

        options = dict(env.config.sv_default_options or {})
        if "members" not in self.options:
            options["members"] = True       # whole-tree implies members
        options.update(self.options)
        for key in ("undoc-members",):
            if key in options and options[key] is None:
                options[key] = True
        default_style = self.options.get("doc-style") or env.config.sv_doc_style

        documenter = SvDocumenter(app, options, default_style, index=index)
        rst_lines: list[str] = []
        for root in roots:
            rst_lines.extend(documenter.render(root))

        if not rst_lines:
            return []
        container = nodes.section()
        container.document = self.state.document
        nested_parse_with_titles(
            self.state, StringList(rst_lines, source="<autosvsummary>"), container
        )
        return container.children


AUTODOC_DIRECTIVES = {
    "autosvpackage": AutoSvPackageDirective,
    "autosvclass": AutoSvClassDirective,
    "autosvmodule": AutoSvModuleDirective,
    "autosvfunction": AutoSvFunctionDirective,
    "autosvtask": AutoSvTaskDirective,
    "autosvsummary": AutoSvSummaryDirective,
}
