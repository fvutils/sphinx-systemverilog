"""The ``sv`` Sphinx domain: object directives, roles, and the object index.

This is the manual surface (``.. sv:class::`` etc.) that the autodoc layer emits
into.  It owns cross-reference resolution and the per-build object inventory.
"""

from __future__ import annotations

from typing import Any, Iterable

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.nodes import make_refnode

logger = logging.getLogger(__name__)

#: directive name -> (display label, role names that point at it)
OBJECT_TYPES = {
    "package": ("package", ("package", "obj")),
    "module": ("module", ("module", "mod", "obj")),
    "interface": ("interface", ("interface", "obj")),
    "program": ("program", ("program", "obj")),
    "class": ("class", ("class", "type", "obj")),
    "function": ("function", ("function", "func", "obj")),
    "task": ("task", ("task", "obj")),
    "property": ("property", ("property", "prop", "obj")),
    "port": ("port", ("port", "obj")),
    "parameter": ("parameter", ("parameter", "param", "obj")),
    "typedef": ("typedef", ("typedef", "type", "obj")),
    "macro": ("macro", ("macro", "obj")),
    "covergroup": ("covergroup", ("covergroup", "obj")),
    "coverpoint": ("coverpoint", ("coverpoint", "obj")),
    "constraint": ("constraint", ("constraint", "obj")),
}


class SvObjectDescription(ObjectDescription):
    """Base directive for all ``sv:*`` objects."""

    option_spec = {
        "no-index": directives.flag,
        "no-index-entry": directives.flag,
        "module": directives.unchanged,
        "extends": directives.unchanged,
        "virtual": directives.flag,
        "qualifiers": directives.unchanged,
        "source": directives.unchanged,
    }

    #: The object kind (set per subclass); matches OBJECT_TYPES keys.
    object_kind = "obj"

    def handle_signature(self, sig: str, signode: addnodes.desc_signature) -> str:
        """Parse a signature into nodes and return the lookup name.

        *sig* is the rendered SystemVerilog declaration (e.g.
        ``function bit parity(bit[7:0] data)``).  The lookup name is the
        identifier - either an explicit ``name`` after the qualifiers, or the
        whole signature when it is a bare identifier.
        """
        qualifiers = self.options.get("qualifiers", "")
        if self.options.get("virtual"):
            qualifiers = ("virtual " + qualifiers).strip()

        name = _signature_name(sig, self.object_kind)

        if qualifiers:
            signode += addnodes.desc_annotation(
                qualifiers + " ", qualifiers + " "
            )
        # Port/parameter/typedef signatures start with their own keyword
        # (input/output/parameter/typedef), so the kind label is redundant.
        if self.object_kind not in _KEYWORD_LED_KINDS:
            kind_label = OBJECT_TYPES[self.object_kind][0]
            signode += addnodes.desc_annotation(kind_label + " ", kind_label + " ")

        if self.object_kind in _DATA_KINDS:
            type_part, tail = _split_data_signature(sig, name)
            if type_part:
                signode += addnodes.desc_annotation(
                    type_part + " ", type_part + " "
                )
            signode += addnodes.desc_name(name, name)
            if tail:
                signode += addnodes.desc_annotation(" " + tail, " " + tail)
        else:
            signode += addnodes.desc_name(name, name)
            extra = _signature_extra(sig, name, self.object_kind)
            if extra:
                signode += addnodes.desc_addname(extra, extra)

        extends = self.options.get("extends")
        if extends:
            signode += addnodes.desc_annotation(
                "  extends " + extends, "  extends " + extends
            )

        self._add_source_link(signode)
        return name

    def _add_source_link(self, signode: addnodes.desc_signature) -> None:
        source = self.options.get("source")
        if not source or not getattr(self.env.config, "sv_viewcode", True):
            return
        file_path, _, line_s = source.rpartition(":")
        if not file_path or not line_s.isdigit():
            return
        from . import viewcode

        node = viewcode.make_source_node(self.env, file_path, int(line_s))
        if node is not None:
            signode["_sv_source"] = (file_path, int(line_s))
            signode += node

    def add_target_and_index(
        self, name: str, sig: str, signode: addnodes.desc_signature
    ) -> None:
        module = self.options.get("module")
        fullname = f"{module}::{name}" if module else name
        anchor = "sv-" + fullname.replace("::", "-")
        if anchor not in self.state.document.ids:
            signode["names"].append(fullname)
            signode["ids"].append(anchor)
            self.state.document.note_explicit_target(signode)

        domain: "SystemVerilogDomain" = self.env.get_domain("sv")  # type: ignore[assignment]
        if "no-index" not in self.options:
            domain.note_object(fullname, self.object_kind, anchor, self.env.docname)

        source = signode.get("_sv_source")
        if source:
            from . import viewcode

            viewcode.record(self.env, source[0], source[1], anchor)

        if "no-index" not in self.options and "no-index-entry" not in self.options:
            label = OBJECT_TYPES[self.object_kind][0]
            self.indexnode["entries"].append(
                ("single", f"{name} ({label})", anchor, "", None)
            )

    def _object_hierarchy_parts(self, sig_node):
        if "names" in sig_node and sig_node["names"]:
            return tuple(sig_node["names"][0].split("::"))
        return ()

    def _toc_entry_name(self, sig_node) -> str:
        if sig_node.get("_toc_parts"):
            return sig_node["_toc_parts"][-1]
        return ""


def _make_directive(kind: str) -> type:
    return type(
        f"Sv{kind.capitalize()}Directive",
        (SvObjectDescription,),
        {"object_kind": kind},
    )


class SystemVerilogDomain(Domain):
    """Domain for SystemVerilog objects."""

    name = "sv"
    label = "SystemVerilog"

    object_types = {
        kind: ObjType(label, *roles)
        for kind, (label, roles) in OBJECT_TYPES.items()
    }
    directives = {kind: _make_directive(kind) for kind in OBJECT_TYPES}
    roles = {
        role: XRefRole()
        for role in {r for _, rs in OBJECT_TYPES.values() for r in rs}
    }

    initial_data: dict[str, Any] = {"objects": {}}

    @property
    def objects(self) -> dict[str, tuple[str, str, str]]:
        # fullname -> (docname, anchor, kind)
        return self.data.setdefault("objects", {})

    def note_object(self, fullname: str, kind: str, anchor: str, docname: str) -> None:
        self.objects[fullname] = (docname, anchor, kind)

    def clear_doc(self, docname: str) -> None:
        for fullname, (dn, _anchor, _kind) in list(self.objects.items()):
            if dn == docname:
                del self.objects[fullname]

    def merge_domaindata(self, docnames: Iterable[str], otherdata: dict) -> None:
        for fullname, data in otherdata.get("objects", {}).items():
            if data[0] in docnames:
                self.objects[fullname] = data

    def resolve_xref(
        self, env, fromdocname, builder, typ, target, node, contnode
    ):
        match = self._find(target)
        if match is None:
            # The generic ``obj`` role is also what NaturalDocs ``<xref>`` spans
            # are converted to; those are inferred, not author-written, so they
            # degrade silently to text.  Explicit typed roles warn.
            if typ != "obj":
                candidates = self.candidates(target)
                detail = ""
                if candidates:
                    detail = " (ambiguous; candidates: %s)" % ", ".join(
                        sorted(candidates)
                    )
                logger.warning(
                    "sphinx-systemverilog: cannot resolve sv:%s reference %r%s",
                    typ, target, detail, type="systemverilog",
                    location=node,
                )
            return None
        fullname, (docname, anchor, _kind) = match
        return make_refnode(builder, fromdocname, docname, anchor, contnode, fullname)

    def candidates(self, target: str) -> list[str]:
        """Fully-qualified names whose final segment matches *target*."""
        leaf = target.replace(".", "::").split("::")[-1]
        return [fn for fn in self.objects if fn.split("::")[-1] == leaf]

    def resolve_any_xref(
        self, env, fromdocname, builder, target, node, contnode
    ):
        match = self._find(target)
        if match is None:
            return []
        fullname, (docname, anchor, kind) = match
        refnode = make_refnode(
            builder, fromdocname, docname, anchor, contnode, fullname
        )
        return [(f"sv:{kind}", refnode)]

    def _find(self, target: str):
        if target in self.objects:
            return target, self.objects[target]
        alt = target.replace(".", "::")
        if alt in self.objects:
            return alt, self.objects[alt]
        # Bare-name fallback: unique suffix match.
        suffix = "::" + target
        hits = [fn for fn in self.objects if fn == target or fn.endswith(suffix)]
        if len(hits) == 1:
            return hits[0], self.objects[hits[0]]
        return None

    def get_objects(self):
        for fullname, (docname, anchor, kind) in self.objects.items():
            yield (fullname, fullname, kind, docname, anchor, 1)


#: Data-like kinds rendered as ``<type> <name> [= default]``.
_DATA_KINDS = {
    "property", "port", "parameter", "typedef",
    "covergroup", "coverpoint", "constraint",
}

#: Kinds whose signature already begins with a SystemVerilog keyword, so the
#: directive's kind label would be redundant.
_KEYWORD_LED_KINDS = {
    "port", "parameter", "typedef", "covergroup", "coverpoint", "constraint",
}


def _signature_name(sig: str, kind: str) -> str:
    sig = sig.strip()
    if not sig:
        return ""
    if kind in ("function", "task"):
        head = sig.split("(", 1)[0]
        return head.split()[-1] if head.split() else sig
    if kind in _DATA_KINDS:
        # '<type> ... <name> [= default]' -> last token before any '='.
        head = sig.split("=", 1)[0].strip()
        return head.split()[-1] if head.split() else sig
    return sig.split()[0] if sig.split() else sig


def _signature_extra(sig: str, name: str, kind: str) -> str:
    if kind in ("function", "task") and "(" in sig:
        return "(" + sig.split("(", 1)[1]
    return ""


def _split_data_signature(sig: str, name: str) -> tuple[str, str]:
    """Split ``<type> <name> [= default]`` into (type_part, tail)."""
    sig = sig.strip()
    head, sep, default = sig.partition("=")
    tokens = head.split()
    type_part = " ".join(tokens[:-1]) if len(tokens) > 1 else ""
    tail = ("= " + default.strip()) if sep else ""
    return type_part, tail
