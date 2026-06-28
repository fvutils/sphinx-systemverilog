"""Generate reStructuredText for SvObjects, emitting ``sv:*`` domain directives.

This is the autodoc engine: it mirrors ``sphinx.ext.autodoc`` conceptually
(member discovery + options + a docstring-processing event) but operates on the
normalized :class:`~sphinx_systemverilog.model.objects.SvObject` model rather
than live Python objects.  Output is RST text that the directive layer
nested-parses, so all rendering/cross-referencing flows through the ``sv`` domain.
"""

from __future__ import annotations

from typing import Any

from ..docparse import get_parser_for
from ..model.objects import SvObject

INDENT = "   "

#: Directive option lines emitted for an object, by attribute.
_MEMBER_ORDERS = ("source", "alpha", "groups")


class SvDocumenter:
    """Render one :class:`SvObject` (and, optionally, its members) to RST."""

    def __init__(
        self,
        app: Any,
        options: dict[str, Any],
        default_style: str,
        index: Any = None,
    ):
        self.app = app
        self.options = options
        self.default_style = default_style
        self.index = index

    # -- public ---------------------------------------------------------------

    def render(self, obj: SvObject, level: int = 0) -> list[str]:
        lines: list[str] = []
        indent = INDENT * level
        directive = f".. sv:{obj.kind}:: {obj.signature or obj.name}"
        lines.append(indent + directive)

        for opt in self._option_lines(obj):
            lines.append(indent + INDENT + opt)
        lines.append("")

        for doc_line in self._doc_lines(obj):
            lines.append((indent + INDENT + doc_line).rstrip())
        lines.append("")

        if obj.kind == "class" and self.options.get("show-inheritance"):
            qn = obj.qualified_name or obj.name
            lines.append(f"{indent}{INDENT}.. sv:inheritance-diagram:: {qn}")
            lines.append("")

        if self._wants_members(obj):
            shown = [
                c for c in self._ordered_members(obj) if not self._skip_member(obj, c)
            ]
            lines.extend(self._render_members(shown, indent, level))
            lines.extend(self._render_inherited(obj, indent, level))
        return lines

    def _render_inherited(
        self, obj: SvObject, indent: str, level: int
    ) -> list[str]:
        if obj.kind != "class" or not self.options.get("inherited-members"):
            return []
        if self.index is None or not obj.extends:
            return []
        lines: list[str] = []
        member_indent = indent + INDENT
        own = {c.name for c in obj.children}
        seen = set(own)
        base_name = obj.extends
        while base_name:
            base = self.index.get(base_name)
            if base is None:
                break
            inherited = [
                c for c in base.children
                if c.name not in seen and not self._skip_member(base, c)
            ]
            seen.update(c.name for c in base.children)
            if inherited:
                lines.append(f"{member_indent}.. rubric:: Inherited from {base.name}")
                lines.append("")
                for child in inherited:
                    lines.extend(self.render(child, level + 1))
            base_name = base.extends
        return lines

    def _render_members(
        self, members: list[SvObject], indent: str, level: int
    ) -> list[str]:
        lines: list[str] = []
        member_indent = indent + INDENT
        current_group = object()  # sentinel distinct from any real group
        grouped = any(m.group for m in members)
        for child in members:
            if grouped and child.group != current_group:
                current_group = child.group
                if current_group:
                    lines.append(f"{member_indent}.. rubric:: {current_group}")
                    lines.append("")
            lines.extend(self.render(child, level + 1))
        return lines

    # -- options & docs -------------------------------------------------------

    #: Kinds whose signature already embeds type/direction, so qualifiers are
    #: not emitted separately to avoid duplication.
    _SELF_DESCRIBING = {"port", "parameter", "typedef"}

    def _option_lines(self, obj: SvObject) -> list[str]:
        opts: list[str] = []
        module = _module_of(obj)
        if module:
            opts.append(f":module: {module}")
        if obj.kind not in self._SELF_DESCRIBING:
            quals = [q for q in obj.qualifiers if q != "virtual"]
            if "virtual" in obj.qualifiers:
                opts.append(":virtual:")
            if quals:
                opts.append(":qualifiers: " + " ".join(quals))
        if obj.extends:
            opts.append(f":extends: {obj.extends}")
        if obj.location and obj.location.is_valid:
            opts.append(f":source: {obj.location.file}:{obj.location.line}")
        return opts

    def _doc_lines(self, obj: SvObject) -> list[str]:
        style = obj.doc_style or self.default_style
        parser = get_parser_for(style, obj.raw_doc or "")
        parsed = parser.parse(obj.raw_doc or "")
        lines = parsed.as_rst()
        # Allow user post-processing (mirrors autodoc-process-docstring).
        result = self.app.emit_firstresult(
            "sv-autodoc-process-doc", obj.kind, obj.qualified_name or obj.name,
            obj, self.options, lines,
        )
        if isinstance(result, list):
            lines = result
        return lines

    # -- member handling ------------------------------------------------------

    def _wants_members(self, obj: SvObject) -> bool:
        if not obj.is_scope or not obj.children:
            return False
        return self.options.get("members") is not None

    def _ordered_members(self, obj: SvObject) -> list[SvObject]:
        order = self.options.get("member-order", "source")
        members = list(obj.children)
        if order == "alpha":
            members.sort(key=lambda m: m.name)
        elif order == "groups":
            members.sort(key=lambda m: (m.group or "", m.location.line if m.location else 0))
        # 'source' keeps the builder's line-sorted order.
        return members

    def _skip_member(self, parent: SvObject, child: SvObject) -> bool:
        members = self.options.get("members")
        # An explicit member list restricts output to those names.
        if isinstance(members, (list, tuple)) and members and child.name not in members:
            return True
        if child.name in (self.options.get("exclude-members") or ()):
            return True
        # Undocumented leaf members are hidden unless :undoc-members: is set.
        # Ports, parameters and coverpoints are structural API and always shown.
        structural = child.kind in ("port", "parameter", "coverpoint")
        default_skip = (
            not child.is_documented
            and not child.is_scope
            and not structural
            and not self.options.get("undoc-members")
        )
        return self._emit_skip(parent, child, default_skip)

    def _emit_skip(self, parent: SvObject, child: SvObject, default: bool) -> bool:
        results = self.app.emit(
            "sv-autodoc-skip-member", child.kind,
            child.qualified_name or child.name, child, self.options, default,
        )
        for r in results:
            if r is not None:
                return bool(r)
        return default


def _module_of(obj: SvObject) -> str | None:
    qn = obj.qualified_name
    if not qn or "::" not in qn:
        return None
    return qn.rsplit("::", 1)[0]
