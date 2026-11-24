"""Build the normalized :class:`SvObject` model from SystemVerilog source.

The builder uses pyslang's elaborated AST for clean scope iteration, but is
deliberately tolerant of unresolved references (e.g. a base class defined in
another, unparsed file): parse diagnostics are collected, never fatal.  Phase 1
targets self-contained packages; Phase 2 adds include/define-driven elaboration.
"""

from __future__ import annotations

import os
import re
from fnmatch import fnmatchcase
from typing import Any, Iterable

from .comments import clean_comment_block, doc_above_line, split_leading_trivia
from .locations import is_real_location, macro_chain, resolve_location
from .objects import (
    KIND_CLASS,
    KIND_CONSTRAINT,
    KIND_COVERGROUP,
    KIND_COVERPOINT,
    KIND_FUNCTION,
    KIND_INTERFACE,
    KIND_MACRO,
    KIND_MODULE,
    KIND_PACKAGE,
    KIND_PARAMETER,
    KIND_PORT,
    KIND_PROGRAM,
    KIND_PROPERTY,
    KIND_TASK,
    KIND_TYPEDEF,
    SvObject,
)

# pyslang imports are kept local to this module (the pyslang isolation boundary).
import pyslang
from pyslang.ast import Compilation, SymbolKind
from pyslang.parsing import Token
from pyslang.syntax import SyntaxTree


#: Diagnostics an ``sv_external`` pattern silences for the names it matches.
#: ``UndeclaredIdentifier`` is how slang reports a class used as a type
#: (``axi_vip_cfg cfg;``); ``UnknownPackage``, a VIP package import.
_EXTERNAL_CODES = frozenset({"UnknownModule", "UnknownInterface", "UnknownClass", "UnknownClassOrPackage",
                             "UnknownPackage", "UndeclaredIdentifier"})


class ModelBuilder:
    """Parse SystemVerilog and emit a list of top-level :class:`SvObject`."""

    def __init__(
        self,
        doc_style: str = "native",
        include_dirs: Iterable[str] | None = None,
        defines: dict[str, str] | None = None,
        nodocs_policy: str = "include",
        document_macros: bool = True,
        external: Iterable[str] | None = None,
        external_files: dict[str, str] | None = None,
        links: Iterable[str] | None = None,
    ) -> None:
        self.doc_style = doc_style
        self.include_dirs = list(include_dirs or [])
        self.defines = dict(defines or {})
        #: How to treat UVM ``-- NODOCS --`` blocks: "include" the prose or "skip".
        self.nodocs_policy = nodocs_policy
        #: Whether to extract ``\\`define`` macros.
        self.document_macros = document_macros
        #: ``sv_external`` glob patterns: names defined outside the sources.
        self.external = list(external or [])
        #: ``sv_external_sources``: absolute path -> origin label.  Parsed like
        #: any source; what they declare is flagged ``external``.
        self.external_files = {os.path.abspath(k): v for k, v in (external_files or {}).items()}
        #: The live pyslang ``Compilation``, retained after :meth:`_build` so the
        #: instance hierarchy can be walked lazily.  Never walked during a build.
        self.compilation: Any = None
        #: The ``SourceManager`` matching :attr:`compilation`.
        self.source_manager: Any = None
        #: Error/fatal diagnostics rendered as strings; surfaced as warnings.
        self.diagnostics: list[str] = []
        #: Link databases (``svdb build --link``): names the sources use but do
        #: not define are compiled from declarations generated from these.
        self.links = list(links or [])
        #: What the compile took from each link database (``Link`` records).
        self.linked: list[Any] = []
        #: Count of suppressed non-error (lint) diagnostics; surfaced as info.
        self.suppressed_count: int = 0
        self._nd_index = None

    # -- entry points ---------------------------------------------------------

    def build_from_text(self, text: str, name: str = "source") -> list[SvObject]:
        tree = SyntaxTree.fromText(text, name)
        return self._build([tree])

    def build_from_files(self, paths: Iterable[str]) -> list[SvObject]:
        paths = [str(p) for p in paths]
        sm, options = self._parse_options()
        linker = None
        if self.links:
            from ..frontend.link import Linker

            if sm is None:
                sm, options = pyslang.SourceManager(), pyslang.Bag([pyslang.parsing.PreprocessorOptions()])
            linker = Linker(self.links, self.include_dirs)
            linker.preinclude(sm, paths)
        trees = []
        for p in paths:
            if sm is not None:
                trees.append(SyntaxTree.fromFile(p, sm, options))
            else:
                trees.append(SyntaxTree.fromFile(p))
        if linker is None:
            return self._build(trees)
        try:
            comp = linker.link(sm, trees)
            self.linked = linker.used()
            self.diagnostics.extend(linker.errors)
            return self._build(trees, linked=linker.trees, comp=comp)
        finally:
            linker.close()

    def _parse_options(self):
        """Build a shared SourceManager + options Bag honoring include dirs/defines.

        Returns ``(None, None)`` when no include dirs or defines are configured,
        so simple cases keep the default single-file parsing path.
        """
        if not self.include_dirs and not self.defines:
            return None, None
        po = pyslang.parsing.PreprocessorOptions()
        if self.include_dirs:
            po.additionalIncludePaths = list(self.include_dirs)
        if self.defines:
            po.predefines = [f"{k}={v}" for k, v in self.defines.items()]
        sm = pyslang.SourceManager()
        for inc in self.include_dirs:
            try:
                sm.addUserDirectories(str(inc))
            except Exception:
                pass
        return sm, pyslang.Bag([po])

    # -- core -----------------------------------------------------------------

    def _build(self, trees: list[Any], linked: list[Any] = (), comp: Any = None) -> list[SvObject]:
        """*linked* trees (generated from link databases) are compiled, not
        documented; *comp*, when given, already holds every tree."""
        source_manager = trees[0].sourceManager if trees else None
        if comp is None:
            comp = Compilation()
            for tree in [*trees, *linked]:
                comp.addSyntaxTree(tree)
        self._collect_diagnostics(comp)
        self._build_nd_index(trees, source_manager)

        roots: list[SvObject] = []
        for pkg in comp.getPackages():
            if pkg.name in ("std", "$unit") or _is_linked(source_manager, pkg.location):
                continue
            obj = self._build_scope(
                pkg, KIND_PACKAGE, source_manager, pkg.name, include_inline=True
            )
            if obj is not None:
                roots.append(obj)
        # Modules/interfaces/programs (Phase 2 fleshes out ports/params).
        for defn in comp.getDefinitions():
            kind = _DEFINITION_KINDS.get(str(getattr(defn, "definitionKind", "")))
            if kind is None or _is_linked(source_manager, defn.location):
                continue
            obj = self._build_scope(
                defn, kind, source_manager, defn.name, include_inline=True
            )
            if obj is not None:
                roots.append(obj)

        if self.document_macros:
            roots.extend(self._collect_macros(trees))
        # Deliberately *not* walking the instance hierarchy here.  ``getRoot()``
        # is free but touching each ``inst.body`` is not, and most builds never
        # render a structural directive.  The compilation is retained instead so
        # ``model.structure.StructureProvider`` can walk it on demand.
        self.compilation = comp
        self.source_manager = source_manager
        return roots

    def _collect_macros(self, trees: list[Any]) -> list[SvObject]:
        """Extract ``\\`define`` macros (with doc comments) from the token stream."""
        from .ndblocks import _iter_tokens
        from pyslang.parsing import TriviaKind

        macros: list[SvObject] = []
        seen: set[tuple[str, int]] = set()
        for tree in trees:
            sm = tree.sourceManager
            root = getattr(tree, "root", None)
            if root is None:
                continue
            for token in _iter_tokens(root):
                for tr in token.trivia:
                    if tr.kind != TriviaKind.Directive:
                        continue
                    syn = _trivia_syntax(tr)
                    if syn is not None and type(syn).__name__ == \
                            "DefineDirectiveSyntax":
                        macro = self._build_macro(syn, sm, seen)
                        if macro is not None:
                            macros.append(macro)
        return macros

    def _build_macro(self, syn: Any, sm: Any, seen: set) -> SvObject | None:
        name = syn.name.valueText
        loc = resolve_location(sm, syn.name.location)
        key = (name, loc.line if loc else 0, loc.file if loc else "")
        if key in seen:
            return None
        seen.add(key)
        obj = SvObject(
            kind=KIND_MACRO, name=name, qualified_name=name,
            signature=_macro_signature(syn),
            location=loc,
            raw_doc=_token_leading_doc(syn.getFirstToken(), include_inline=True),
            doc_style=self.doc_style,
        )
        self._apply_nd(obj, syn)
        return obj

    def _build_nd_index(self, trees: list[Any], sm: Any) -> None:
        """Build the NaturalDocs detached-block index when the dialect needs it."""
        if self.doc_style not in ("naturaldocs", "auto"):
            return
        from .ndblocks import NDBlockIndex, build_nd_index

        index = NDBlockIndex()
        for tree in trees:
            build_nd_index(tree, tree.sourceManager, index)
        self._nd_index = index if not index.is_empty else None

    def _apply_nd(self, obj: SvObject, sym: Any) -> None:
        """Override doc/group from the ND block index when applicable."""
        if self._nd_index is None:
            return
        line = obj.location.line if obj.location else None
        file = obj.location.file if obj.location else None
        block = self._nd_index.lookup(obj.name, line, file)
        if block is not None:
            if self.nodocs_policy == "skip" and block.nodocs:
                obj.raw_doc = None
            else:
                obj.raw_doc = block.raw
        group = self._nd_index.group_for(line, file)
        if group and not obj.is_scope:
            obj.group = group

    def _collect_diagnostics(self, comp: Any) -> None:
        """Collect parse/elaboration diagnostics.

        Only error/fatal diagnostics are surfaced individually (they may mean
        the docs are incomplete); the many benign lint-style warnings UVM emits
        are counted and summarized so the build log is not flooded.
        """
        try:
            diags = comp.getAllDiagnostics()
        except Exception:
            return
        engine = pyslang.DiagnosticEngine(comp.sourceManager)
        suppressed = 0
        for diag in diags:
            if self._is_external(diag) or _is_linked(comp.sourceManager, diag.location):
                continue        # in generated text: the linker reports those
            try:
                severity = engine.getSeverity(diag.code, diag.location)
            except Exception:
                severity = None
            if severity is not None and str(severity) not in (
                "DiagnosticSeverity.Error",
                "DiagnosticSeverity.Fatal",
            ):
                suppressed += 1
                continue
            try:
                self.diagnostics.append(engine.reportAll(comp.sourceManager, [diag]))
            except Exception:
                self.diagnostics.append(str(getattr(diag, "code", diag)))
        self.suppressed_count += suppressed

    def origin_of(self, path: str | None) -> str | None:
        """The ``sv_external_sources`` origin of the file at *path*, or ``None``
        when it is one of the project's own sources."""
        if not path or not self.external_files:
            return None
        return self.external_files.get(os.path.abspath(path))

    def _is_external(self, diag: Any) -> bool:
        """Whether *diag* reports a missing module/class whose name matches an
        ``sv_external`` pattern.  Only those codes, and only matching names: any
        other unknown name still warns."""
        if not self.external or str(diag.code).removeprefix("DiagCode(").rstrip(")") not in _EXTERNAL_CODES:
            return False
        try:
            name = str(diag.args[0])
        except Exception:
            return False
        return any(fnmatchcase(name, p) for p in self.external)

    # -- per-symbol dispatch --------------------------------------------------

    def _build_symbol(
        self, sym: Any, sm: Any, parent_qname: str | None
    ) -> SvObject | None:
        kind = sym.kind
        if kind == SymbolKind.ClassType:
            return self._build_scope(
                sym, KIND_CLASS, sm, _join(parent_qname, sym.name), class_sym=sym
            )
        if kind == SymbolKind.GenericClassDef:
            return self._build_generic_class(sym, sm, parent_qname)
        if kind in (SymbolKind.Subroutine, SymbolKind.MethodPrototype):
            return self._build_subroutine(sym, sm, parent_qname)
        if kind == SymbolKind.ConstraintBlock:
            return self._build_constraint(sym, sm, parent_qname)
        if kind == SymbolKind.CovergroupType:
            return None  # documented via its ClassProperty instance
        if kind in (SymbolKind.ClassProperty, SymbolKind.Variable):
            if _is_covergroup(sym):
                return self._build_covergroup(sym, sm, parent_qname)
            return self._build_property(sym, sm, parent_qname)
        if kind == SymbolKind.TypeAlias:
            return self._build_simple(sym, KIND_TYPEDEF, sm, parent_qname,
                                      signature=_typedef_signature(sym))
        if kind == SymbolKind.Definition:
            mapped = _DEFINITION_KINDS.get(str(getattr(sym, "definitionKind", "")))
            if mapped:
                return self._build_scope(sym, mapped, sm, _join(parent_qname, sym.name))
        return None

    def _build_scope(
        self,
        sym: Any,
        kind: str,
        sm: Any,
        qname: str,
        class_sym: Any | None = None,
        include_inline: bool = False,
    ) -> SvObject | None:
        obj = SvObject(
            kind=kind,
            name=sym.name,
            qualified_name=qname,
            location=resolve_location(sm, sym.location),
            raw_doc=self._leading_doc(sym, include_inline=include_inline, sm=sm),
            doc_style=self.doc_style,
        )
        if class_sym is not None:
            if getattr(class_sym, "isInterface", False):
                obj.qualifiers.append("interface")
            elif getattr(class_sym, "isAbstract", False):
                obj.qualifiers.append("virtual")
            base = getattr(class_sym, "baseClass", None)
            if base is not None and getattr(base, "name", ""):
                obj.extends = base.name
                generic = getattr(base, "genericClass", None) or base
                if _is_linked(sm, getattr(generic, "location", None)):
                    obj.extends_target = getattr(generic, "hierarchicalPath", None) or None
        self._apply_nd(obj, sym)
        if sym.kind == SymbolKind.Definition:
            self._build_module_header(sym, obj, sm, qname)
        else:
            self._build_members(sym, obj, sm, qname)
        return obj

    def _build_members(self, scope: Any, parent: SvObject, sm: Any, qname: str) -> None:
        members: list[SvObject] = []
        trailing: list[list[str]] = []
        order: dict[int, tuple] = {}
        for sym in _iter_scope(scope):
            if not _has_real_location(sym, sm):
                continue
            child = self._build_symbol(sym, sm, qname)
            if child is None:
                continue
            child.from_macros = macro_chain(sm, getattr(sym, "location", None))
            order[id(child)] = _stream_key(sm, getattr(sym, "location", None))
            members.append(child)
            trailing.append(self._trailing_for(sym))

        # Re-assign each member's leading trailing-comment to the *previous*
        # sibling that has no doc of its own (the inline `; // ...` case).
        for i in range(1, len(members)):
            prev = members[i - 1]
            inline = trailing[i]
            if inline and not prev.is_documented:
                prev.raw_doc = clean_comment_block(inline)

        # Source order across `include`d files, not line numbers alone: a
        # package spread over files would otherwise put uses before
        # declarations.
        members.sort(key=lambda m: order[id(m)])
        parent.children = members

    def _build_constraint(
        self, sym: Any, sm: Any, parent_qname: str | None
    ) -> SvObject:
        sig = "constraint " + sym.name
        syntax = getattr(sym, "syntax", None)
        if syntax is not None:
            sig = _node_source(syntax, sm).split("{", 1)[0].strip() or sig
        return self._build_simple(
            sym, KIND_CONSTRAINT, sm, parent_qname, signature=sig
        )

    def _build_covergroup(
        self, sym: Any, sm: Any, parent_qname: str | None
    ) -> SvObject:
        qname = _join(parent_qname, sym.name)
        # The ClassProperty carries the name; its CovergroupType carries the
        # syntax (and thus the doc comment and the `covergroup` location).
        cgtype = getattr(sym, "type", None)
        doc_sym = cgtype if cgtype is not None and getattr(cgtype, "syntax", None) \
            else sym
        loc = cgtype if cgtype is not None and is_real_location(
            sm, getattr(cgtype, "location", None)) else sym
        obj = SvObject(
            kind=KIND_COVERGROUP, name=sym.name, qualified_name=qname,
            signature="covergroup " + sym.name,
            location=resolve_location(sm, loc.location),
            raw_doc=self._leading_doc(doc_sym), doc_style=self.doc_style,
        )
        self._apply_nd(obj, sym)
        obj.children = self._coverpoints(cgtype, sm, qname)
        return obj

    def _coverpoints(self, cgtype: Any, sm: Any, qname: str) -> list[SvObject]:
        out: list[SvObject] = []
        if cgtype is None:
            return out
        for body in _iter_scope(cgtype):           # CovergroupBody
            for cp in _iter_scope(body):
                if cp.kind != SymbolKind.Coverpoint:
                    continue
                if not is_real_location(sm, getattr(cp, "location", None)):
                    continue
                out.append(SvObject(
                    kind=KIND_COVERPOINT, name=cp.name,
                    qualified_name=_join(qname, cp.name),
                    signature="coverpoint " + cp.name,
                    location=resolve_location(sm, cp.location),
                    raw_doc=self._leading_doc(cp), doc_style=self.doc_style,
                ))
        return out

    def _build_generic_class(
        self, sym: Any, sm: Any, parent_qname: str | None
    ) -> SvObject:
        """Build a parameterized (generic) class from its CST.

        pyslang exposes uninstantiated generic classes as ``GenericClassDef``
        symbols without an iterable member scope, so members are recovered from
        the class-declaration syntax (best-effort: name + source signature).
        """
        qname = _join(parent_qname, sym.name)
        obj = SvObject(
            kind=KIND_CLASS,
            name=sym.name,
            qualified_name=qname,
            qualifiers=["parameterized"],
            location=resolve_location(sm, sym.location),
            raw_doc=self._leading_doc(sym, include_inline=True),
            doc_style=self.doc_style,
        )
        syntax = getattr(sym, "syntax", None)
        word = _cst_class_qualifier(syntax)
        if word:
            obj.qualifiers.append(word)
        obj.extends = _extends_from_clause(getattr(syntax, "extendsClause", None))
        self._apply_nd(obj, sym)
        if syntax is not None:
            plist = getattr(syntax, "parameters", None)
            if plist is not None:
                obj.signature = f"{sym.name} {_tokens_text(plist)}"
            params = self._parse_parameters(syntax, sm, qname)
            for p in params:
                if not p.signature.split(None, 1)[0] in ("parameter", "localparam"):
                    p.signature = "parameter " + p.signature
            obj.children = params + self._parse_cst_members(syntax, sm, qname)
        return obj

    def _parse_cst_members(self, syntax: Any, sm: Any, qname: str) -> list[SvObject]:
        members: list[SvObject] = []
        for item in getattr(syntax, "items", []) or []:
            tn = type(item).__name__
            first = len(members)
            try:
                decl_tn = type(getattr(item, "declaration", None)).__name__
                if "PropertyDeclaration" in tn and "Typedef" in decl_tn:
                    # A class-scope typedef is wrapped as a property declaration.
                    members.append(self._cst_typedef(item, item.declaration, sm, qname))
                elif "PropertyDeclaration" in tn:
                    members.extend(self._cst_property(item, sm, qname))
                elif "MethodPrototype" in tn:
                    members.append(self._cst_method(item, item.prototype, sm, qname))
                elif "MethodDeclaration" in tn:
                    members.append(
                        self._cst_method(item, item.declaration.prototype, sm, qname)
                    )
                elif "TypedefDeclaration" in tn:
                    members.append(self._cst_typedef(item, item, sm, qname))
            except Exception:
                continue
            # A parameterized class gets the same `uvm_*_utils treatment as any
            # other, so provenance has to be recorded on this path too.
            chain = _cst_macro_chain(item, sm)
            for member in members[first:]:
                if member is not None:
                    member.from_macros = chain
        return [m for m in members if m is not None]

    def _cst_property(self, item: Any, sm: Any, qname: str) -> list[SvObject]:
        out: list[SvObject] = []
        decl = getattr(item, "declaration", item)
        doc = _token_leading_doc(item.getFirstToken())
        words = {getattr(t, "valueText", "") or str(t).strip()
                 for node in (getattr(item, "qualifiers", None), getattr(decl, "modifiers", None))
                 for t in node or ()}
        quals = [q for q in ("rand", "randc", "static", "const", "var", "local", "protected") if q in words]
        for declarator in _syntax_elements(getattr(decl, "declarators", None)):
            name = declarator.name.valueText
            out.append(SvObject(
                kind=KIND_PROPERTY, name=name, qualified_name=_join(qname, name),
                qualifiers=list(quals),
                signature=_node_source(item, sm),
                location=resolve_location(sm, declarator.name.location),
                raw_doc=doc, doc_style=self.doc_style,
            ))
            doc = None  # only the first declarator gets the leading comment
        return out

    def _cst_typedef(self, item: Any, decl: Any, sm: Any, qname: str) -> SvObject | None:
        name = _name_text(getattr(decl, "name", None))
        if not name:
            return None
        return SvObject(
            kind=KIND_TYPEDEF, name=name, qualified_name=_join(qname, name),
            signature=_typedef_text(decl),
            location=resolve_location(sm, item.getFirstToken().location),
            raw_doc=_token_leading_doc(item.getFirstToken()),
            doc_style=self.doc_style,
        )

    def _cst_method(self, item: Any, proto: Any, sm: Any, qname: str) -> SvObject | None:
        name = _name_text(getattr(proto, "name", None))
        if not name:
            return None
        # Use only the prototype: everything up to the first ';' (drops any body).
        sig = _node_source(item, sm).split(";", 1)[0].strip()
        head = sig.split("(", 1)[0]
        kind = KIND_TASK if "task" in head.split() else KIND_FUNCTION
        return SvObject(
            kind=kind, name=name, qualified_name=_join(qname, name), signature=sig,
            qualifiers=_cst_qualifiers(item),
            location=resolve_location(sm, item.getFirstToken().location),
            raw_doc=_token_leading_doc(item.getFirstToken()),
            doc_style=self.doc_style,
        )

    def _build_module_header(
        self, defn: Any, parent: SvObject, sm: Any, qname: str
    ) -> None:
        """Extract parameters and ports from a module/interface header (CST)."""
        header = getattr(getattr(defn, "syntax", None), "header", None)
        if header is None:
            return
        children: list[SvObject] = []
        children.extend(self._parse_parameters(header, sm, qname))
        children.extend(self._parse_ports(header, sm, qname))
        parent.children = children

    def _parse_parameters(self, header: Any, sm: Any, qname: str) -> list[SvObject]:
        params: list[SvObject] = []
        trailing: list[list[str]] = []
        plist = getattr(header, "parameters", None)
        if plist is None:
            return params
        for decl in getattr(plist, "declarations", []) or []:
            if "Parameter" not in type(decl).__name__:
                continue
            sig = _node_source(decl, sm)
            trailing_prev, leading = split_leading_trivia(decl.getFirstToken())
            for declarator in _syntax_elements(getattr(decl, "declarators", None)):
                name = declarator.name.valueText
                params.append(
                    SvObject(
                        kind=KIND_PARAMETER,
                        name=name,
                        qualified_name=_join(qname, name),
                        signature=sig,
                        location=resolve_location(sm, declarator.name.location),
                        raw_doc=clean_comment_block(leading),
                        doc_style=self.doc_style,
                    )
                )
                trailing.append(trailing_prev)
        for i in range(1, len(params)):
            if trailing[i] and not params[i - 1].is_documented:
                params[i - 1].raw_doc = clean_comment_block(trailing[i])
        # The last parameter's trailing comment is trivia of the closing paren.
        close = getattr(plist, "closeParen", None)
        if params and close is not None and not params[-1].is_documented:
            trailing_last, _ = split_leading_trivia(close)
            if trailing_last:
                params[-1].raw_doc = clean_comment_block(trailing_last)
        return params

    def _parse_ports(self, header: Any, sm: Any, qname: str) -> list[SvObject]:
        ports: list[SvObject] = []
        trailing: list[list[str]] = []
        plist = getattr(header, "ports", None)
        if plist is None:
            return ports
        for port in getattr(plist, "ports", []) or []:
            declarator = getattr(port, "declarator", None)
            if declarator is None:
                continue  # skip comma tokens / non-declarator entries
            name = declarator.name.valueText
            direction = ""
            phdr = getattr(port, "header", None)
            if phdr is not None and getattr(phdr, "direction", None):
                direction = phdr.direction.valueText
            trailing_prev, leading = split_leading_trivia(port.getFirstToken())
            obj = SvObject(
                kind=KIND_PORT,
                name=name,
                qualified_name=_join(qname, name),
                qualifiers=[direction] if direction else [],
                signature=_node_source(port, sm),
                location=resolve_location(sm, declarator.name.location),
                raw_doc=clean_comment_block(leading),
                doc_style=self.doc_style,
            )
            ports.append(obj)
            trailing.append(trailing_prev)
        for i in range(1, len(ports)):
            if trailing[i] and not ports[i - 1].is_documented:
                ports[i - 1].raw_doc = clean_comment_block(trailing[i])
        return ports

    # -- leaf builders --------------------------------------------------------

    def _build_subroutine(self, sym: Any, sm: Any, qname: str | None) -> SvObject:
        is_task = str(getattr(sym, "subroutineKind", "")) == "SubroutineKind.Task"
        kind = KIND_TASK if is_task else KIND_FUNCTION
        obj = self._build_simple(
            sym, kind, sm, qname, signature=_subroutine_signature(sym, is_task)
        )
        if _method_flag(sym, "Pure"):
            obj.qualifiers.append("pure")
        if getattr(sym, "isVirtual", False):
            obj.qualifiers.append("virtual")
        if _method_flag(sym, "Static"):
            obj.qualifiers.append("static")
        vis = _visibility(sym)
        if vis:
            obj.qualifiers.append(vis)
        return obj

    def _build_property(self, sym: Any, sm: Any, qname: str | None) -> SvObject:
        type_str, dims = _written_type(sym) or _split_unpacked(str(getattr(sym, "type", "")) or "")
        sig = f"{type_str} {sym.name}{dims}".strip()
        obj = self._build_simple(sym, KIND_PROPERTY, sm, qname, signature=sig)
        obj.qualifiers.extend(_property_qualifiers(sym))
        vis = _visibility(sym)
        if vis:
            obj.qualifiers.append(vis)
        return obj

    def _build_simple(
        self, sym: Any, kind: str, sm: Any, qname: str | None, signature: str = ""
    ) -> SvObject:
        obj = SvObject(
            kind=kind,
            name=sym.name,
            qualified_name=_join(qname, sym.name),
            signature=signature,
            location=resolve_location(sm, sym.location),
            raw_doc=self._leading_doc(sym),
            doc_style=self.doc_style,
        )
        self._apply_nd(obj, sym)
        return obj

    # -- comment helpers ------------------------------------------------------

    def _leading_doc(
        self, sym: Any, include_inline: bool = False, sm: Any = None
    ) -> str | None:
        token = _decl_token(sym)
        if token is None:
            return None
        trailing_prev, leading = split_leading_trivia(token)
        # At a buffer/scope start there is no previous declaration to own an
        # inline comment, so a pre-newline comment is part of this symbol's own
        # doc block (it is the first line, ahead of any wrapped continuation).
        if include_inline and trailing_prev:
            leading = trailing_prev + leading
        doc = clean_comment_block(leading)
        if doc is None and sm is not None:
            doc = self._doc_from_text(sym, sm)
        return doc

    def _doc_from_text(self, sym: Any, sm: Any) -> str | None:
        """Read the doc comment out of the source, for a macro-led declaration.

        See :func:`~.comments.doc_above_line` for when the trivia route cannot
        see it and why this is a fallback rather than the normal path.
        """
        location = getattr(sym, "location", None)
        if location is None:
            return None
        try:
            line = sm.getLineNumber(location)
            text = sm.getSourceText(location.buffer)
        except Exception:
            return None
        if not text or not line:
            return None
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        return clean_comment_block(doc_above_line(text, int(line)))

    def _trailing_for(self, sym: Any) -> list[str]:
        token = _decl_token(sym)
        if token is None:
            return []
        trailing_prev, _ = split_leading_trivia(token)
        return trailing_prev


# -- module-level helpers -----------------------------------------------------

_DEFINITION_KINDS = {
    "DefinitionKind.Module": KIND_MODULE,
    "DefinitionKind.Interface": KIND_INTERFACE,
    "DefinitionKind.Program": KIND_PROGRAM,
}


def _iter_scope(scope: Any) -> Iterable[Any]:
    try:
        return list(scope)
    except TypeError:
        return []


def _cst_macro_chain(item: Any, sm: Any) -> tuple[str, ...]:
    """:func:`macro_chain` for a CST node, via its first token's location."""
    try:
        return macro_chain(sm, item.getFirstToken().location)
    except Exception:
        return ()


def _has_real_location(sym: Any, sm: Any) -> bool:
    if sym.kind == SymbolKind.TransparentMember:
        return False
    return is_real_location(sm, getattr(sym, "location", None))


#: Syntax nodes that introduce a new scope; the comment climb stops below these
#: so a member never inherits its container's doc comment.
_SCOPE_SYNTAX_NAMES = {
    "ClassDeclaration",
    "ModuleDeclaration",
    "PackageDeclaration",
    "InterfaceDeclaration",
    "ProgramDeclaration",
    "CovergroupDeclaration",
    "CheckerDeclaration",
    "CompilationUnit",
}


def _decl_token(sym: Any) -> Any | None:
    """Return the first token of *sym*'s full declaration statement.

    A pyslang symbol's ``.syntax`` is often the inner declarator (e.g. just the
    field name), while the doc comment sits on the enclosing declaration (which
    carries the type and qualifiers).  Climb to the outermost non-scope ancestor
    so leading/trailing comments are read from the declaration, not the bare name.
    """
    syntax = getattr(sym, "syntax", None)
    if syntax is None:
        return None
    cur = syntax
    while True:
        parent = getattr(cur, "parent", None)
        if parent is None:
            break
        if type(parent).__name__.replace("Syntax", "") in _SCOPE_SYNTAX_NAMES:
            break
        cur = parent
    getter = getattr(cur, "getFirstToken", None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:
        return None


def _trivia_syntax(trivia: Any) -> Any:
    """Return the syntax node behind a Directive trivia (method or attr form)."""
    s = getattr(trivia, "syntax", None)
    if callable(s):
        try:
            return s()
        except Exception:
            return None
    return s


def _macro_signature(syn: Any) -> str:
    name = syn.name.valueText
    args = ""
    formal = getattr(syn, "formalArguments", None)
    if formal is not None:
        args = _normalize_ws(str(formal))
    body = " ".join(t.valueText for t in getattr(syn, "body", []) or [])
    body = body.replace("\\", "").strip()
    sig = f"`define {name}{args}"
    if body and len(body) <= 48:
        sig += " " + body
    return sig


def _is_covergroup(sym: Any) -> bool:
    t = getattr(sym, "type", None)
    return t is not None and str(getattr(t, "kind", "")) == "SymbolKind.CovergroupType"


def _safe_flags(sym: Any) -> str:
    """Stringify a symbol's ``flags`` enum, tolerating unknown bits.

    Some pyslang flag enums (e.g. ``MethodFlags``) can carry bits the Python
    binding's enum does not know about, which makes ``str(sym.flags)`` raise.
    """
    try:
        return str(getattr(sym, "flags", ""))
    except Exception:
        return ""


def _method_flag(sym: Any, name: str) -> bool:
    """Whether a subroutine or prototype carries ``MethodFlags.<name>``.

    The flags are an integer-valued enum, and ``str()`` of a combination is
    often a bare number (``"4"``), so test the bit; fall back to the name for a
    binding that stringifies by name.  Python < 3.11 builds the enum strictly,
    so a bit the binding does not know makes reading ``sym.flags`` itself raise.
    """
    try:
        flags = getattr(sym, "flags", None)
    except ValueError:
        return False
    bit = getattr(pyslang.ast.MethodFlags, name, None)
    if flags is None or bit is None:
        return False
    try:
        return bool(int(flags) & int(bit))
    except Exception:
        return name in _safe_flags(sym)


#: Method qualifiers recovered from syntax.  ``extern`` is left out: it says
#: where the body is, which is no part of the method's interface.
_CST_METHOD_QUALIFIERS = ("local", "protected", "static", "pure", "virtual")


def _cst_qualifiers(item: Any) -> list[str]:
    # valueText, not str(): a token's str() carries its leading trivia, which
    # for the first qualifier is the doc comment.
    words = {getattr(q, "valueText", "") for q in (getattr(item, "qualifiers", None) or [])}
    return [q for q in _CST_METHOD_QUALIFIERS if q in words]


def _tokens_text(node: Any) -> str:
    """A syntax node's source on one line, without comments: its tokens joined
    with one space wherever the source had whitespace or a comment, except just
    inside brackets and before a comma."""
    tokens: list[Any] = []
    collect = lambda n: tokens.append(n) if type(n).__name__ == "Token" else None  # noqa: E731
    # Some syntax lists (a declarator's dimensions) come back as plain lists.
    for part in node if isinstance(node, list) else [node]:
        part.visit(collect)
    out = ""
    for tok in tokens:
        text = tok.rawText
        if out and tok.trivia and out[-1] not in "([{" and text not in (")", "]", "}", ","):
            out += " "
        out += text
    return out


def _cst_class_qualifier(syntax: Any) -> str | None:
    """``virtual`` or ``interface``, from a class declaration's syntax."""
    tok = getattr(syntax, "virtualOrInterface", None)
    word = getattr(tok, "valueText", "") if tok is not None else ""
    return word if word in ("virtual", "interface") else None


def _is_linked(sm: Any, loc: Any) -> bool:
    """Whether *loc* lies in text generated from a link database."""
    try:
        return sm is not None and sm.getFileName(loc).startswith("svdb-link:")
    except Exception:  # noqa: BLE001
        return False


def _stream_key(sm: Any, loc: Any) -> tuple:
    """Where *loc* falls in its compilation unit's preprocessed text: the root
    buffer, then the offset at each level of `` `include `` down to *loc*
    (after macro expansion).  No location sorts last."""
    try:
        loc = sm.getFullyExpandedLoc(loc)
        offsets = []
        while loc is not None and loc.buffer.id != 0:
            offsets.append(loc.offset)
            inc = sm.getIncludedFrom(loc.buffer)
            if inc.buffer.id == 0:
                return (0, loc.buffer.id, *reversed(offsets))
            loc = sm.getFullyExpandedLoc(inc)
    except Exception:  # noqa: BLE001 - a binding without these: no order
        pass
    return (1,)


def _property_qualifiers(sym: Any) -> list[str]:
    """``rand``/``randc``, ``static``, ``const`` and ``var`` of a class property,
    in that order (visibility is added by the caller)."""
    rand = str(getattr(sym, "randMode", ""))
    quals = ["randc"] if rand == "RandMode.RandC" else ["rand"] if rand == "RandMode.Rand" else []
    words: set[str] = set()
    decl = getattr(getattr(sym, "syntax", None), "parent", None)
    for node in (getattr(decl, "modifiers", None), getattr(getattr(decl, "parent", None), "qualifiers", None)):
        for tok in node or ():
            words.add(getattr(tok, "valueText", "") or str(tok).strip())
    if "static" in words:
        quals.append("static")
    if "const" in words:
        quals.append("const")
    if "var" in words:
        quals.append("var")
    return quals


def _visibility(sym: Any) -> str | None:
    vis = str(getattr(sym, "visibility", ""))
    if vis == "Visibility.Local":
        return "local"
    if vis == "Visibility.Protected":
        return "protected"
    return None


def _subroutine_signature(sym: Any, is_task: bool) -> str:
    args = []
    for arg in getattr(sym, "arguments", []) or []:
        direction = _ARG_DIR.get(str(getattr(arg, "direction", "")), "")
        atype, dims = _written_type(arg) or _split_unpacked(str(getattr(arg, "type", "")) or "")
        piece = " ".join(p for p in (direction, atype, arg.name + dims) if p)
        default = _argument_default(arg)
        if default:
            piece += f" = {default}"
        args.append(piece)
    arglist = ", ".join(args)
    if is_task:
        return f"task {sym.name}({arglist})"
    ret = _written_return_type(sym) or str(getattr(sym, "returnType", "")) or "void"
    return f"function {ret} {sym.name}({arglist})"


def _written_type(sym: Any) -> tuple[str, str] | None:
    """A variable's or argument's ``(type, unpacked dimensions)`` as written:
    ``pair_t`` and ``[]`` rather than slang's resolved ``int$[][0:1]``.

    ``None`` when there is no written type (an implicit one, or no syntax), so
    the caller falls back to the resolved type.
    """
    declared = getattr(sym, "declaredType", None)
    type_syntax = getattr(declared, "typeSyntax", None) if declared is not None else None
    if type_syntax is None:
        return None
    # Packed dimensions bind to the type, as slang prints them: ``bit[7:0]``.
    text = re.sub(r"\s+\[", "[", _tokens_text(type_syntax))
    if not text:
        return None
    declarator = getattr(sym, "syntax", None)
    dims = getattr(declarator, "dimensions", None) if declarator is not None else None
    return text, (_tokens_text(dims) if dims is not None else "")


def _written_return_type(sym: Any) -> str:
    """A function's return type as written (``params_t``), or "" if unknown."""
    syntax = getattr(sym, "syntax", None)
    proto = getattr(syntax, "prototype", None) if syntax is not None else None
    ret = getattr(proto, "returnType", None) if proto is not None else None
    return _tokens_text(ret) if ret is not None else ""


def _typedef_signature(sym: Any) -> str:
    """``typedef <type> <name><dims>`` as written.  A struct, union or enum body
    is abbreviated to ``{ ... }``: the members are not a one-line signature."""
    syntax = getattr(sym, "syntax", None)
    if syntax is None or "Typedef" not in type(syntax).__name__:
        return f"typedef {sym.name}"
    return _typedef_text(syntax)


def _typedef_text(syntax: Any) -> str:
    text = _tokens_text(syntax).rstrip(";").rstrip()
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                text = text[:start] + "{ ... }" + text[i + 1:]
                break
    return text


def _split_unpacked(type_str: str) -> tuple[str, str]:
    """Split slang's ``elem$[dim]`` notation into SV declaration order.

    Slang renders unpacked dimensions inline and separated by ``$``
    (``int$[$]``, ``byte$[]``, ``int$[string]``), which is not valid SV.  In
    SystemVerilog the dimensions follow the *declarator*: ``int q[$]``.  Packed
    dimensions carry no ``$`` and are already in the right place, so they are
    left alone.

    Returns ``(base_type, dimensions)``; ``dimensions`` is "" when there are no
    unpacked dimensions.
    """
    if "$[" not in type_str:
        return type_str, ""
    base = type_str.split("$[", 1)[0]
    dims = "".join(re.findall(r"\$(\[[^\]]*\])", type_str))
    return base, dims


def _argument_default(arg: Any) -> str:
    """Source text of an argument's default value, or "" when it has none.

    Slang wraps a default in an implicit conversion to the argument type, and
    only the innermost expression carries syntax, so unwrap until something
    with a syntax node appears.
    """
    expr = getattr(arg, "defaultValue", None)
    for _ in range(8):  # bounded: guards against a cyclic/deep operand chain
        if expr is None:
            return ""
        syntax = getattr(expr, "syntax", None)
        if syntax is not None:
            return " ".join(str(syntax).split())
        expr = getattr(expr, "operand", None)
    return ""


_ARG_DIR = {
    # 'input' is the default direction for subroutine args; omit it for brevity.
    "ArgumentDirection.In": "",
    "ArgumentDirection.Out": "output",
    "ArgumentDirection.InOut": "inout",
    "ArgumentDirection.Ref": "ref",
}


def _join(parent: str | None, name: str) -> str:
    return f"{parent}::{name}" if parent else name


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace (incl. newlines) to single spaces."""
    return " ".join(text.split())


def _node_source(node: Any, sm: Any) -> str:
    """Exact source text of *node*, from its first token to its last.

    Uses token offsets so leading comment/whitespace trivia is excluded (unlike
    ``str(node)``, which includes leading trivia).
    """
    try:
        start = node.getFirstToken().range.start
        end = node.getLastToken().range.end
        if sm.isMacroLoc(start) or sm.isMacroLoc(end):
            # Expanded from a macro: there is no source text to slice.
            return _tokens_text(node)
        text = sm.getSourceText(start.buffer)
        if not text.isascii():
            # Offsets count bytes: a multi-byte character before *node* (a
            # typographic apostrophe in a comment) would shift a str slice.
            return _normalize_ws(text.encode("utf-8")[start.offset:end.offset].decode("utf-8", "replace"))
        return _normalize_ws(text[start.offset:end.offset])
    except Exception:
        return _normalize_ws(str(node))


def _token_leading_doc(token: Any, include_inline: bool = False) -> str | None:
    if token is None:
        return None
    trailing_prev, leading = split_leading_trivia(token)
    if include_inline and not leading and trailing_prev:
        leading = trailing_prev
    return clean_comment_block(leading)


def _syntax_elements(seplist: Any) -> list[Any]:
    """The elements of a CST separated list, without its separator tokens.

    Iterating a pyslang ``SeparatedSyntaxList`` yields the comma tokens between
    elements as well as the elements themselves.
    """
    return [e for e in seplist or [] if not isinstance(e, Token)]


def _name_text(name_node: Any) -> str | None:
    """Best-effort identifier text from a CST name token or name-syntax node."""
    if name_node is None:
        return None
    val = getattr(name_node, "valueText", None)
    if val:
        return val
    text = _normalize_ws(str(name_node))
    # Strip any parameter specialization, e.g. "base #(T)" -> "base".
    return text.split("#")[0].split()[0] if text else None


def _extends_from_clause(clause: Any) -> str | None:
    """Extract the base class name from an ``extends`` clause CST node."""
    if clause is None:
        return None
    text = _normalize_ws(str(clause))
    text = text.replace("extends", "", 1).strip()
    if not text:
        return None
    return text.split("#")[0].split("(")[0].split()[0] or None
