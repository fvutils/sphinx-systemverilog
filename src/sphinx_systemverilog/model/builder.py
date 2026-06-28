"""Build the normalized :class:`SvObject` model from SystemVerilog source.

The builder uses pyslang's elaborated AST for clean scope iteration, but is
deliberately tolerant of unresolved references (e.g. a base class defined in
another, unparsed file): parse diagnostics are collected, never fatal.  Phase 1
targets self-contained packages; Phase 2 adds include/define-driven elaboration.
"""

from __future__ import annotations

from typing import Any, Iterable

from .comments import clean_comment_block, split_leading_trivia
from .locations import is_real_location, resolve_location
from .objects import (
    KIND_CLASS,
    KIND_FUNCTION,
    KIND_INTERFACE,
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
from pyslang.syntax import SyntaxTree


class ModelBuilder:
    """Parse SystemVerilog and emit a list of top-level :class:`SvObject`."""

    def __init__(
        self,
        doc_style: str = "native",
        include_dirs: Iterable[str] | None = None,
        defines: dict[str, str] | None = None,
        nodocs_policy: str = "include",
    ) -> None:
        self.doc_style = doc_style
        self.include_dirs = list(include_dirs or [])
        self.defines = dict(defines or {})
        #: How to treat UVM ``-- NODOCS --`` blocks: "include" the prose or "skip".
        self.nodocs_policy = nodocs_policy
        #: Error/fatal diagnostics rendered as strings; surfaced as warnings.
        self.diagnostics: list[str] = []
        #: Count of suppressed non-error (lint) diagnostics; surfaced as info.
        self.suppressed_count: int = 0
        self._nd_index = None

    # -- entry points ---------------------------------------------------------

    def build_from_text(self, text: str, name: str = "source") -> list[SvObject]:
        tree = SyntaxTree.fromText(text, name)
        return self._build([tree])

    def build_from_files(self, paths: Iterable[str]) -> list[SvObject]:
        sm, options = self._parse_options()
        trees = []
        for p in paths:
            if sm is not None:
                trees.append(SyntaxTree.fromFile(str(p), sm, options))
            else:
                trees.append(SyntaxTree.fromFile(str(p)))
        return self._build(trees)

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

    def _build(self, trees: list[Any]) -> list[SvObject]:
        comp = Compilation()
        source_manager = None
        for tree in trees:
            comp.addSyntaxTree(tree)
            if source_manager is None:
                source_manager = tree.sourceManager
        self._collect_diagnostics(comp)
        self._build_nd_index(trees, source_manager)

        roots: list[SvObject] = []
        for pkg in comp.getPackages():
            if pkg.name in ("std", "$unit"):
                continue
            obj = self._build_scope(
                pkg, KIND_PACKAGE, source_manager, pkg.name, include_inline=True
            )
            if obj is not None:
                roots.append(obj)
        # Modules/interfaces/programs (Phase 2 fleshes out ports/params).
        for defn in comp.getDefinitions():
            kind = _DEFINITION_KINDS.get(str(getattr(defn, "definitionKind", "")))
            if kind is None:
                continue
            obj = self._build_scope(
                defn, kind, source_manager, defn.name, include_inline=True
            )
            if obj is not None:
                roots.append(obj)
        return roots

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
        if kind in (SymbolKind.ClassProperty, SymbolKind.Variable):
            return self._build_property(sym, sm, parent_qname)
        if kind == SymbolKind.TypeAlias:
            return self._build_simple(sym, KIND_TYPEDEF, sm, parent_qname,
                                      signature=f"typedef {sym.name}")
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
            raw_doc=self._leading_doc(sym, include_inline=include_inline),
            doc_style=self.doc_style,
        )
        if class_sym is not None:
            if getattr(class_sym, "isAbstract", False):
                obj.qualifiers.append("virtual")
            base = getattr(class_sym, "baseClass", None)
            if base is not None and getattr(base, "name", ""):
                obj.extends = base.name
        self._apply_nd(obj, sym)
        if sym.kind == SymbolKind.Definition:
            self._build_module_header(sym, obj, sm, qname)
        else:
            self._build_members(sym, obj, sm, qname)
        return obj

    def _build_members(self, scope: Any, parent: SvObject, sm: Any, qname: str) -> None:
        members: list[SvObject] = []
        trailing: list[list[str]] = []
        for sym in _iter_scope(scope):
            if not _has_real_location(sym, sm):
                continue
            child = self._build_symbol(sym, sm, qname)
            if child is None:
                continue
            members.append(child)
            trailing.append(self._trailing_for(sym))

        # Re-assign each member's leading trailing-comment to the *previous*
        # sibling that has no doc of its own (the inline `; // ...` case).
        for i in range(1, len(members)):
            prev = members[i - 1]
            inline = trailing[i]
            if inline and not prev.is_documented:
                prev.raw_doc = clean_comment_block(inline)

        members.sort(key=lambda m: (m.location.line if m.location else 1 << 30))
        parent.children = members

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
        obj.extends = _extends_from_clause(getattr(syntax, "extendsClause", None))
        self._apply_nd(obj, sym)
        if syntax is not None:
            obj.children = self._parse_cst_members(syntax, sm, qname)
        return obj

    def _parse_cst_members(self, syntax: Any, sm: Any, qname: str) -> list[SvObject]:
        members: list[SvObject] = []
        for item in getattr(syntax, "items", []) or []:
            tn = type(item).__name__
            try:
                if "PropertyDeclaration" in tn:
                    members.extend(self._cst_property(item, sm, qname))
                elif "MethodPrototype" in tn:
                    members.append(self._cst_method(item, item.prototype, sm, qname))
                elif "MethodDeclaration" in tn:
                    members.append(
                        self._cst_method(item, item.declaration.prototype, sm, qname)
                    )
            except Exception:
                continue
        return [m for m in members if m is not None]

    def _cst_property(self, item: Any, sm: Any, qname: str) -> list[SvObject]:
        out: list[SvObject] = []
        decl = getattr(item, "declaration", item)
        doc = _token_leading_doc(item.getFirstToken())
        for declarator in getattr(decl, "declarators", []) or []:
            name = declarator.name.valueText
            out.append(SvObject(
                kind=KIND_PROPERTY, name=name, qualified_name=_join(qname, name),
                signature=_node_source(item, sm),
                location=resolve_location(sm, declarator.name.location),
                raw_doc=doc, doc_style=self.doc_style,
            ))
            doc = None  # only the first declarator gets the leading comment
        return out

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
            for declarator in getattr(decl, "declarators", []) or []:
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
        flags = _safe_flags(sym)
        if "Pure" in flags:
            obj.qualifiers.append("pure")
        if getattr(sym, "isVirtual", False):
            obj.qualifiers.append("virtual")
        if "Static" in flags:
            obj.qualifiers.append("static")
        vis = _visibility(sym)
        if vis:
            obj.qualifiers.append(vis)
        return obj

    def _build_property(self, sym: Any, sm: Any, qname: str | None) -> SvObject:
        type_str = str(getattr(sym, "type", "")) or ""
        sig = f"{type_str} {sym.name}".strip()
        obj = self._build_simple(sym, KIND_PROPERTY, sm, qname, signature=sig)
        if str(getattr(sym, "randMode", "")) in ("RandMode.Rand", "RandMode.RandC"):
            obj.qualifiers.append("rand")
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

    def _leading_doc(self, sym: Any, include_inline: bool = False) -> str | None:
        token = _decl_token(sym)
        if token is None:
            return None
        trailing_prev, leading = split_leading_trivia(token)
        # At a buffer/scope start there is no previous declaration to own an
        # inline comment, so a pre-newline comment is part of this symbol's own
        # doc block (it is the first line, ahead of any wrapped continuation).
        if include_inline and trailing_prev:
            leading = trailing_prev + leading
        return clean_comment_block(leading)

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


def _safe_flags(sym: Any) -> str:
    """Stringify a symbol's ``flags`` enum, tolerating unknown bits.

    Some pyslang flag enums (e.g. ``MethodFlags``) can carry bits the Python
    binding's enum does not know about, which makes ``str(sym.flags)`` raise.
    """
    try:
        return str(getattr(sym, "flags", ""))
    except Exception:
        return ""


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
        atype = str(getattr(arg, "type", "")) or ""
        piece = " ".join(p for p in (direction, atype, arg.name) if p)
        args.append(piece)
    arglist = ", ".join(args)
    if is_task:
        return f"task {sym.name}({arglist})"
    ret = str(getattr(sym, "returnType", "")) or "void"
    return f"function {ret} {sym.name}({arglist})"


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
        text = sm.getSourceText(start.buffer)
        return _normalize_ws(text[start.offset:end.offset])
    except Exception:
        return _normalize_ws(str(node))


def _token_leading_doc(token: Any) -> str | None:
    if token is None:
        return None
    _, leading = split_leading_trivia(token)
    return clean_comment_block(leading)


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
