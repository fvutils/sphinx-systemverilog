"""The ``sv`` Sphinx domain: object directives, roles, and the object index.

This is the manual surface (``.. sv:class::`` etc.) that the autodoc layer emits
into.  It owns cross-reference resolution and the per-build object inventory.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.docfields import Field, GroupedField, TypedField
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

    #: Field handling, mirroring the Python domain.  Without this, ``:param x:``
    #: renders as a bare docutils field ("Param x:") rather than being collected
    #: under a single "Parameters" heading, and every dialect that produces
    #: fields -- Doxygen ``@param``, NaturalDocs ``Parameters:`` -- looks
    #: unstructured next to the rest of a Sphinx doc set.
    doc_field_types = [
        TypedField(
            "parameter",
            label="Parameters",
            names=("param", "parameter", "arg", "argument"),
            typerolename="obj",
            typenames=("paramtype", "type"),
            can_collapse=True,
        ),
        Field(
            "returnvalue", label="Returns", has_arg=False,
            names=("returns", "return"),
        ),
        Field(
            "returntype", label="Return type", has_arg=False,
            names=("rtype",),
        ),
        GroupedField(
            "throws", label="Throws", names=("throws", "throw", "exception"),
            can_collapse=True,
        ),
        GroupedField(
            "seealso", label="See also", names=("see", "seealso"),
            can_collapse=True,
        ),
    ]

    def handle_signature(self, sig: str, signode: addnodes.desc_signature) -> str:
        """Parse a signature into nodes and return the lookup name.

        *sig* is the rendered SystemVerilog declaration (e.g.
        ``function bit parity(bit[7:0] data)``).  The lookup name is the
        identifier - either an explicit ``name`` after the qualifiers, or the
        whole signature when it is a bare identifier.
        """
        qualifiers = self.options.get("qualifiers", "")
        # ``virtual`` is a flag option, so docutils stores None when it is
        # *present*; test for membership, not truthiness.
        if "virtual" in self.options:
            qualifiers = ("virtual " + qualifiers).strip()

        name = _signature_name(sig, self.object_kind)
        # Stash the resolved name for the TOC hooks: Sphinx calls
        # ``_object_hierarchy_parts()`` before ``add_target_and_index()`` has
        # populated ``names``/``ids``, so those are still empty at that point.
        signode["sv_fullname"] = self._fullname(name)
        signode["sv_kind"] = self.object_kind

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
                signode += _type_node(type_part, self.env)
                signode += addnodes.desc_sig_space()
            signode += addnodes.desc_name(name, name)
            if tail:
                # Dimensions bind to the name; anything else is set off by a space.
                sep = "" if tail.startswith("[") else " "
                signode += addnodes.desc_annotation(sep + tail, sep + tail)
        else:
            return_type = _signature_return(sig, name, self.object_kind)
            if return_type:
                signode += _type_node(return_type, self.env)
                signode += addnodes.desc_sig_space()
            signode += addnodes.desc_name(name, name)
            self._add_arglist(sig, name, signode)

        extends = self.options.get("extends")
        if extends:
            signode += addnodes.desc_annotation("  extends ", "  extends ")
            signode += _type_xref(extends, self.env)

        self._add_source_link(signode)
        return name

    def _add_arglist(
        self, sig: str, name: str, signode: addnodes.desc_signature
    ) -> None:
        """Render the argument list as a real parameter list where possible.

        A signature the parser does not understand falls back to the opaque
        string it used to emit: losing the per-parameter markup costs polish,
        never content (D2).
        """
        if self.object_kind not in ("function", "task"):
            return
        args = _parse_arglist(sig)
        if args is None:
            extra = _signature_extra(sig, name, self.object_kind)
            if extra:
                signode += addnodes.desc_addname(extra, extra)
            return

        paramlist = addnodes.desc_parameterlist()
        for arg in args:
            node = _argument_node(arg, self.env)
            if node is None:
                # One unparseable argument invalidates the whole list, or the
                # rendering would silently drop it.
                extra = _signature_extra(sig, name, self.object_kind)
                if extra:
                    signode += addnodes.desc_addname(extra, extra)
                return
            paramlist += node
        signode += paramlist

    def _fullname(self, name: str) -> str:
        """``module::name``, the key used for the anchor and the TOC entry."""
        module = self.options.get("module")
        return f"{module}::{name}" if module else name

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
        fullname = self._fullname(name)
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

    def _object_hierarchy_parts(self, sig_node) -> tuple[str, ...]:
        fullname = sig_node.get("sv_fullname")
        if not fullname:
            # Hand-built signodes (or a subclass that skipped handle_signature)
            # may only have the target names Sphinx assigned later.
            names = sig_node.get("names") or []
            fullname = names[0] if names else ""
        return tuple(p for p in fullname.split("::") if p)

    def _toc_entry_name(self, sig_node) -> str:
        parts = sig_node.get("_toc_parts") or ()
        if not parts:
            return ""

        config = self.env.config
        parens = ""
        if config.add_function_parentheses and sig_node.get("sv_kind") in (
            "function", "task"
        ):
            parens = "()"

        *parents, name = parts
        mode = config.toc_object_entries_show_parents
        if mode == "domain":
            # The domain decides how much to show.  Mirroring the Python
            # domain, that is the name qualified by its enclosing declarations
            # but *not* by the package -- the package is the SV analogue of a
            # Python module, and it heads the parts tuple.
            return "::".join([*parents[1:], name + parens])
        if mode == "hide":
            return name + parens
        if mode == "all":
            return "::".join([*parents, name + parens])
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
        # '<type> ... <name>[dims] [= default]' -> last token before any '=',
        # minus any unpacked dimensions, which belong to the declarator rather
        # than to the name used for lookup and indexing.
        head = sig.split("=", 1)[0].strip()
        last = head.split()[-1] if head.split() else sig
        return last.split("[", 1)[0] or last
    return sig.split()[0] if sig.split() else sig


def _signature_extra(sig: str, name: str, kind: str) -> str:
    if kind in ("function", "task") and "(" in sig:
        return "(" + sig.split("(", 1)[1]
    return ""


def _signature_return(sig: str, name: str, kind: str) -> str:
    """Extract a function's return type from ``function <type> <name>(...)``.

    Tasks have no return type.  The leading ``function`` keyword is dropped -
    the kind label already supplies it - as are any qualifiers that a
    hand-written signature happens to carry inline (they are rendered from the
    ``:virtual:`` / ``:qualifiers:`` options instead).
    """
    if kind != "function":
        return ""
    head = sig.split("(", 1)[0].strip()
    tokens = head.split()
    if len(tokens) < 2 or tokens[-1] != name:
        return ""
    middle = [t for t in tokens[:-1] if t not in _SIGNATURE_LEADERS]
    return " ".join(middle)


#: Words that may lead a hand-written subroutine signature but are not part of
#: the return type.
_SIGNATURE_LEADERS = frozenset(
    {"function", "task", "virtual", "static", "pure", "extern",
     "local", "protected"}
)


#: Leading keywords of an argument declaration that state how it is passed
#: rather than what its type is.
_ARG_DIRECTIONS = ("input", "output", "inout", "ref", "const", "var")

_OPENERS = "([{"
_CLOSERS = ")]}"


def _split_top_level(text: str, sep: str) -> list[str] | None:
    """Split *text* on *sep*, ignoring separators nested in brackets or strings.

    Returns ``None`` if the brackets do not balance -- a naive ``split(",")``
    would mangle a default like ``'{1, 2}`` into two arguments.
    """
    parts: list[str] = []
    depth = 0
    in_string = False
    current: list[str] = []
    escaped = False
    for ch in text:
        if in_string:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth -= 1
            if depth < 0:
                return None
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if depth != 0 or in_string:
        return None
    parts.append("".join(current))
    return parts


def _parse_arglist(sig: str) -> list[str] | None:
    """The argument texts of ``... name(a, b = '{1, 2})``, or ``None``.

    ``None`` means "do not understand this" -- an empty list means a genuine
    zero-argument subroutine, and the two must not be confused.
    """
    start = sig.find("(")
    if start < 0 or not sig.rstrip().endswith(")"):
        return None
    inner = sig.rstrip()[start + 1 : -1]
    parts = _split_top_level(inner, ",")
    if parts is None:
        return None
    if len(parts) == 1 and not parts[0].strip():
        return []
    if any(not p.strip() for p in parts):
        return None
    return [p.strip() for p in parts]


def _parse_argument(text: str) -> tuple[str, str, str, str, str] | None:
    """Split one argument into ``(direction, type, name, dims, default)``.

    ``None`` if it does not look like a declaration at all.
    """
    head, sep, default = "", "", ""
    split = _split_top_level(text, "=")
    if split is None:
        return None
    if len(split) == 2:
        head, sep, default = split[0], "=", split[1]
    elif len(split) == 1:
        head = split[0]
    else:
        return None

    tokens = head.split()
    direction: list[str] = []
    while tokens and tokens[0] in _ARG_DIRECTIONS:
        direction.append(tokens.pop(0))
    # Unpacked dimensions may be written apart from the declarator
    # (``bit [7:0] q [3]``); either way they bind to the name.
    trailing: list[str] = []
    while tokens and tokens[-1].startswith("["):
        trailing.insert(0, tokens.pop())
    if not tokens:
        return None
    declarator = tokens.pop()
    name, bracket, rest = declarator.partition("[")
    dims = (bracket + rest if bracket else "") + "".join(trailing)
    if not _IDENTIFIER.match(name):
        return None
    return (
        " ".join(direction),
        " ".join(tokens),
        name,
        dims,
        default.strip() if sep else "",
    )


def _type_node(text: str, env: Any) -> nodes.Node:
    """Render a type as a cross-reference where one is possible."""
    node = _type_xref(text, env)
    if isinstance(node, nodes.Text):
        return addnodes.desc_sig_keyword_type(text, text)
    return node


def _argument_node(text: str, env: Any) -> addnodes.desc_parameter | None:
    parsed = _parse_argument(text)
    if parsed is None:
        return None
    direction, type_text, name, dims, default = parsed
    param = addnodes.desc_parameter()
    if direction:
        param += addnodes.desc_sig_keyword(direction, direction)
        param += addnodes.desc_sig_space()
    if type_text:
        param += _type_node(type_text, env)
        param += addnodes.desc_sig_space()
    param += addnodes.desc_sig_name(name, name)
    if dims:
        param += addnodes.desc_sig_punctuation(dims, dims)
    if default:
        param += addnodes.desc_sig_space()
        param += addnodes.desc_sig_operator("=", "=")
        param += addnodes.desc_sig_space()
        param += nodes.inline(default, default, classes=["default_value"])
    return param


#: SystemVerilog built-in types and type qualifiers.  These are keywords, not
#: documented objects, so a signature must not emit a cross-reference for them:
#: it would put an unresolvable node in nearly every signature.
_BUILTIN_TYPES = frozenset(
    {
        "bit", "logic", "reg", "byte", "shortint", "int", "longint", "integer",
        "time", "real", "shortreal", "realtime", "string", "chandle", "event",
        "void", "signed", "unsigned", "var", "wire", "genvar", "supply0",
        "supply1", "tri", "wand", "wor", "type",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*(::[A-Za-z_]\w*)*$")


def _xref_target(text: str) -> str:
    """The name to resolve for a type in a signature, or ``""`` for none.

    Packed dimensions and parameterization are stripped before the check
    (``logic[7:0]`` resolves ``logic``, which the built-in filter then drops);
    anything that is not a plain identifier is left as text.
    """
    target = text.split("[", 1)[0].split("#", 1)[0].strip()
    if not target or target in _BUILTIN_TYPES:
        return ""
    return target if _IDENTIFIER.match(target) else ""


def _type_xref(text: str, env: Any) -> nodes.Node:
    """A type reference node for *text*, or a plain text node if it is not one.

    The reference is *inferred* rather than author-written, so it uses the
    generic ``obj`` reftype, which the domain resolves silently: an undocumented
    type degrades to plain text instead of warning.
    """
    target = _xref_target(text)
    if not target:
        return nodes.Text(text)
    node = addnodes.pending_xref(
        "",
        nodes.Text(text),
        refdomain="sv",
        reftype="obj",
        reftarget=target,
        refexplicit=False,
        refwarn=False,
    )
    node["refdoc"] = env.docname
    return node


def _split_data_signature(sig: str, name: str) -> tuple[str, str]:
    """Split ``<type> <name>[dims] [= default]`` into (type_part, tail).

    Unpacked dimensions stay with the declarator, so they lead the tail and are
    rendered flush against the name (``q[$]``, not ``q [$]``).
    """
    sig = sig.strip()
    head, sep, default = sig.partition("=")
    tokens = head.split()
    type_part = " ".join(tokens[:-1]) if len(tokens) > 1 else ""
    declarator = tokens[-1] if tokens else ""
    dims = declarator[declarator.index("["):] if "[" in declarator else ""
    tail = dims
    if sep:
        tail = (tail + " = " + default.strip()).strip()
    return type_part, tail
