"""Declarations the object model does not carry, for the database (plan D3a, D3b).

:class:`~.builder.ModelBuilder` makes what the Sphinx renderer documents
today.  :func:`extract` reads the same compilation again and returns what the
database needs beyond that:

* **new objects**, by parent qname: nets, variables, parameters, typedefs,
  nettypes, tasks, functions, modports and clocking blocks (with their
  clockvars) declared in a module, interface or program body; parameters and
  nettypes declared in a package; the enum literals and struct or union
  fields of every typedef and every variable whose type is declared inline;
* **detail**, by qname, for objects the builder already made: the declared
  type of every variable, parameter, port and typedef as a ``TypeRef`` with
  its ``form``, subroutine return types and arguments, typedef shape, the
  interface and modport of an interface port, a definition's default
  clocking.

It walks the same scopes as the builder (packages, classes, the default
specialization of a parameterized class) and, for a definition, the first
elaborated body of it that a breadth-first walk from the tops reaches --- a
top's body when there is one, so parameter values are the defaults.  A
definition no walk reaches contributes no body declarations.

Text is as written (from syntax); semantics supply what text cannot: the
evaluated value of an enum literal, which nets are implicit, a nettype's
resolution function.  pyslang stays inside :mod:`~sphinx_systemverilog.model`.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator

from pyslang.ast import SymbolKind

from .builder import (
    _DEFINITION_KINDS,
    _decl_token,
    _has_real_location,
    _iter_scope,
    _join,
    _method_flag,
    _split_unpacked,
    _subroutine_signature,
    _tokens_text,
    _written_return_type,
)
from .comments import clean_comment_block, split_leading_trivia
from .locations import is_real_location, macro_chain, resolve_location
from .objects import SourceRef
from .structure import _element_count, _first_element, _range_text


def _is_concurrent_assertion(sym: Any) -> bool:
    """A ``ProceduralBlock`` that is a concurrent assertion written directly
    as a module item (``assert property (...);``), not an ``initial``/
    ``always`` block."""
    return type(getattr(sym, "syntax", None)).__name__ == "ConcurrentAssertionMemberSyntax"


def _is_gate_array(array: Any) -> bool:
    """A gate array (``and g[3:0] (...)``) shares ``SymbolKind.InstanceArray``
    with a module-instance array, but its elements are ``PrimitiveInstance``
    symbols with no ``.body`` -- checked on the first element, which always
    exists (a gate array is never conditionally elaborated)."""
    for m in array:
        return m.kind == SymbolKind.PrimitiveInstance
    return False


def _is_udp_instance(sym: Any) -> bool:
    """An instance (or array) of a user-defined primitive (LRM 29), not of a
    built-in gate: recorded always, with ``of_kind: primitive``, since it
    names a design object rather than a netlist cell."""
    if sym.kind == SymbolKind.InstanceArray:
        sym = next(iter(sym), None)
    prim = getattr(sym, "primitiveType", None)
    return prim is not None and prim.primitiveKind == prim.PrimitiveKind.UserDefined


def _first_generate_element(array: Any) -> Any | None:
    """The first instantiated iteration of a for-generate array (which, with
    an inline-declared genvar, also holds the genvar itself as a member);
    its body is representative of every iteration's declarations."""
    for m in _iter_scope(array):
        if m.kind == SymbolKind.GenerateBlock and not getattr(m, "isUninstantiated", False):
            return m
    return None
from ..svdb import canon

log = logging.getLogger("sphinx_systemverilog.model")

#: Upper bound on instances visited looking for one body per definition.
MAX_BODY_SEARCH = 100_000

_BUILTIN_TYPES = {
    "bit", "logic", "reg", "byte", "shortint", "int", "longint", "integer", "time", "shortreal", "real",
    "realtime", "string", "chandle", "event", "void", "signed", "unsigned", "struct", "union", "enum",
    "packed", "tagged", "soft", "virtual", "interface", "type", "var", "wire", "tri", "untyped",
    "sequence", "property",
}
_NAME = re.compile(r"[A-Za-z_][\w$]*(?:\s*::\s*[A-Za-z_][\w$]*)*")

_FORMS = {
    SymbolKind.ScalarType: "builtin", SymbolKind.PredefinedIntegerType: "builtin",
    SymbolKind.PackedArrayType: "builtin", SymbolKind.FloatingType: "builtin",
    SymbolKind.EnumType: "enum", SymbolKind.PackedStructType: "struct",
    SymbolKind.UnpackedStructType: "struct", SymbolKind.PackedUnionType: "union",
    SymbolKind.UnpackedUnionType: "union", SymbolKind.ClassType: "class",
    SymbolKind.VirtualInterfaceType: "virtual_interface", SymbolKind.StringType: "string",
    SymbolKind.CHandleType: "chandle", SymbolKind.VoidType: "void", SymbolKind.EventType: "event",
    SymbolKind.UntypedType: "untyped", SymbolKind.SequenceType: "sequence",
    SymbolKind.PropertyType: "property",
}
_UNPACKED = {
    SymbolKind.FixedSizeUnpackedArrayType, SymbolKind.DynamicArrayType, SymbolKind.QueueType,
    SymbolKind.AssociativeArrayType,
}
_ARG_DIRS = {"ArgumentDirection.In": "input", "ArgumentDirection.Out": "output",
             "ArgumentDirection.InOut": "inout", "ArgumentDirection.Ref": "ref"}
#: A concurrent assertion's keyword token text -> schema ``verb`` (LRM 16);
#: ``expect`` is procedural-only and never reaches this module-item path.
_ASSERTION_VERBS = {"assert": "assert", "assume": "assume", "cover": "cover", "restrict": "restrict"}
_BIN_KINDS = {"BinKind.Bins": "bins", "BinKind.IllegalBins": "illegal_bins", "BinKind.IgnoreBins": "ignore_bins"}
_PROC_KINDS = {"Initial": "initial", "Final": "final", "Always": "always", "AlwaysFF": "always_ff",
               "AlwaysComb": "always_comb", "AlwaysLatch": "always_latch"}
_FORK_KINDS = {"JoinAll": "join", "JoinAny": "join_any", "JoinNone": "join_none"}


@dataclass
class Decl:
    """One declaration the builder does not make, shaped like an ``SvObject``
    where the emitter and the doc helpers look."""

    kind: str
    name: str
    qualified_name: str
    location: SourceRef | None = None
    signature: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    #: Lookup scope, when it is not the parent (an enum literal's).
    scope: str | None = None
    flags: list[str] = field(default_factory=list)
    qualifiers: list[str] = field(default_factory=list)
    raw_doc: str | None = None
    group: str | None = None
    children: list["Decl"] = field(default_factory=list)
    from_macros: tuple[str, ...] = ()

    @property
    def is_scope(self) -> bool:
        return False

    @property
    def is_documented(self) -> bool:
        return bool(self.raw_doc and self.raw_doc.strip())


@dataclass
class Extras:
    """What :func:`extract` found."""

    #: New objects, by the qname of their parent.
    children: dict[str, list[Decl]] = field(default_factory=dict)
    #: ``detail`` fields for objects the builder made, by qname.
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: ``import`` records (package imports and exports), ``loc`` a ``SourceRef``.
    imports: list[dict[str, Any]] = field(default_factory=list)
    #: ``include`` edges, ``(from path, to path, line)``, in parse order.
    includes: list[tuple[str, str, int]] = field(default_factory=list)
    #: ``unit`` records, one per syntax tree, with file paths in ``files``.
    units: list[dict[str, Any]] = field(default_factory=list)
    #: Each `` `define ``'s ``params`` (function-like only) and ``body`` text,
    #: by the ``(file, line, column)`` of its name.
    macros: dict[tuple[str, int, int], dict[str, Any]] = field(default_factory=dict)
    #: ``(* name = value *)`` attributes (``Attr`` list), by the
    #: ``(file, line, column)`` of the attributed declaration's name.
    attrs: dict[tuple[str, int, int], list[dict[str, Any]]] = field(default_factory=dict)
    #: Encrypted envelopes (`` `pragma protect begin_protected `` ...
    #: ``end_protected``, LRM 34) as ``[start, end]`` lines, by file path.
    protected: dict[str, list[list[int]]] = field(default_factory=dict)
    #: The ``(file, line, column)`` of the name of each declaration whose
    #: body holds an envelope (the innermost one; ``flags.protected``).
    protected_decls: set[tuple[str, int, int]] = field(default_factory=set)

    def add(self, parent: str, decl: Decl) -> None:
        self.children.setdefault(parent, []).append(decl)

    def patch(self, qname: str, detail: dict[str, Any]) -> None:
        if detail:
            self.details.setdefault(qname, {}).update(detail)


def extract(builder: Any, gates: bool = False) -> Extras:
    """The declarations of *builder*'s retained compilation (after
    :meth:`~.builder.ModelBuilder.build_from_files`).

    *gates* opts into gate instances (``and g1(...)``, ``of_kind: gate``):
    they are skipped by default because a gate-level netlist can be huge
    (plan §5.2.1, ``structure.gates``)."""
    comp = getattr(builder, "compilation", None)
    out = Extras()
    if comp is None:
        return out
    x = _Extractor(builder, builder.source_manager, out, gates=gates)
    for pkg in comp.getPackages():
        if pkg.name in ("std", "$unit"):
            continue
        _guard(x.scope, pkg, pkg.name)
        _guard(x.package_imports, pkg.syntax, pkg.name)
    names = [d.name for d in comp.getDefinitions()
             if _DEFINITION_KINDS.get(str(getattr(d, "definitionKind", ""))) is not None]
    bodies = _guard(canonical_bodies, comp) or {}
    missing = [n for n in names if n not in bodies]
    # Keeps the second compilation alive while its symbols are read.
    keep = _guard(_elaborate_alone, comp, builder.source_manager, missing) if missing else None
    if keep is not None:
        bodies.update(keep[1])
    for name in names:
        body = bodies.get(name)
        if body is not None:
            _guard(x.definition, body, name)
    # Checkers last: their contents come from an instance's body (above).
    for unit in comp.getRoot().compilationUnits:
        for sym in unit:
            if sym.kind == SymbolKind.Checker and _has_real_location(sym, builder.source_manager):
                x.checkers.append((sym, ""))
    for sym, parent in x.checkers:
        d = _guard(x.checker, sym, parent, x._checker_bodies.get(sym.name))
        if d is not None:
            out.add(parent, d)
    # UDPs and configs: only ever at the root (LRM 29, 33).
    for unit in comp.getRoot().compilationUnits:
        for sym in unit:
            if sym.kind not in (SymbolKind.Primitive, SymbolKind.ConfigBlock) \
                    or not _has_real_location(sym, builder.source_manager):
                continue
            d = _guard(x.primitive if sym.kind == SymbolKind.Primitive else x.config, sym, "")
            if d is not None:
                out.add("", d)
    _guard(_includes, comp, builder.source_manager, out.includes)
    _guard(_units, comp, builder.source_manager, dict(getattr(builder, "defines", None) or {}), out.units)
    _guard(_macros, comp, builder.source_manager, out.macros)
    _guard(_attributes, comp, builder.source_manager, out.attrs)
    _guard(_protected, comp, builder.source_manager, out)
    return out


def _attr_list(specs: Any) -> list[dict[str, Any]]:
    out = []
    for spec in specs:
        if type(spec).__name__ != "AttributeSpecSyntax":  # skip `,` separators
            continue
        attr: dict[str, Any] = {"name": spec.name.valueText}
        if spec.value is not None:
            attr["value"] = {"text": str(spec.value.expr).strip()}
        out.append(attr)
    return out


def _attributes(comp: Any, sm: Any, out: dict[tuple[str, int, int], list[dict[str, Any]]]) -> None:
    """The ``(* ... *)`` attributes (LRM 5.12) of every declaration in *comp*.

    slang binds most of them to symbols (``Compilation.getAttributes``);
    those it drops (class declarations, ANSI ports, parameter ports) are
    taken from the syntax: any node with ``attributes`` and a name token."""
    def add(token_loc: Any, attrs: list[dict[str, Any]]) -> None:
        ref = resolve_location(sm, token_loc)
        if attrs and ref is not None and ref.is_valid:
            out.setdefault((ref.file, ref.line, ref.column), attrs)

    def symbol(sym: Any) -> None:
        specs = [a.syntax for a in comp.getAttributes(sym) if a.syntax is not None]
        if specs:
            add(sym.location, _attr_list(specs))

    comp.getRoot().visit(symbol)
    for d in comp.getDefinitions():
        symbol(d)

    def names(node: Any) -> list[Any]:
        for owner in (node, getattr(node, "header", None), getattr(node, "declarator", None)):
            token = getattr(owner, "name", None)
            if token is not None and hasattr(token, "valueText") and token.valueText:
                return [token]
        return [d.name for d in getattr(node, "declarators", None) or ()
                if hasattr(d, "name") and getattr(d.name, "valueText", "")]

    def syntax(node: Any) -> None:
        specs = [s for inst in getattr(node, "attributes", None) or () for s in inst.specs]
        if specs:
            attrs = _attr_list(specs)
            for token in names(node):
                add(token.location, attrs)

    for tree in comp.getSyntaxTrees():
        tree.root.visit(syntax)


def _macros(comp: Any, sm: Any, out: dict[tuple[str, int, int], dict[str, Any]]) -> None:
    """The formal arguments and body text of every `` `define `` in *comp*'s
    syntax trees (included files' directives are in the including tree)."""
    def visit(node: Any) -> None:
        for trivia in getattr(node, "trivia", None) or ():
            syntax = trivia.syntax()
            if str(getattr(syntax, "kind", "")) != "SyntaxKind.DefineDirective":
                continue
            ref = resolve_location(sm, syntax.name.location)
            if ref is None or not ref.is_valid:
                continue
            rec: dict[str, Any] = {}
            formal = syntax.formalArguments
            if formal is not None:
                params = []
                for arg in formal.args:
                    if type(arg).__name__ != "MacroFormalArgumentSyntax" or not arg.name.valueText:
                        continue
                    param = {"name": arg.name.valueText}
                    if arg.defaultValue is not None:
                        param["default"] = "".join(str(t) for t in arg.defaultValue.tokens).strip()
                    params.append(param)
                rec["params"] = params
            tokens = list(syntax.body or ())
            # A body that starts on the next line starts with its `\` continuation.
            while tokens and str(tokens[0].kind) == "TokenKind.LineContinuation":
                tokens.pop(0)
            body = "".join(str(t) for t in tokens).strip()
            if body:
                rec["body"] = body
            out.setdefault((ref.file, ref.line, ref.column), rec)

    for tree in comp.getSyntaxTrees():
        last = getattr(tree.root, "endOfFile", None) or tree.root.getLastToken()
        tree.root.visit(visit)
        visit(last)


_ENVELOPE_SCOPES = {
    "SyntaxKind.ModuleDeclaration", "SyntaxKind.InterfaceDeclaration",
    "SyntaxKind.ProgramDeclaration", "SyntaxKind.PackageDeclaration",
    "SyntaxKind.ClassDeclaration", "SyntaxKind.FunctionDeclaration",
    "SyntaxKind.TaskDeclaration",
}


def _envelope_scope_name(node: Any) -> Any:
    """The name token of a declaration in :data:`_ENVELOPE_SCOPES`."""
    header = getattr(node, "header", None) or getattr(node, "prototype", None)
    name = getattr(header, "name", None) if header is not None else getattr(node, "name", None)
    if name is not None and not hasattr(name, "valueText"):
        name = name.getLastToken()  # `C::f`: the object's name is the last part
    return name


def _protected(comp: Any, sm: Any, out: Extras) -> None:
    """Encrypted envelopes in *comp*'s syntax trees: their line ranges (per
    file) and the innermost declaration around each. Markers only: the
    data block is never read (slang skips it, warning ``ProtectedEnvelope``)."""
    open_at: dict[str, int] = {}

    def trivia_of(token: Any, scope: Any) -> None:
        for trivia in getattr(token, "trivia", None) or ():
            syntax = trivia.syntax()
            if str(getattr(syntax, "kind", "")) != "SyntaxKind.PragmaDirective" \
                    or syntax.name.valueText != "protect":
                continue
            words = {str(a).strip().split("=")[0].strip() for a in syntax.args}
            if not words & {"begin_protected", "end_protected"}:
                continue
            ref = resolve_location(sm, syntax.directive.location)
            if ref is None or not ref.is_valid:
                continue
            if "begin_protected" in words:
                open_at.setdefault(ref.file, ref.line)
                continue
            start = open_at.pop(ref.file, None)
            if start is None:
                continue
            out.protected.setdefault(ref.file, []).append([start, ref.line])
            if scope is not None:
                at = resolve_location(sm, scope.location)
                if at is not None and at.is_valid:
                    out.protected_decls.add((at.file, at.line, at.column))

    def walk(node: Any, scope: Any) -> None:
        if str(getattr(node, "kind", "")) in _ENVELOPE_SCOPES:
            scope = _envelope_scope_name(node) or scope
        for child in node:
            if child is None:
                continue
            if hasattr(child, "valueText"):
                trivia_of(child, scope)
            else:
                walk(child, scope)

    for tree in comp.getSyntaxTrees():
        walk(tree.root, None)


def _units(comp: Any, sm: Any, defines: dict[str, str], out: list[dict[str, Any]]) -> None:
    """One ``unit`` record per syntax tree (each is its own compilation unit):
    its file and the files it includes, the build's predefines, and the first
    `` `default_nettype `` / `` `timescale `` it sets (``wire`` and nothing
    when it sets none)."""
    from pyslang import SourceLocation

    for n, tree in enumerate(comp.getSyntaxTrees()):
        # A one-declaration text tree has that declaration as its root.
        last = getattr(tree.root, "endOfFile", None) or tree.root.getLastToken()
        main = str(sm.getFileName(last.location))
        files = [main]
        for d in tree.getIncludeDirectives():
            if d.buffer is not None:
                path = str(sm.getFileName(SourceLocation(d.buffer.id, 0)))
                if path not in files:
                    files.append(path)
        directives: dict[str, str] = {}

        def visit(node: Any) -> None:
            for trivia in getattr(node, "trivia", None) or ():
                syntax = trivia.syntax()
                kind = str(getattr(syntax, "kind", ""))
                key = {"SyntaxKind.DefaultNetTypeDirective": "default_nettype",
                       "SyntaxKind.TimeScaleDirective": "timescale"}.get(kind)
                if key and key not in directives:
                    directives[key] = syntax.netType.valueText if key == "default_nettype" else \
                        f"{syntax.timeUnit.valueText}/{syntax.timePrecision.valueText}"

        tree.root.visit(visit)
        visit(last)
        rec: dict[str, Any] = {"r": "unit", "id": f"cu{n}", "files": files}
        if defines:
            rec["defines"] = {k: str(v) for k, v in defines.items()}
        rec["default_nettype"] = directives.get("default_nettype", "wire")
        if "timescale" in directives:
            rec["timescale"] = directives["timescale"]
        out.append(rec)


def _includes(comp: Any, sm: Any, out: list[tuple[str, str, int]]) -> None:
    """The `` `include `` edges of *comp*'s syntax trees (nested ones too: an
    included file's directives belong to the tree that includes it)."""
    from pyslang import SourceLocation

    seen: set[tuple[str, str, int]] = set()
    for tree in comp.getSyntaxTrees():
        for d in tree.getIncludeDirectives():
            start = getattr(getattr(d.syntax, "sourceRange", None), "start", None)
            if d.buffer is None or not is_real_location(sm, start):
                continue
            edge = (str(sm.getFileName(start)), str(sm.getFileName(SourceLocation(d.buffer.id, 0))),
                    int(sm.getLineNumber(start)))
            if edge not in seen:
                seen.add(edge)
                out.append(edge)


def _port_declarator(body: Any, name: str) -> Any | None:
    """The declarator of *name* in a non-ANSI ``input``/``output`` declaration."""
    syntax = getattr(getattr(body, "definition", None), "syntax", None)
    for member in getattr(syntax, "members", None) or ():
        if type(member).__name__ != "PortDeclarationSyntax":
            continue
        for declarator in _syntax_list(member.declarators):
            if declarator.name.valueText == name:
                return declarator
    return None


class _Syntax:
    """Enough of a symbol for the builder's comment helpers: its syntax."""

    def __init__(self, syntax: Any):
        self.syntax = syntax
        self.location = syntax.getFirstToken().location


def _specialization(generic: Any, scope: Any) -> Any | None:
    """A specialization of a parameterized class to read its members from:
    the default one, or, when a parameter has no default, the one slang makes
    with error values (types written as text are all this pass needs)."""
    for get in (lambda: type(generic).defaultSpecialization.fget(generic, scope),
                lambda: generic.invalidSpecialization):
        try:
            spec = get()
        except Exception:
            spec = None
        if spec is not None and spec.kind == SymbolKind.ClassType:
            return spec
    return None


def _guard(fn, *args):
    """A construct this pass cannot read costs its own declarations, never the build."""
    try:
        return fn(*args)
    except Exception as e:
        log.debug("sphinx-systemverilog: reading the declarations of %s failed: %s", args[-1], e, exc_info=True)
        return None


def canonical_bodies(comp: Any, limit: int = MAX_BODY_SEARCH) -> dict[str, Any]:
    """The first elaborated body of each definition, breadth first from the tops."""
    found: dict[str, Any] = {}
    queue: deque = deque(comp.getRoot().topInstances)
    visited = 0
    while queue and visited < limit:
        sym = queue.popleft()
        visited += 1
        if sym.kind == SymbolKind.Instance:
            body = sym.body
            name = sym.definition.name
            if name not in found:
                found[name] = body
            queue.extend(m for m in _iter_scope(body) if m.kind in _HIER)
        elif sym.kind in (SymbolKind.InstanceArray, SymbolKind.GenerateBlockArray):
            queue.extend(_iter_scope(sym))
        elif sym.kind == SymbolKind.GenerateBlock:
            if not getattr(sym, "isUninstantiated", False):
                queue.extend(m for m in _iter_scope(sym) if m.kind in _HIER)
    return found


def _elaborate_alone(comp: Any, sm: Any, names: list[str]) -> tuple[Any, dict[str, Any]]:
    """Bodies for definitions nothing elaborates: an interface (slang never
    makes one a top), or a module instantiated only in an untaken generate arm.

    A second compilation over the same syntax trees, plus one module that
    instantiates each of them with default parameters, gives each a body.
    The first compilation --- its diagnostics, tops and structure --- is not
    touched.  Missing connections and parameters without defaults are errors
    in that second compilation only; the declarations are there regardless.
    """
    from pyslang.ast import Compilation
    from pyslang.syntax import SyntaxTree

    second = Compilation()
    for tree in comp.getSyntaxTrees():
        second.addSyntaxTree(tree)
    insts = {f"__svdb_{i}": name for i, name in enumerate(names)}
    text = "module __svdb_elaborate__;\n" + "".join(
        f"  {_ident(name)} {inst} ();\n" for inst, name in insts.items()) + "endmodule\n"
    second.addSyntaxTree(SyntaxTree.fromText(text, sm, "<svdb>") if sm is not None
                         else SyntaxTree.fromText(text, "<svdb>"))
    found: dict[str, Any] = {}
    for top in second.getRoot().topInstances:
        if top.name != "__svdb_elaborate__":
            continue
        for sym in _iter_scope(top.body):
            name = insts.get(sym.name)
            if name is not None and sym.kind == SymbolKind.Instance and sym.definition.name == name:
                found[name] = sym.body
    return second, found


def _ident(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][\w$]*", name) else f"\\{name} "


_HIER = {SymbolKind.Instance, SymbolKind.InstanceArray, SymbolKind.GenerateBlock,
         SymbolKind.GenerateBlockArray}


class _Extractor:
    def __init__(self, builder: Any, sm: Any, out: Extras, gates: bool = False):
        self.b = builder
        self.sm = sm
        self.out = out
        self._gates = gates
        #: A checker's name -> the body of its first instance seen.
        self._checker_bodies: dict[str, Any] = {}
        #: ``(Checker symbol, parent qname)`` found, built once instances are seen.
        self.checkers: list[tuple[Any, str]] = []
        #: A scope's syntax id -> (that syntax, its DPI exports) (:meth:`_dpi_exports`).
        self._exports: dict[int, tuple[Any, dict[str, dict[str, Any]]]] = {}

    # -- scopes ----------------------------------------------------------------

    def scope(self, scope: Any, qname: str) -> None:
        """A package or class: patch what the builder made, add what it did not."""
        new: list[tuple[Decl, Any]] = []
        for sym in _iter_scope(scope):
            if not _has_real_location(sym, self.sm):
                continue
            k = sym.kind
            name = _join(qname, sym.name)
            if k == SymbolKind.ClassType:
                self.scope(sym, name)
            elif k == SymbolKind.GenericClassDef:
                spec = _specialization(sym, scope)
                if spec is not None:
                    self.scope(spec, name)
            elif k == SymbolKind.TypeAlias:
                detail, kids = self.typedef(sym, qname)
                self.out.patch(name, detail)
                for kid in kids:
                    self.out.add(name, kid)
            elif k in (SymbolKind.Variable, SymbolKind.ClassProperty):
                if _is_covergroup(sym):
                    _guard(self.covergroup_region, sym.type, name)
                    continue
                self.out.patch(name, self.variable_detail(sym))
                for kid in self.inline_members(sym, qname, name):
                    self.out.add(name, kid)
            elif k in (SymbolKind.Subroutine, SymbolKind.MethodPrototype):
                self.out.patch(name, self.subroutine_detail(sym))
                for kid in _guard(self.body, sym, name) or ():
                    self.out.add(name, kid)
            elif k in (SymbolKind.Parameter, SymbolKind.TypeParameter):
                detail = self.parameter_detail(sym)
                if sym.isPortParam:
                    self.out.patch(name, detail)    # a class's #(...) list: the builder has it
                else:
                    new.append((self.decl(sym, "parameter", qname, detail), sym))
            elif k == SymbolKind.NetType:
                new.append((self.decl(sym, "nettype", qname, self.nettype_detail(sym)), sym))
            elif k == SymbolKind.Net:
                new.append((self.decl(sym, "net", qname, self.net_detail(sym)), sym))
            elif k == SymbolKind.LetDecl:
                d = _guard(self.let, sym, qname)
                if d is not None:
                    new.append((d, sym))
            elif k in (SymbolKind.Sequence, SymbolKind.Property):
                d = _guard(self.sva_decl, sym, qname)
                if d is not None:
                    new.append((d, sym))
            elif k == SymbolKind.Checker:
                self.checkers.append((sym, qname))
        self._attach(qname, new)

    def definition(self, body: Any, qname: str) -> None:
        """A module, interface or program body: the builder made only the
        header's parameters and ports."""
        overridden = any(getattr(p, "isOverridden", False) for p in getattr(body, "parameters", ()) or ())
        default_clocking = _default_clocking(body)
        internal = set()
        new: list[tuple[Decl, Any]] = []
        _guard(self.package_imports, getattr(body, "syntax", None), qname)
        for sym in _iter_scope(body):
            if sym.kind == SymbolKind.InterfacePort:
                detail = self.interface_port_detail(sym)
                declarator = getattr(sym, "syntax", None)
                decl = getattr(declarator, "parent", None)
                if type(decl).__name__ == "PortDeclarationSyntax":
                    # ``bus_if.slv bus;`` in the body of a non-ANSI header.
                    d = self.decl(sym, "port", qname, detail)
                    d.signature = f"{_tokens_text(decl.header)} {_tokens_text(declarator)}"
                    new.append((d, sym))
                else:
                    self.out.patch(_join(qname, sym.name), {"ansi": True, **detail})
                continue
            if sym.kind == SymbolKind.Port:
                inner = getattr(sym, "internalSymbol", None)
                if inner is not None:
                    internal.add(inner.name)
                detail = self.port_detail(sym)
                if detail.get("ansi"):
                    self.out.patch(_join(qname, sym.name), detail)
                elif inner is not None:
                    # Non-ANSI (``input a; wire a;``): one object, the port,
                    # declared where its direction is (§3.3).
                    direction = _ARG_DIRS.get(str(getattr(sym, "direction", "")))
                    if direction:
                        detail = {"dir": direction, **detail}
                    d = self.decl(inner, "port", qname, detail)
                    declarator = _port_declarator(body, sym.name)
                    if declarator is not None:
                        decl = declarator.parent
                        d.location = resolve_location(self.sm, declarator.name.location)
                        d.raw_doc = self.b._leading_doc(_Syntax(declarator))
                        d.signature = f"{_tokens_text(decl.header)} {sym.name}"
                    new.append((d, inner))
        for sym in _iter_scope(body):
            k = sym.kind
            if k == SymbolKind.TransparentMember or getattr(sym, "location", None) is None:
                continue
            if not _has_real_location(sym, self.sm) and not getattr(sym, "isImplicit", False):
                continue
            name = _join(qname, sym.name)
            if k in (SymbolKind.Parameter, SymbolKind.TypeParameter):
                detail = self.parameter_detail(sym, evaluate=not overridden)
                if sym.isPortParam:
                    self.out.patch(name, detail)
                else:
                    new.append((self.decl(sym, "parameter", qname, detail), sym))
            elif k == SymbolKind.Net and sym.name not in internal:
                d = self.decl(sym, "net", qname, self.net_detail(sym))
                if getattr(sym, "isImplicit", False):
                    d.flags.append("implicit")
                    d.raw_doc = None
                new.append((d, sym))
            elif k == SymbolKind.Variable and sym.name not in internal:
                d = self.decl(sym, "variable", qname, self.variable_detail(sym))
                d.children = self.inline_members(sym, qname, name)
                new.append((d, sym))
            elif k == SymbolKind.TypeAlias:
                detail, kids = self.typedef(sym, qname, resolve=not overridden)
                d = self.decl(sym, "typedef", qname, detail)
                d.signature = _typedef_signature(sym)
                d.children = kids
                new.append((d, sym))
            elif k == SymbolKind.NetType:
                new.append((self.decl(sym, "nettype", qname, self.nettype_detail(sym)), sym))
            elif k in (SymbolKind.Subroutine, SymbolKind.MethodPrototype):
                # A modport's ``export task t(...)`` also declares ``t`` here;
                # it is the modport's, not a declaration of the body.
                if not type(getattr(sym, "syntax", None)).__name__.startswith("Modport"):
                    d = _guard(self.subroutine, sym, name)
                    if d is not None:
                        new.append((d, sym))
            elif k == SymbolKind.Modport:
                d = _guard(self.modport, sym, name)
                if d is not None:
                    new.append((d, sym))
            elif k == SymbolKind.ClockingBlock:
                d = _guard(self.clocking, sym, body, name)
                if d is not None:
                    if sym.name == default_clocking:
                        d.detail["default"] = True
                    new.append((d, sym))
        if default_clocking:
            self.out.patch(qname, {"default_clocking": {"name": default_clocking}})
        self._attach(qname, new)
        for d in _guard(self.generate_region, body, qname) or ():
            self.out.add(qname, d)

    def _attach(self, parent: str, new: list[tuple[Decl, Any]]) -> None:
        """Add *new* under *parent*, with the builder's comment rules: a
        trailing ``// ...`` after a declaration documents it.  Items of one
        declaration (``int x, y;``, ``modport a (...), b (...);``) share its
        first token, whose trailing comment belongs to the declaration before."""
        for i, (decl, sym) in enumerate(new):
            if i + 1 < len(new) and not decl.is_documented and "implicit" not in decl.flags \
                    and _decl_offset(new[i + 1][1]) != _decl_offset(sym):
                inline = self.b._trailing_for(new[i + 1][1])
                if inline:
                    decl.raw_doc = clean_comment_block(inline)
            self.out.add(parent, decl)

    # -- objects ---------------------------------------------------------------

    def decl(self, sym: Any, kind: str, parent: str, detail: dict[str, Any]) -> Decl:
        d = Decl(kind=kind, name=sym.name, qualified_name=_join(parent, sym.name),
                 location=resolve_location(self.sm, sym.location), detail=detail,
                 raw_doc=self.b._leading_doc(sym))
        d.from_macros = macro_chain(self.sm, sym.location)
        d.signature = _signature(kind, sym, detail)
        self.b._apply_nd(d, sym)
        return d

    def typedef(self, sym: Any, scope: str, resolve: bool = True) -> tuple[dict[str, Any], list[Decl]]:
        """``detail`` and children (literals or fields) of a typedef."""
        declared = sym.targetType
        syntax = getattr(declared, "typeSyntax", None)
        detail: dict[str, Any] = {}
        tn = type(syntax).__name__ if syntax is not None else ""
        t = declared.type
        canon = t.canonicalType
        qname = _join(scope, sym.name)
        kids: list[Decl] = []
        if tn == "EnumTypeSyntax":
            detail["form"] = "enum"
            if syntax.baseType is not None:
                detail["base"] = self.type_ref(_type_text(syntax.baseType, None), getattr(canon, "baseType", None),
                                               None)
            kids = self.enum_members(canon, syntax, qname, scope)
        elif tn == "StructUnionTypeSyntax":
            word = syntax.keyword.valueText
            detail["form"] = "union" if word == "union" else "struct"
            if syntax.packed is not None and syntax.packed.valueText:
                detail["packed"] = True
            if syntax.signing is not None and syntax.signing.valueText == "signed":
                detail["signed"] = True
            tagged = getattr(syntax, "taggedOrSoft", None)
            if tagged is not None and tagged.valueText:
                detail[tagged.valueText] = True
            kids = self.fields(canon, qname)
        else:
            detail["form"] = "interface_based" if tn == "ScopedNameSyntax" and "." in str(syntax) else "alias"
            if syntax is not None:
                dims = getattr(getattr(sym, "syntax", None), "dimensions", None)
                text = _type_text(syntax, dims)
                detail["type"] = self.type_ref(text, t, t if resolve else None)
        return detail, kids

    def enum_members(self, enum: Any, syntax: Any, parent: str, scope: str) -> list[Decl]:
        """The literals of *enum*, documented under *parent*, named in *scope*.

        ``RED[3]`` declares ``RED0`` to ``RED2``; each records the range form
        it came from.  A trailing comment after a literal documents it.
        """
        out: list[Decl] = []
        decls = [m for m in _syntax_list(syntax.members)]
        values = {m.name: m for m in _iter_scope(enum) if m.kind == SymbolKind.EnumValue}
        trailing: list[list[str]] = []
        heads: list[int] = []
        for decl in decls:
            heads.append(len(out))
            name = decl.name.valueText
            prev, leading = split_leading_trivia(decl.getFirstToken())
            trailing.append(prev)
            init = getattr(decl, "initializer", None)
            text = _tokens_text(init.expr) if init is not None else ""
            dims = getattr(decl, "dimensions", None)
            dims_text = _tokens_text(dims) if dims is not None and len(dims) else ""
            names = [name]
            if dims_text:
                names = [n for n in values if re.fullmatch(re.escape(name) + r"\d+", n)]
                names.sort(key=lambda n: values[n].location.offset if values[n].location else 0)
            for i, n in enumerate(names):
                sym = values.get(n)
                expr: dict[str, Any] = {"text": text if i == 0 else ""}
                value = _value(sym)
                if value is not None:
                    expr["value"] = value
                detail: dict[str, Any] = {"value": expr}
                if dims_text:
                    detail["generated_from"] = name + dims_text
                d = Decl(kind="enum_member", name=n, qualified_name=_join(scope, n),
                         location=resolve_location(self.sm, decl.name.location), detail=detail,
                         scope=scope, raw_doc=clean_comment_block(leading) if i == 0 else None)
                d.signature = n + (f" = {text}" if text and i == 0 else "")
                out.append(d)
        _inline_docs(out, heads, trailing, syntax.closeBrace)
        return out

    def fields(self, struct: Any, parent: str) -> list[Decl]:
        out: list[Decl] = []
        heads: list[int] = []
        trailing: list[list[str]] = []
        last = None
        for f in _iter_scope(struct):
            if f.kind != SymbolKind.Field:
                continue
            declarator = f.syntax
            member = getattr(declarator, "parent", None) or declarator
            first = member.getFirstToken()
            here = first.location.offset
            leading: list[str] = []
            if here != last:                # the first declarator of a member
                prev, leading = split_leading_trivia(first)
                heads.append(len(out))
                trailing.append(prev)
                last = here
            ts = f.declaredType.typeSyntax or getattr(member, "type", None)
            if type(ts).__name__ in ("EnumTypeSyntax", "StructUnionTypeSyntax"):
                text = _anonymous_type_text(ts, _dims_text(f))
            else:
                text = _type_text(ts, declarator.dimensions)
            detail = {"type": self.type_ref(text, f.type, None)}
            init = getattr(declarator, "initializer", None)
            if init is not None:
                detail["default"] = {"text": _tokens_text(init.expr)}
            d = Decl(kind="field", name=f.name, qualified_name=_join(parent, f.name),
                     location=resolve_location(self.sm, f.location), detail=detail,
                     raw_doc=clean_comment_block(leading))
            d.signature = f"{detail['type']['text']} {f.name}"
            d.children = self.inline_members(f, parent, d.qualified_name)
            out.append(d)
        close = getattr(getattr(struct, "syntax", None), "closeBrace", None)
        _inline_docs(out, heads, trailing, close)
        return out

    def inline_members(self, sym: Any, scope: str, parent: str) -> list[Decl]:
        """Literals or fields of a type declared inline on *sym*
        (``enum {A, B} st;``, ``struct {...} pt;``)."""
        syntax = getattr(getattr(sym, "declaredType", None), "typeSyntax", None)
        tn = type(syntax).__name__ if syntax is not None else ""
        canon = sym.type.canonicalType
        if tn == "EnumTypeSyntax":
            return self.enum_members(canon, syntax, parent, scope)
        if tn == "StructUnionTypeSyntax":
            return self.fields(canon, parent)
        return []

    def subroutine(self, sym: Any, qname: str) -> Decl:
        """A task or function declared in a definition body (the builder
        makes only those of packages and classes)."""
        parent = _parent(qname)
        is_task = str(getattr(sym, "subroutineKind", "")) == "SubroutineKind.Task"
        d = self.decl(sym, "task" if is_task else "function", parent, self.subroutine_detail(sym))
        d.signature = _subroutine_signature(sym, is_task)
        d.children = self.body(sym, qname)
        if _method_flag(sym, "Pure"):
            d.qualifiers.append("pure")
        return d

    def package_imports(self, syntax: Any, qname: str) -> None:
        """``import p::*;``, ``import p::x;`` and a package's ``export p::x;``
        written in *syntax* (a package or a definition, header included)."""
        decls = list(getattr(getattr(syntax, "header", None), "imports", None) or ())
        decls += [m for m in getattr(syntax, "members", None) or ()
                  if type(m).__name__ in ("PackageImportDeclarationSyntax", "PackageExportDeclarationSyntax")]
        for decl in decls:
            export = type(decl).__name__ == "PackageExportDeclarationSyntax"
            for item in decl.items or ():
                self.import_item(item, qname, export)

    def import_item(self, item: Any, scope: str, export: bool) -> None:
        """One ``p::x`` or ``p::*`` (``*::*`` in an export names no package)."""
        pkg, name = item.package.valueText, item.item.valueText
        if not pkg or not name:
            return
        rec: dict[str, Any] = {"r": "import", "scope": scope, "package": {"name": pkg, "ns": "package"},
                               "item": name}
        if export:
            rec["export"] = True
        loc = resolve_location(self.sm, item.package.location)
        if loc is not None:
            rec["loc"] = loc
        self.out.imports.append(rec)

    def _dpi_exports(self, syntax: Any) -> dict[str, dict[str, Any]]:
        """``export "DPI-C" [c =] function f;`` among *syntax*'s members, by
        SystemVerilog name."""
        # Keyed by id(), so the entry holds *syntax*: pyslang makes a new
        # wrapper per access, and a collected one's id is reused.
        key = id(syntax)
        if key not in self._exports:
            found: dict[str, dict[str, Any]] = {}
            for m in getattr(syntax, "members", None) or ():
                if type(m).__name__ == "DPIExportSyntax":
                    found[m.name.valueText] = {"dir": "export", **_dpi_spec(m)}
            self._exports[key] = (syntax, found)
        return self._exports[key][1]

    def modport(self, sym: Any, qname: str) -> Decl:
        """``modport mst (output a, input .b(e), import t, clocking cb)``."""
        parent = _parent(qname)
        item = sym.syntax
        detail: dict[str, Any] = {}
        for group in _syntax_list(item.ports.ports):
            gn = type(group).__name__
            if gn == "ModportSimplePortListSyntax":
                direction = group.direction.valueText
                for port in _syntax_list(group.ports):
                    entry: dict[str, Any] = {"name": port.name.valueText, "dir": direction}
                    if getattr(port, "expr", None) is not None:
                        entry["expr"] = _expr(port.expr)
                    detail.setdefault("ports", []).append(entry)
            elif gn == "ModportSubroutinePortListSyntax":
                key = "imports" if group.importExport.valueText == "import" else "exports"
                for port in _syntax_list(group.ports):
                    proto = getattr(port, "prototype", None)
                    if proto is not None:
                        entry = {"name": _tokens_text(proto.name), "proto": _tokens_text(proto)}
                    else:
                        entry = {"name": port.name.valueText}
                    detail.setdefault(key, []).append(entry)
            elif gn == "ModportClockingPortSyntax":
                detail.setdefault("clocking", []).append({"name": group.name.valueText})
        d = self.decl(sym, "modport", parent, detail)
        d.signature = f"modport {_tokens_text(item)}"
        return d

    def clocking(self, sym: Any, body: Any, qname: str) -> Decl:
        """A clocking block and, as its children, its clocking variables."""
        parent = _parent(qname)
        syntax = sym.syntax
        word = syntax.globalOrDefault.valueText if syntax.globalOrDefault is not None else ""
        detail: dict[str, Any] = {}
        event = None
        if syntax.event is not None:
            event = _expr(syntax.event, prefix=syntax.at.valueText)
            detail["event"] = event
        if word:
            detail[word] = True                     # default, global
        # A clockvar's expression names signals of the enclosing scope, not
        # the clockvars beside it (LRM 14.3): give those targets.
        outer = {m.name for m in _iter_scope(body) if m.kind != SymbolKind.ClockingBlock and m.name}
        kids: list[Decl] = []
        heads: list[int] = []
        trailing: list[list[str]] = []
        for item in _syntax_list(syntax.items):
            if type(item).__name__ == "DefaultSkewItemSyntax":
                direction = item.direction
                for key, skew in (("default_input", direction.inputSkew), ("default_output", direction.outputSkew)):
                    if skew is not None and _tokens_text(skew):
                        detail[key] = _tokens_text(skew)
                continue
            if type(item).__name__ != "ClockingItemSyntax":
                continue
            prev, leading = split_leading_trivia(item.getFirstToken())
            heads.append(len(kids))
            trailing.append(prev)
            written = _tokens_text(item.direction)
            dirs = [t.valueText for t in (item.direction.input, item.direction.output)
                    if t is not None and t.valueText]
            cv: dict[str, Any] = {"dir": "inout" if len(dirs) > 1 else dirs[0] if dirs else "inout"}
            for key, skew in (("input_skew", item.direction.inputSkew), ("output_skew", item.direction.outputSkew)):
                if skew is not None and _tokens_text(skew):
                    cv[key] = _tokens_text(skew)
            for i, spec in enumerate(_syntax_list(item.decls)):
                name = spec.name.valueText
                this = dict(cv)
                sig = f"{written} {name}"
                value = getattr(spec, "value", None)
                if value is not None:
                    this["expr"] = _expr(value.expr, scope=parent, names=outer)
                    sig += f" = {this['expr']['text']}"
                d = Decl(kind="clockvar", name=name, qualified_name=_join(qname, name),
                         location=resolve_location(self.sm, spec.name.location), detail=this,
                         raw_doc=clean_comment_block(leading) if i == 0 else None)
                d.signature = sig
                kids.append(d)
        _inline_docs(kids, heads, trailing, syntax.endClocking)
        d = self.decl(sym, "clocking", parent, detail)
        d.signature = " ".join(p for p in (word, "clocking", sym.name, event["text"] if event else "") if p)
        d.children = kids
        return d

    # -- structure (D3c): instances, generate, genvar ---------------------------

    def generate_region(self, scope: Any, qname: str) -> list[Decl]:
        """Instances, generate constructs and genvars directly in *scope* (a
        definition body, or one arm or representative iteration of a generate
        construct). Other declaration kinds inside a generate block (nets,
        variables, typedefs, ...) are not extracted yet (D3c follow-up); only
        the structural skeleton is."""
        out: list[Decl] = []
        members = list(_iter_scope(scope))
        i, n = 0, len(members)
        anon_assertions = anon_defparams = 0
        while i < n:
            sym = members[i]
            k = sym.kind
            if k in (SymbolKind.Instance, SymbolKind.UninstantiatedDef):
                d = _guard(self.instance, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k == SymbolKind.InstanceArray:
                if _is_gate_array(sym):
                    if self._gates or _is_udp_instance(sym):
                        d = _guard(self.gate, sym, qname)
                        if d is not None:
                            out.append(d)
                else:
                    d = _guard(self.instance, sym, qname)
                    if d is not None:
                        out.append(d)
                i += 1
            elif k == SymbolKind.PrimitiveInstance:
                if self._gates or _is_udp_instance(sym):
                    d = _guard(self.gate, sym, qname)
                    if d is not None:
                        out.append(d)
                i += 1
            elif k == SymbolKind.Genvar:
                d = self.decl(sym, "genvar", qname, {})
                d.signature = f"genvar {sym.name}"
                out.append(d)
                i += 1
            elif k == SymbolKind.GenerateBlockArray:
                d = _guard(self.generate_for, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k == SymbolKind.GenerateBlock:
                j = i
                ci = getattr(sym, "constructIndex", None)
                group = []
                while j < n and members[j].kind == SymbolKind.GenerateBlock \
                        and getattr(members[j], "constructIndex", None) == ci:
                    group.append(members[j])
                    j += 1
                out.extend(_guard(self.generate_arms, group, qname) or ())
                i = j
            elif k == SymbolKind.LetDecl:
                d = _guard(self.let, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k in (SymbolKind.Sequence, SymbolKind.Property):
                d = _guard(self.sva_decl, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k == SymbolKind.CheckerInstance:
                d = _guard(self.checker_instance, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k == SymbolKind.ProceduralBlock and _is_concurrent_assertion(sym):
                labeled = sym.syntax.statement.label is not None
                d = _guard(self.assertion, sym, qname, None if labeled else anon_assertions)
                if d is not None:
                    out.append(d)
                if not labeled:
                    anon_assertions += 1
                i += 1
            elif k == SymbolKind.ProceduralBlock:
                d = _guard(self.process, sym, qname)
                if d is not None:
                    out.append(d)
                i += 1
            elif k == SymbolKind.DefParam:
                d = _guard(self.defparam, sym, qname, anon_defparams)
                if d is not None:
                    out.append(d)
                anon_defparams += 1
                i += 1
            else:
                i += 1
        return out

    def _defined_externally(self, body: Any) -> bool:
        """Whether *body*'s definition comes from ``sv_external_sources``."""
        origin_of = getattr(self.b, "origin_of", None)
        if origin_of is None or not getattr(self.b, "external_files", None):
            return False
        try:
            path = self.sm.getFileName(body.definition.location)
        except Exception:
            return False
        return origin_of(str(path)) is not None

    def instance(self, sym: Any, qname: str) -> Decl:
        """One instantiation site: ``leaf #(.W(4)) u1 (.a(x), .b(y))``, or an
        instance array, or a site whose definition is not in this compilation
        (``state: unresolved``: its connections are still recorded)."""
        array = sym if sym.kind == SymbolKind.InstanceArray else None
        element = _first_element(array) if array is not None else sym
        inst_syntax = element.syntax if element is not None else sym.syntax
        hi = inst_syntax.parent
        type_name = hi.type.valueText if getattr(hi, "type", None) is not None else ""
        body = getattr(element, "body", None) if element is not None else None
        of_kind = self._defs_by_name().get(type_name)
        if body is not None:
            of_kind = _DEFINITION_KINDS.get(str(getattr(body.definition, "definitionKind", ""))) or of_kind
        state = "ok" if body is not None else "unresolved"
        if body is not None and self._defined_externally(body):
            state = "external"
        detail: dict[str, Any] = {"of": {"name": type_name}, "of_kind": of_kind or "unknown",
                                   "state": state}
        if array is not None:
            detail["array"] = {"dims": _range_text(array), "count": _element_count(array)}
        port_dirs: dict[str, str] = {}
        if body is not None:
            for p in getattr(body, "portList", ()) or ():
                direction = _ARG_DIRS.get(str(getattr(p, "direction", "")))
                if direction:
                    port_dirs[p.name] = direction
        if hi.parameters is not None:
            detail["params"] = self._instance_params(hi.parameters, self._type_params(body))
        detail["conns"] = self._instance_conns(inst_syntax, port_dirs)
        detail["bind"] = self._bind_detail(hi)
        d = self.decl(array if array is not None else sym, "instance", qname, detail)
        params_text = _tokens_text(hi.parameters) if hi.parameters is not None else ""
        d.signature = " ".join(p for p in (type_name, params_text, _tokens_text(inst_syntax)) if p)
        return d

    def _bind_detail(self, hi: Any) -> dict[str, Any] | None:
        """``detail.bind`` when *hi* (a ``HierarchyInstantiationSyntax``) is the
        instantiation half of a ``bind`` directive.

        A bind's instance is elaborated directly into the *target*
        definition's own body (LRM 23.11), so :meth:`instance` already parents
        and names it correctly with no change: this only has to recognize the
        directive and describe where it was written. ``from`` is the simple
        name of the nearest enclosing module/interface/program; a bind
        written at compilation-unit scope has none, so it is left undescribed
        (``bind: null`` would be wrong -- the instance is still bind-created --
        but there is nothing to resolve ``target_def`` from either, so this
        pass skips the detail rather than guess)."""
        bd = hi.parent
        if type(bd).__name__ != "BindDirectiveSyntax":
            return None
        from_name = _enclosing_definition_name(bd)
        if from_name is None:
            return None
        detail: dict[str, Any] = {"from": from_name, "target_def": {"name": _tokens_text(bd.target)}}
        insts = getattr(bd, "targetInstances", None)
        targets = [_tokens_text(t) for t in getattr(insts, "targets", ())] if insts is not None else []
        if targets:
            detail["target_insts"] = targets
        return detail

    def gate(self, sym: Any, qname: str) -> Decl:
        """One built-in gate instance (``and g1(y, a, b);``), or a gate array
        (``and g[3:0] (...)``).  A different symbol kind from a module
        instance (``PrimitiveInstance``/``PrimitiveInstantiationSyntax``, no
        ``.parameters``) and a different array shape (no ``.body`` on an
        element, so :func:`_first_element` does not apply -- the first
        element is always real, a gate is never conditionally elaborated).
        Opt-in only (``self._gates``): see :func:`extract`."""
        array = sym if sym.kind == SymbolKind.InstanceArray else None
        element = next(iter(array), None) if array is not None else sym
        inst_syntax = element.syntax
        pis = inst_syntax.parent
        type_name = pis.type.valueText if getattr(pis, "type", None) is not None else ""
        of_kind = "primitive" if _is_udp_instance(element) else "gate"
        detail: dict[str, Any] = {"of": {"name": type_name}, "of_kind": of_kind, "state": "ok"}
        if array is not None:
            detail["array"] = {"dims": _range_text(array), "count": sum(1 for _ in array)}
        detail["conns"] = self._instance_conns(inst_syntax, {})
        d = self.decl(array if array is not None else sym, "instance", qname, detail)
        d.signature = " ".join(p for p in (type_name, _tokens_text(inst_syntax)) if p)
        return d

    def _defs_by_name(self) -> dict[str, str]:
        cache = getattr(self, "_defs_cache", None)
        if cache is None:
            comp = getattr(self.b, "compilation", None)
            cache = {}
            if comp is not None:
                for defn in comp.getDefinitions():
                    mapped = _DEFINITION_KINDS.get(str(getattr(defn, "definitionKind", "")))
                    if mapped:
                        cache[defn.name] = mapped
            self._defs_cache = cache
        return cache

    def _type_params(self, body: Any) -> list[tuple[str, bool]]:
        """``(name, is_type_param)`` of *body*'s ``#(...)`` parameters, in
        declaration order; empty when *body* is not known."""
        if body is None:
            return []
        return [(m.name, m.kind == SymbolKind.TypeParameter)
                for m in getattr(body, "parameters", ()) or () if getattr(m, "isPortParam", False)]

    def _instance_params(self, pva: Any, type_params: list[tuple[str, bool]]) -> list[dict[str, Any]]:
        by_name = dict(type_params)
        out: list[dict[str, Any]] = []
        for pos, item in enumerate(_syntax_list(pva.parameters)):
            named = type(item).__name__ == "NamedParamAssignmentSyntax"
            name = item.name.valueText if named else None
            is_type = by_name.get(name, False) if named else (pos < len(type_params) and type_params[pos][1])
            entry: dict[str, Any] = {"pos": pos, "mode": "named" if named else "positional"}
            if name:
                entry["name"] = name
            expr = getattr(item, "expr", None)
            if is_type:
                entry["type"] = self.type_ref(_tokens_text(expr), None, None) if expr is not None else {"text": ""}
            else:
                entry["value"] = _expr(expr) if expr is not None else {"text": ""}
            out.append(entry)
        return out

    def _instance_conns(self, inst_syntax: Any, port_dirs: dict[str, str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pos, item in enumerate(_syntax_list(inst_syntax.connections)):
            tn = type(item).__name__
            entry: dict[str, Any] = {"pos": pos}
            if tn == "WildcardPortConnectionSyntax":
                entry["mode"] = "wildcard"
            elif tn == "OrderedPortConnectionSyntax":
                entry["mode"] = "positional"
                if item.expr is not None:
                    entry["expr"] = _expr(item.expr)
            elif tn == "NamedPortConnectionSyntax":
                name = item.name.valueText
                entry["port"] = name
                if item.openParen is None:
                    entry["mode"] = "implicit"
                    entry["expr"] = {"text": name, "refs": [{"at": [0, len(name)], "name": name}]}
                elif item.expr is None:
                    entry["mode"] = "unconnected"
                else:
                    entry["mode"] = "named"
                    entry["expr"] = _expr(item.expr)
                direction = port_dirs.get(name)
                if direction:
                    entry["dir"] = direction
            elif tn == "EmptyPortConnectionSyntax":
                entry["mode"] = "positional"
            else:
                continue
            out.append(entry)
        if port_dirs and any(e["mode"] == "wildcard" for e in out):
            # The definition is known: expand ".*" into one implicit entry
            # per unconnected port, keeping the wildcard marker (plan §5.2.1).
            named = {e["port"] for e in out if e.get("port")}
            for name, direction in port_dirs.items():
                if name in named:
                    continue
                out.append({"port": name, "pos": len(out), "mode": "implicit", "dir": direction,
                            "expr": {"text": name, "refs": [{"at": [0, len(name)], "name": name}]}})
        return out

    def generate_for(self, sym: Any, qname: str) -> Decl:
        """``for (genvar i = 0; i < 4; i++) begin : g_lp ... end``.

        ``genvar i`` declared inline scopes the genvar to the loop: each
        iteration gets its own symbol, so there is nothing outside to
        resolve the loop's ``genvar`` ref to.  A genvar child of the loop
        itself, with an explicit target, is made instead."""
        syntax = sym.syntax
        gv_name = syntax.identifier.valueText
        detail: dict[str, Any] = {"construct": "for"}
        d = self.decl(sym, "generate", qname, detail)
        element = _first_generate_element(sym)
        kids: list[Decl] = []
        gv_qname: str | None = None
        if getattr(syntax, "genvar", None) is not None:
            gv_sym = next((m for m in _iter_scope(sym)
                           if m.kind == SymbolKind.Genvar and m.name == gv_name), None)
            if gv_sym is not None:
                gd = self.decl(gv_sym, "genvar", d.qualified_name, {})
                gd.signature = f"genvar {gv_name}"
                kids.append(gd)
                gv_qname = gd.qualified_name
        detail["genvar"] = {"name": gv_name, "target": gv_qname} if gv_qname else {"name": gv_name}
        names = {gv_name} if gv_qname else None
        loop: dict[str, Any] = {}
        if syntax.initialExpr is not None:
            loop["init"] = _expr(syntax.initialExpr, scope=d.qualified_name, names=names)
        if syntax.stopExpr is not None:
            loop["cond"] = _expr(syntax.stopExpr, scope=d.qualified_name, names=names)
        if syntax.iterationExpr is not None:
            loop["step"] = _expr(syntax.iterationExpr, scope=d.qualified_name, names=names)
        if loop:
            detail["loop"] = loop
        d.signature = f"for ({_tokens_text(syntax.initialExpr)}; {_tokens_text(syntax.stopExpr)};" \
                      f" {_tokens_text(syntax.iterationExpr)})"
        if element is not None:
            kids.extend(self.generate_region(element, d.qualified_name))
        d.children = kids
        return d

    def generate_arms(self, group: list[Any], qname: str) -> list[Decl]:
        """The sibling arms of one ``if``/``case`` generate construct.  Arms
        with no label (an untaken branch, most often) may share a computed
        name; :func:`canon.disambiguate` keeps them unique as siblings even
        though only one is ever elaborated."""
        names = canon.disambiguate([sym.name or self._genblk_fallback(sym) for sym in group])
        out: list[Decl] = []
        for arm, (sym, name) in enumerate(zip(group, names)):
            d = _guard(self._generate_arm, sym, qname, name, arm)
            if d is not None:
                out.append(d)
        return out

    def _genblk_fallback(self, sym: Any) -> str:
        ci = getattr(sym, "constructIndex", None)
        return f"genblk{ci}" if ci is not None else "genblk"

    def _generate_arm(self, sym: Any, qname: str, name: str, arm: int) -> Decl:
        syntax = sym.syntax
        wrapper = syntax.parent
        wn = type(wrapper).__name__
        construct = "if" if wn in ("IfGenerateSyntax", "ElseClauseSyntax") else "case"
        detail: dict[str, Any] = {"construct": construct, "arm": arm}
        if wn == "IfGenerateSyntax":
            detail["cond"] = _expr(wrapper.condition)
        elif wn in ("StandardCaseItemSyntax", "DefaultCaseItemSyntax"):
            casegen = _enclosing(wrapper, "CaseGenerateSyntax")
            if casegen is not None and getattr(casegen, "condition", None) is not None:
                detail["cond"] = _expr(casegen.condition)
            detail["case_items"] = [_expr(e) for e in _syntax_list(getattr(wrapper, "expressions", None))] \
                if wn == "StandardCaseItemSyntax" else []
        d = Decl(kind="generate", name=name, qualified_name=_join(qname, name),
                 location=resolve_location(self.sm, sym.location), detail=detail,
                 raw_doc=self.b._leading_doc(sym))
        d.signature = _generate_arm_signature(construct, detail)
        d.children = self.generate_region(sym, d.qualified_name)
        return d

    # -- verification (D3d): let, assertion ------------------------------------

    def let(self, sym: Any, qname: str) -> Decl:
        """``let name(args) = expr;`` (LRM 11.12)."""
        detail: dict[str, Any] = {}
        args = self._assertion_port_args(getattr(sym, "ports", ()) or ())
        if args:
            detail["args"] = args
        expr = getattr(sym.syntax, "expr", None)
        if expr is not None:
            detail["expr"] = _expr(expr)
        d = self.decl(sym, "let", qname, detail)
        d.signature = f"let {sym.name}({', '.join(a['name'] for a in args)})"
        return d

    def sva_decl(self, sym: Any, qname: str) -> Decl:
        """A named ``sequence`` (LRM 16.8) or ``property`` (16.12, kind
        ``sva_property``: ``property`` already means a class data member):
        its formal arguments and its body as an ``Expr``."""
        is_seq = sym.kind == SymbolKind.Sequence
        detail: dict[str, Any] = {}
        args = self._assertion_port_args(getattr(sym, "ports", ()) or ())
        if args:
            detail["args"] = args
        body = sym.syntax.seqExpr if is_seq else sym.syntax.propertySpec
        if body is not None:
            detail["body"] = _expr(body)
        kind = "sequence" if is_seq else "sva_property"
        d = self.decl(sym, kind, qname, detail)
        keyword = "sequence" if is_seq else "property"
        d.signature = f"{keyword} {sym.name}" + (f"({', '.join(a['name'] for a in args)})" if args else "")
        return d

    def checker(self, sym: Any, qname: str, body: Any | None) -> Decl:
        """A ``checker`` declaration (LRM 17): its formal arguments, and the
        declarations in *body* -- the body of one of its instances, since
        slang elaborates a checker's contents only per instance. A checker
        never instantiated keeps only its arguments."""
        detail: dict[str, Any] = {}
        args = self._assertion_port_args(getattr(sym, "ports", ()) or ())
        if args:
            detail["args"] = args
        d = self.decl(sym, "checker", qname, detail)
        d.signature = f"checker {sym.name}" + (f"({', '.join(a['name'] for a in args)})" if args else "")
        if body is not None:
            d.children = _guard(self.generate_region, body, d.qualified_name) or []
        return d

    def checker_instance(self, sym: Any, qname: str) -> Decl:
        """``chk u_chk(clk, v);``: an ``instance`` of ``of_kind: checker``."""
        inst_syntax = sym.syntax
        hi = inst_syntax.parent
        type_name = hi.type.valueText if getattr(hi, "type", None) is not None else ""
        detail: dict[str, Any] = {"of": {"name": type_name}, "of_kind": "checker", "state": "ok"}
        if hi.parameters is not None:
            detail["params"] = self._instance_params(hi.parameters, [])
        detail["conns"] = self._instance_conns(inst_syntax, {})
        body = getattr(sym, "body", None)
        if body is not None:
            self._checker_bodies.setdefault(type_name, body)
        d = self.decl(sym, "instance", qname, detail)
        params_text = _tokens_text(hi.parameters) if hi.parameters is not None else ""
        d.signature = " ".join(p for p in (type_name, params_text, _tokens_text(inst_syntax)) if p)
        return d

    # -- other (D3e): primitive, config, defparam -------------------------------

    def primitive(self, sym: Any, qname: str) -> Decl:
        """A user-defined primitive (LRM 29): ``sequential``, a sequential
        UDP's ``initial`` value, and its ports as ``port`` children. The
        state table is not recorded."""
        detail: dict[str, Any] = {"sequential": bool(sym.isSequential)}
        init = getattr(sym.syntax.body, "initialStmt", None)
        if init is not None and init.value is not None:
            detail["initial"] = _expr(init.value)
        d = self.decl(sym, "primitive", qname, detail)
        ports = list(getattr(sym, "ports", ()) or ())
        for p in ports:
            out = str(p.direction).rsplit(".", 1)[-1].startswith("Out")
            # Not self.decl: a port's leading comment is the primitive's own.
            kid = Decl(kind="port", name=p.name, qualified_name=_join(d.qualified_name, p.name),
                       location=resolve_location(self.sm, p.location), detail={"dir": "output" if out else "input"})
            kid.signature = f"{'output' if out else 'input'} {p.name}"
            d.children.append(kid)
        d.signature = f"primitive {sym.name}({', '.join(p.name for p in ports)})"
        return d

    def config(self, sym: Any, qname: str) -> Decl:
        """A ``config`` (LRM 33), recorded but not applied: its ``design``
        cells (the library prefix dropped, so each resolves to the design
        object of that name) and each rule as text."""
        syntax = sym.syntax
        design = [{"name": c.cell.valueText, "ns": "design"} for c in (syntax.topCells or ())]
        detail: dict[str, Any] = {"design": design} if design else {}
        rules = [_tokens_text(r) for r in (syntax.rules or ())]
        if rules:
            detail["rules"] = rules
        d = self.decl(sym, "config", qname, detail)
        d.signature = f"config {sym.name}"
        return d

    def process(self, sym: Any, qname: str) -> Decl | None:
        """An ``initial``/``final``/``always*`` procedure (LRM 9.2) whose body,
        after any timing control, is a named block (``always_ff @(...) begin :
        l``): the process takes the label, and the block's own named blocks
        are its children. Unlabelled processes are ``$process#N`` objects the
        ``anonymous`` section would carry; no option asks for that section
        yet, so they -- and the named blocks inside them -- are not emitted."""
        proc = _PROC_KINDS.get(str(sym.procedureKind).rsplit(".", 1)[-1])
        if proc is None:
            return None
        body, stmt = sym.body, sym.syntax.statement
        detail: dict[str, Any] = {"proc": proc}
        if body.kind.name == "Timed":
            tc = stmt.timingControl
            if "EventControl" in type(tc).__name__:
                detail["event"] = _expr(tc)
            body = body.stmt
        block = getattr(body, "blockSymbol", None) if body.kind.name == "Block" else None
        if block is None or not block.name:
            return None
        d = Decl(kind="process", name=block.name, qualified_name=_join(qname, block.name),
                 location=resolve_location(self.sm, block.location), detail=detail,
                 raw_doc=self.b._leading_doc(sym))
        d.signature = f"{proc} begin : {block.name}"
        d.children = self.body(block, d.qualified_name)
        return d

    def body(self, scope: Any, qname: str, outer: frozenset[str] = frozenset()) -> list[Decl]:
        """The named blocks and immediate assertions directly in *scope* (a
        process's block, a subroutine, or a named block); *outer* are the
        names declared in the blocks and subroutine around it."""
        local = outer | _local_names(scope)
        out = self.blocks(scope, qname, local) + self.immediate_assertions(scope, qname, local)
        out.sort(key=lambda d: (d.location.line, d.location.column) if d.location else (1 << 30, 0))
        return out

    def immediate_assertions(self, scope: Any, qname: str, local: frozenset[str]) -> list[Decl]:
        """The immediate and deferred assertions (LRM 16.3, 16.4) among
        *scope*'s statements, in source order, outside any named block
        (that block's own :meth:`body` has those). Labelled ones take the
        label; others are ``$assertion#N``."""
        out: list[Decl] = []
        anon = 0
        for stmt in _immediate_assertion_syntax(getattr(getattr(scope, "syntax", None), "items", None)):
            verb = _ASSERTION_VERBS.get(stmt.keyword.valueText)
            if verb is None:
                continue
            form, delay = "immediate", stmt.delay
            if delay is not None:
                form = "deferred_final" if delay.finalKeyword.valueText else "deferred_0"
            detail: dict[str, Any] = {"verb": verb, "form": form}
            expr = getattr(stmt.expr, "expression", None)
            if expr is not None:
                prop = _expr(expr)
                # An argument or local variable is not an object to refer to.
                refs = [r for r in prop.pop("refs", ()) if r["name"] not in local]
                if refs:
                    prop["refs"] = refs
                detail["property"] = prop
            label = stmt.label
            if label is not None:
                name, loc = label.name.valueText, label.name.location
            else:
                name, loc = canon.anonymous_name("assertion", anon), stmt.keyword.location
                anon += 1
            _, leading = split_leading_trivia(stmt.getFirstToken())
            d = Decl(kind="assertion", name=name, qualified_name=_join(qname, name),
                     location=resolve_location(self.sm, loc), detail=detail,
                     raw_doc=clean_comment_block(leading))
            when = {"deferred_0": " #0", "deferred_final": " final"}.get(form, "")
            d.signature = f"{verb}{when} (...)"
            out.append(d)
        return out

    def blocks(self, scope: Any, qname: str, local: frozenset[str] = frozenset()) -> list[Decl]:
        """The named ``begin``/``fork`` blocks (LRM 9.3) directly in *scope*
        (a process's block, a subroutine, or a named block); an unnamed
        block's named blocks belong to the nearest named parent."""
        out: list[Decl] = []
        for m in _iter_scope(scope):
            if m.kind != SymbolKind.StatementBlock \
                    or type(getattr(m, "syntax", None)).__name__ != "BlockStatementSyntax":
                continue    # a labelled assertion's StatementBlock is not a block
            if not m.name:
                out.extend(self.blocks(m, qname, local))
                continue
            detail: dict[str, Any] = {}
            fork = _FORK_KINDS.get(str(m.blockKind).rsplit(".", 1)[-1])
            if fork is not None:
                detail["fork"] = fork
            # The builder's _leading_doc climbs to the enclosing declaration
            # (the process); a block's doc is on its own first token.
            _, leading = split_leading_trivia(m.syntax.getFirstToken())
            d = Decl(kind="block", name=m.name, qualified_name=_join(qname, m.name),
                     location=resolve_location(self.sm, m.location), detail=detail,
                     raw_doc=clean_comment_block(leading))
            d.signature = f"{'fork' if fork else 'begin'} : {m.name}"
            d.children = self.body(m, d.qualified_name, local)
            out.append(d)
        return out

    def defparam(self, sym: Any, qname: str, ordinal: int) -> Decl:
        """One ``defparam`` assignment (LRM 23.10): never named, so
        ``$defparam#N`` in source order within *qname*; ``target`` is the
        hierarchical name as written."""
        syntax = sym.syntax
        detail: dict[str, Any] = {"target": _tokens_text(syntax.name)}
        value = getattr(syntax.setter, "expr", None)
        if value is not None:
            detail["value"] = _expr(value)
        name = canon.anonymous_name("defparam", ordinal)
        d = Decl(kind="defparam", name=name, qualified_name=_join(qname, name),
                 location=resolve_location(self.sm, sym.location), detail=detail,
                 raw_doc=self.b._leading_doc(sym))
        d.signature = f"defparam {_tokens_text(syntax)}"
        return d

    def _assertion_port_args(self, ports: Any) -> list[dict[str, Any]]:
        """``Arg`` entries for a ``let``'s formal arguments (``AssertionPort``
        symbols): not a subroutine's arguments, so :meth:`subroutine_detail`
        does not apply."""
        out: list[dict[str, Any]] = []
        for p in ports:
            a: dict[str, Any] = {"name": p.name}
            text = _type_str(getattr(p, "type", None))
            if text and text not in ("void", "<error>"):
                a["type"] = self.type_ref(text, getattr(p, "type", None), None)
            default = getattr(getattr(p, "syntax", None), "defaultValue", None)
            if default is not None and getattr(default, "expr", None) is not None:
                a["default"] = _expr(default.expr)
            out.append(a)
        return out

    def assertion(self, sym: Any, qname: str, anon_ordinal: int | None) -> Decl | None:
        """A concurrent assertion written directly in a definition, generate
        or checker body (LRM 16): ``assert property (...)`` and its sibling
        verbs, as a module item, wrapped by slang in a ``ProceduralBlock``
        whose syntax is ``ConcurrentAssertionMemberSyntax``.

        An *immediate* assertion (``assert (expr) ...;``) is a statement,
        found by :meth:`immediate_assertions` under its process, block or
        subroutine.

        A label (``check_ab: assert ...``) lives on a *different* symbol
        slang makes alongside this one (a same-named ``StatementBlock``
        sibling, left to fall through ``generate_region`` unhandled) --
        rather than correlate the two, the label is read straight from the
        statement's own syntax. With none, *anon_ordinal* names it
        (``$assertion#0``, per object)."""
        stmt = sym.syntax.statement
        verb = _ASSERTION_VERBS.get(stmt.keyword.valueText)
        if verb is None:
            return None
        detail: dict[str, Any] = {"verb": verb, "form": "concurrent"}
        spec = stmt.propertySpec
        if type(spec).__name__ == "PropertySpecSyntax":
            if spec.expr is not None:
                detail["property"] = _expr(spec.expr)
            clocking = spec.clocking
            if clocking is not None and getattr(clocking, "expr", None) is not None:
                detail["clock"] = _expr(clocking.expr)
            disable = spec.disable
            if disable is not None and disable.expr is not None:
                detail["disable_iff"] = _expr(disable.expr)
        elif spec is not None:
            detail["property"] = _expr(spec)
        label = stmt.label
        name = label.name.valueText if label is not None else canon.anonymous_name("assertion", anon_ordinal or 0)
        d = Decl(kind="assertion", name=name, qualified_name=_join(qname, name),
                 location=resolve_location(self.sm, sym.location), detail=detail,
                 raw_doc=self.b._leading_doc(sym))
        d.signature = f"{verb} property (...)"
        return d

    # -- verification (D3d): covergroup extras, cross, bins ---------------------

    def covergroup_region(self, cgtype: Any, qname: str) -> None:
        """Patches the builder's ``covergroup`` object with ``sample_args``,
        and adds ``cross`` (new) and each coverpoint's ``expr``/``iff``/
        ``type`` and ``bins`` children, under the coverpoint the builder
        already made.

        ``extends`` (1800-2023 covergroup inheritance) is not written here:
        this pyslang build's parser does not accept the construct at all
        (``covergroup cg extends base;`` fails to parse), so there is
        nothing to read a value from yet."""
        body = getattr(cgtype, "body", None)
        if body is None:
            return
        sample = next((m for m in _iter_scope(body) if m.kind == SymbolKind.Subroutine and m.name == "sample"), None)
        if sample is not None:
            args = self._subroutine_args(sample)
            if args:
                self.out.patch(qname, {"sample_args": args})
        for cp in _iter_scope(body):
            if cp.kind == SymbolKind.Coverpoint:
                name = _join(qname, cp.name)
                self.out.patch(name, self.coverpoint_detail(cp))
                for b in _iter_scope(cp):
                    if b.kind == SymbolKind.CoverageBin:
                        self.out.add(name, self.bins(b, name))
            elif cp.kind == SymbolKind.CoverCross:
                self.out.add(qname, self.cross(cp, qname))

    def _subroutine_args(self, sub: Any) -> list[dict[str, Any]]:
        """``Arg`` entries of a plain subroutine's formal arguments (shared
        shape with :meth:`subroutine_detail`, but without a return type)."""
        out: list[dict[str, Any]] = []
        for arg in getattr(sub, "arguments", []) or []:
            a: dict[str, Any] = {"name": arg.name}
            direction = _ARG_DIRS.get(str(getattr(arg, "direction", "")))
            if direction:
                a["dir"] = direction
            text = _declared_text(arg)
            if text:
                a["type"] = self.type_ref(text, arg.type, None)
            out.append(a)
        return out

    def coverpoint_detail(self, sym: Any) -> dict[str, Any]:
        syntax = sym.syntax
        detail: dict[str, Any] = {}
        if getattr(syntax, "expr", None) is not None:
            detail["expr"] = _expr(syntax.expr)
        iff = getattr(syntax, "iff", None)
        if iff is not None and getattr(iff, "expr", None) is not None:
            detail["iff"] = _expr(iff.expr)
        text = _type_str(getattr(sym, "type", None))
        if text:
            detail["type"] = self.type_ref(text, sym.type, None)
        return detail

    def cross(self, sym: Any, qname: str) -> Decl:
        """``cross cp_a, cp_b;`` (LRM 19.6): a new object, since the builder
        (D2) did not know about coverage crosses. ``items`` names the
        crossed coverpoints, always siblings in this same covergroup."""
        targets = list(getattr(sym, "targets", ()) or ())
        detail: dict[str, Any] = {}
        if targets:
            detail["items"] = [{"name": t.name, "target": _join(qname, t.name)} for t in targets]
        syntax_iff = getattr(sym.syntax, "iff", None)
        if syntax_iff is not None and getattr(syntax_iff, "expr", None) is not None:
            detail["iff"] = _expr(syntax_iff.expr)
        d = self.decl(sym, "cross", qname, detail)
        d.signature = f"cross {', '.join(t.name for t in targets)}"
        return d

    def bins(self, sym: Any, qname: str) -> Decl:
        """One ``bins``/``illegal_bins``/``ignore_bins`` under a coverpoint
        or cross (LRM 19.5.x): a new object (the parent's table, per plan).

        ``with (...)`` (an array bin's extra filter) is not read yet --
        this pass covers the common shapes (ranges, wildcard, default,
        transition lists), not every initializer form."""
        detail: dict[str, Any] = {"bin_kind": _BIN_KINDS.get(str(sym.binsKind), "bins")}
        if getattr(sym, "isWildcard", False):
            detail["wildcard"] = True
        if getattr(sym, "isDefault", False) or getattr(sym, "isDefaultSequence", False):
            detail["default"] = True
        if getattr(sym, "isArray", False):
            detail["array"] = True
        syntax = sym.syntax
        size = getattr(syntax, "size", None)
        if size is not None and getattr(size, "expr", None) is not None:
            detail["size"] = _expr(size.expr)
        initializer = getattr(syntax, "initializer", None)
        if initializer is not None:
            if type(initializer).__name__ == "TransListCoverageBinInitializerSyntax":
                detail["transition"] = True
            detail["values"] = _tokens_text(initializer)
        iff = getattr(syntax, "iff", None)
        if iff is not None and getattr(iff, "expr", None) is not None:
            detail["iff"] = _expr(iff.expr)
        d = self.decl(sym, "bins", qname, detail)
        d.signature = f"bins {sym.name} = {detail.get('values', '...')}"
        return d

    # -- detail ----------------------------------------------------------------

    def interface_port_detail(self, sym: Any) -> dict[str, Any]:
        """``bus_if.mst bus``, ``interface bus``, ``interface.slv bus``."""
        ifc: dict[str, Any] = {}
        if getattr(sym, "isGeneric", False):
            ifc["generic"] = True
        else:
            # ``bus_if links [2]`` parses as a variable port; slang knows better.
            header = getattr(getattr(sym.syntax, "parent", None), "header", None)
            token = getattr(header, "nameOrKeyword", None)
            name = token.valueText if token is not None else ""
            if not name and getattr(sym, "interfaceDef", None) is not None:
                name = sym.interfaceDef.name
            if name:
                ifc["ref"] = {"name": name}
        if getattr(sym, "modport", ""):
            ifc["modport"] = sym.modport
        return {"interface": ifc}

    def type_ref(self, text: str, t: Any, resolve_from: Any | None) -> dict[str, Any]:
        """A ``TypeRef``: *text* as written, its form, the name it starts with,
        and, for a named type, what it resolves to."""
        ref: dict[str, Any] = {"text": text}
        form = _form(t)
        if form:
            ref["form"] = form
        # The name a type starts with, after ``virtual [interface]``.
        start = re.match(r"(?:virtual\s+(?:interface\s+)?)?", text).end()
        m = _NAME.match(text, start)
        if m and m.group(0).split("::")[0].strip() not in _BUILTIN_TYPES:
            ref["refs"] = [{"at": [start, m.end()], "name": re.sub(r"\s+", "", m.group(0))}]
        if resolve_from is not None and form in ("typedef", "type_param"):
            resolved = _type_str(resolve_from.canonicalType)
            if resolved and resolved != text:
                ref["resolved"] = resolved
        return ref

    def variable_detail(self, sym: Any) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        text = _declared_text(sym)
        syntax = getattr(sym.declaredType, "typeSyntax", None)
        if type(syntax).__name__ in ("EnumTypeSyntax", "StructUnionTypeSyntax"):
            text = _anonymous_type_text(syntax, _dims_text(sym))
        if text:
            detail["type"] = self.type_ref(text, sym.type, None)
        init = getattr(sym.declaredType, "initializerSyntax", None)
        if init is not None:
            detail["init"] = {"text": _tokens_text(init)}
        return detail

    def parameter_detail(self, sym: Any, evaluate: bool = True) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        if sym.isLocalParam:
            detail["local"] = True
        if sym.isPortParam:
            detail["port_list"] = True
        if sym.kind == SymbolKind.TypeParameter:
            detail["type_param"] = True
            ts = getattr(sym.targetType, "typeSyntax", None)
            if ts is not None and _tokens_text(ts):
                detail["default_type"] = self.type_ref(_tokens_text(ts), sym.targetType.type, None)
            return detail
        ts = getattr(sym.declaredType, "typeSyntax", None)
        text = _tokens_text(ts) if ts is not None else ""
        if text:
            detail["type"] = self.type_ref(re.sub(r"^(parameter|localparam)\s+", "", text), sym.type, None)
        init = getattr(sym.declaredType, "initializerSyntax", None)
        if init is not None:
            expr: dict[str, Any] = {"text": _tokens_text(init)}
            if evaluate:
                value = _value(sym)
                if value is not None and value != expr["text"]:
                    expr["value"] = value
            detail["default"] = expr
        return detail

    def port_detail(self, sym: Any) -> dict[str, Any]:
        """Type and net type of a port; the direction is already there."""
        detail: dict[str, Any] = {"ansi": True}
        declarator = getattr(sym, "syntax", None)
        port = getattr(declarator, "parent", None)
        header = getattr(port, "header", None)
        if header is None:
            # A non-ANSI port: its type is on the body declaration.
            detail = {}
            inner = getattr(sym, "internalSymbol", None)
            if inner is not None:
                detail.update(self._internal(inner))
            return detail
        hn = type(header).__name__
        if hn == "NetPortHeaderSyntax":
            detail["net_type"] = header.netType.valueText
        elif hn == "VariablePortHeaderSyntax":
            inner = getattr(sym, "internalSymbol", None)
            if getattr(header, "varKeyword", None) is not None and header.varKeyword.valueText:
                detail["net_type"] = "var"
            elif inner is not None and inner.kind == SymbolKind.Net:
                detail["net_type"] = inner.netType.name
            else:
                detail["net_type"] = "var"
        else:
            return {}                       # no header with a type to read
        dtype = getattr(header, "dataType", None)
        text = _type_text(dtype, getattr(declarator, "dimensions", None)) if dtype is not None else ""
        inner = getattr(sym, "internalSymbol", None)
        t = inner.type if inner is not None else sym.type
        detail["type"] = self.type_ref(_implicit(text), t, None)
        init = getattr(declarator, "initializer", None)
        if init is not None:
            detail["default"] = {"text": _tokens_text(init.expr)}
        return detail

    def _internal(self, inner: Any) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        if inner.kind == SymbolKind.Net:
            detail["net_type"] = inner.netType.name
        else:
            detail["net_type"] = "var"
        text = _declared_text(inner, fallback=False)
        detail["type"] = self.type_ref(_implicit(text), inner.type, None)
        return detail

    def net_detail(self, sym: Any) -> dict[str, Any]:
        nt = sym.netType
        detail: dict[str, Any] = {}
        if str(nt.netKind) == "NetKind.UserDefined":
            detail["net_type"] = nt.name
            detail["nettype"] = {"name": nt.name}
        else:
            detail["net_type"] = nt.name
        declarator = sym.syntax
        decl = getattr(declarator, "parent", None)
        if type(decl).__name__ == "NetDeclarationSyntax":
            if str(nt.netKind) != "NetKind.Interconnect" or _tokens_text(decl.type):
                text = _type_text(decl.type, getattr(declarator, "dimensions", None))
                detail["type"] = self.type_ref(_implicit(text), sym.type, None)
            if decl.strength is not None:
                detail["strength"] = _tokens_text(decl.strength)
            if decl.delay is not None:
                detail["delay"] = {"text": _tokens_text(decl.delay)}
            if decl.expansionHint is not None and decl.expansionHint.valueText:
                detail["split"] = decl.expansionHint.valueText
            init = getattr(declarator, "initializer", None)
            if init is not None:
                detail["init"] = {"text": _tokens_text(init.expr)}
        elif type(decl).__name__ in ("UserDefinedNetDeclarationSyntax", "DataDeclarationSyntax"):
            # ``vi_net node;``: written like a variable of the nettype.
            init = getattr(declarator, "initializer", None)
            if init is not None:
                detail["init"] = {"text": _tokens_text(init.expr)}
            if getattr(decl, "delay", None) is not None:
                detail["delay"] = {"text": _tokens_text(decl.delay)}
            written = getattr(decl, "type", None) or getattr(decl, "netType", None)
            text = _type_text(written, getattr(declarator, "dimensions", None)) if written is not None else nt.name
            detail["type"] = self.type_ref(text, sym.type, None)
        else:
            detail["type"] = self.type_ref(_join_dims(*_split_unpacked(_type_str(sym.type) or "logic")),
                                           sym.type, None)
        return detail

    def nettype_detail(self, sym: Any) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        ts = getattr(sym.declaredType, "typeSyntax", None)
        if ts is not None:
            detail["type"] = self.type_ref(_tokens_text(ts), sym.declaredType.type, None)
        res = getattr(sym, "resolutionFunction", None)
        if res is not None:
            syntax = getattr(sym, "syntax", None)
            written = getattr(getattr(syntax, "withFunction", None), "resolver", None)
            detail["resolve"] = {"name": _tokens_text(written) if written is not None else res.name}
        return detail

    def subroutine_detail(self, sym: Any) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        is_task = str(getattr(sym, "subroutineKind", "")) == "SubroutineKind.Task"
        if not is_task:
            if sym.name == "new":
                detail["constructor"] = True
            else:
                ret = _written_return_type(sym) or _type_str(getattr(sym, "returnType", None)) or "void"
                detail["return"] = self.type_ref(ret, sym.returnType, None)
        args = []
        for arg in getattr(sym, "arguments", []) or []:
            a: dict[str, Any] = {"name": arg.name}
            direction = _ARG_DIRS.get(str(getattr(arg, "direction", "")))
            if direction:
                a["dir"] = direction
            text = _declared_text(arg)
            if text:
                a["type"] = self.type_ref(text, arg.type, None)
            default = _argument_default_text(arg)
            if default:
                a["default"] = {"text": default}
            args.append(a)
        if args:
            detail["args"] = args
        if sym.kind == SymbolKind.MethodPrototype:
            detail["prototype_only"] = True
        syntax = getattr(sym, "syntax", None)
        if type(syntax).__name__ == "DPIImportSyntax":
            dpi: dict[str, Any] = {"dir": "import", **_dpi_spec(syntax)}
            dpi.setdefault("c_name", sym.name)
            prop = syntax.property.valueText
            if prop in ("pure", "context"):
                dpi[prop] = True
            detail["dpi"] = dpi
        elif syntax is not None and syntax.parent is not None:
            dpi = self._dpi_exports(syntax.parent).get(sym.name)
            if dpi is not None:
                detail["dpi"] = {**dpi, "c_name": dpi.get("c_name", sym.name)}
        return detail


# -- helpers -------------------------------------------------------------------


def _dpi_spec(syntax: Any) -> dict[str, Any]:
    """``spec`` and an explicit ``c_name`` of a DPI import or export."""
    out: dict[str, Any] = {}
    spec = syntax.specString.valueText
    if spec in ("DPI-C", "DPI"):
        out["spec"] = spec
    c_name = syntax.c_identifier.valueText
    if c_name:
        out["c_name"] = c_name
    return out


def _signature(kind: str, sym: Any, detail: dict[str, Any]) -> str:
    if kind == "net":
        declarator = getattr(sym, "syntax", None)
        decl = getattr(declarator, "parent", None)
        dn = type(decl).__name__
        if dn == "NetDeclarationSyntax":
            head = [decl.netType.valueText, _type_text(decl.type, None)]
        elif dn == "UserDefinedNetDeclarationSyntax":
            head = [_tokens_text(decl.netType)]
        elif dn == "DataDeclarationSyntax":
            head = [_tokens_text(decl.type)]
        else:
            head = [detail.get("net_type", "")]
        dims = _dims_text(sym) if type(declarator).__name__ == "DeclaratorSyntax" else ""
        return " ".join(p for p in head + [sym.name + (f" {dims}" if dims else "")] if p)
    if kind == "variable":
        t = detail.get("type", {}).get("text", "")
        return f"{t} {sym.name}".strip()
    if kind == "parameter":
        keyword = getattr(getattr(getattr(sym, "syntax", None), "parent", None), "keyword", None)
        word = keyword.valueText if keyword is not None and keyword.valueText else \
            ("localparam" if detail.get("local") else "parameter")
        if detail.get("type_param"):
            sig = f"{word} type {sym.name}"
            if "default_type" in detail:
                sig += f" = {detail['default_type']['text']}"
            return sig
        sig = " ".join(p for p in (word, detail.get("type", {}).get("text", ""), sym.name) if p)
        if "default" in detail:
            sig += f" = {detail['default']['text']}"
        return sig
    if kind == "nettype":
        sig = f"nettype {detail.get('type', {}).get('text', '')} {sym.name}"
        if "resolve" in detail:
            sig += f" with {detail['resolve']['name']}"
        return sig
    return ""


def _typedef_signature(sym: Any) -> str:
    from .builder import _typedef_signature as sig

    return sig(sym)


def _form(t: Any) -> str | None:
    if t is None:
        return None
    try:
        k = t.kind
        if k == SymbolKind.TypeAlias:
            syntax = getattr(t, "syntax", None)
            return "type_param" if type(syntax).__name__ == "TypeAssignmentSyntax" else "typedef"
        if k in _UNPACKED:
            return _form(t.arrayElementType)
        if k in _FORMS:
            return _FORMS[k]
        canon = t.canonicalType
        if canon.kind in _UNPACKED:
            return _form(canon.arrayElementType)
        return _FORMS.get(canon.kind, "unknown")
    except Exception:
        return None


def _type_str(t: Any) -> str:
    """slang's text for *t*, or "" when it cannot print it or prints an
    internal name (an anonymous struct's ``p::s$1``)."""
    if t is None:
        return ""
    try:
        text = str(t)
    except Exception:
        return ""
    return "" if "$" in text.replace("$[", "") or "{" in text else text


def _type_text(type_syntax: Any, dims: Any) -> str:
    """A type as written, with the declarator's unpacked dimensions after a
    space (the ``TypeRef`` convention): ``bit [7:0] [4]``."""
    text = re.sub(r"(?<=[\w$])\s*\[", " [", _tokens_text(type_syntax)) if type_syntax is not None else ""
    d = _tokens_text(dims) if dims is not None and len(dims) else ""
    return _join_dims(text, d)


def _dims_text(sym: Any) -> str:
    dims = getattr(getattr(sym, "syntax", None), "dimensions", None)
    return _tokens_text(dims) if dims is not None and len(dims) else ""


def _declared_text(sym: Any, fallback: bool = True) -> str:
    """The declared type of a value symbol as written, or slang's text for it
    when nothing is written (and *fallback*)."""
    ts = getattr(getattr(sym, "declaredType", None), "typeSyntax", None)
    syntax = getattr(sym, "syntax", None)
    dims = getattr(syntax, "dimensions", None) if type(syntax).__name__ == "DeclaratorSyntax" else None
    text = _type_text(ts, dims) if ts is not None else ""
    if text and not text.startswith("["):
        return text
    if not fallback:
        return text
    return _join_dims(*_split_unpacked(_type_str(getattr(sym, "type", None)) or "")) or text


def _join_dims(text: str, dims: str) -> str:
    return f"{text} {dims}".strip() if dims else text


def _implicit(text: str) -> str:
    """The implicit data type of a net is ``logic`` (LRM 6.7.1)."""
    if not text:
        return "logic"
    if text.startswith(("[", "signed", "unsigned")):
        return "logic " + text
    return text


def _anonymous_type_text(syntax: Any, dims: str) -> str:
    """``enum logic [1:0] { ... }`` for a type declared inline."""
    head = _tokens_text(syntax)
    start = head.find("{")
    if start >= 0:
        head = head[:start].rstrip() + " { ... }"
    return _join_dims(head, dims)


def _value(sym: Any) -> str | None:
    if sym is None:
        return None
    try:
        v = sym.value
    except Exception:
        return None
    if v is None:
        return None
    text = str(v)
    return None if not text or text == "<unset>" else text


def _argument_default_text(arg: Any) -> str:
    from .builder import _argument_default

    return _argument_default(arg)


def _syntax_list(seplist: Any) -> list[Any]:
    from .builder import _syntax_elements

    return _syntax_elements(seplist)


def _is_covergroup(sym: Any) -> bool:
    from .builder import _is_covergroup as check

    return check(sym)


def _decl_offset(sym: Any) -> int | None:
    token = _decl_token(sym)
    return token.location.offset if token is not None else None


def _parent(qname: str) -> str:
    return qname.rsplit("::", 1)[0]


def _default_clocking(body: Any) -> str | None:
    """The name of a definition's default clocking block: ``default clocking
    cb @(...)`` or, apart from the block, ``default clocking cb;``."""
    syntax = getattr(getattr(body, "definition", None), "syntax", None)
    for member in getattr(syntax, "members", None) or ():
        mn = type(member).__name__
        if mn == "DefaultClockingReferenceSyntax":
            return member.name.valueText
        if mn == "ClockingDeclarationSyntax" and member.globalOrDefault is not None \
                and member.globalOrDefault.valueText == "default":
            return member.blockName.valueText
    return None


def _enclosing(node: Any, type_name: str) -> Any | None:
    """The nearest ancestor of *node* (following ``.parent``) of *type_name*."""
    n = node
    while n is not None and type(n).__name__ != type_name:
        n = getattr(n, "parent", None)
    return n


_DEFINITION_DECL_SYNTAX = ("ModuleDeclarationSyntax", "InterfaceDeclarationSyntax", "ProgramDeclarationSyntax")


def _enclosing_definition_name(node: Any) -> str | None:
    """The simple name of the nearest enclosing module/interface/program
    declaration, following ``.parent`` (not qualified: nesting inside a
    generate block is not resolved here)."""
    n = getattr(node, "parent", None)
    while n is not None:
        if type(n).__name__ in _DEFINITION_DECL_SYNTAX:
            name = getattr(getattr(n, "header", None), "name", None)
            if name is not None and getattr(name, "valueText", None):
                return name.valueText
        n = getattr(n, "parent", None)
    return None


def _generate_arm_signature(construct: str, detail: dict[str, Any]) -> str:
    if construct == "if":
        cond = detail.get("cond")
        return f"if ({cond['text']})" if cond else "else"
    items = detail.get("case_items") or []
    head = ", ".join(i["text"] for i in items) if items else "default"
    return f"{head}:"


_KEYWORD_NAMES = {"posedge", "negedge", "edge", "iff", "or"}


def _local_names(scope: Any) -> set[str]:
    """The names declared in *scope* -- a subroutine or statement block --
    and in the unnamed blocks inside it: arguments and locals."""
    names: set[str] = set()
    for m in _iter_scope(scope):
        if m.kind == SymbolKind.StatementBlock and not m.name:
            names |= _local_names(m)
        elif m.name:
            names.add(m.name)
    return names


def _immediate_assertion_syntax(nodes: Any) -> Iterator[Any]:
    """``ImmediateAssertionStatementSyntax`` nodes under *nodes* (a list of
    statements/declarations), not descending into a named ``begin``/``fork``
    block or into an assertion's own action block."""
    for n in nodes or ():
        tn = type(n).__name__
        if tn == "ImmediateAssertionStatementSyntax":
            yield n
            continue
        if tn == "BlockStatementSyntax" and (n.blockName is not None or n.label is not None):
            continue
        if not hasattr(n, "kind") or hasattr(n, "valueText"):
            continue    # a token
        yield from _immediate_assertion_syntax(list(n))


def _expr(node: Any, prefix: str = "", scope: str | None = None, names: set[str] | None = None) -> dict[str, Any]:
    """An ``Expr``: *node*'s text, after *prefix* (``@``), and the names in
    it as spans.  A hierarchical name's span is its first segment.  A name in
    *names* gets the explicit target ``scope::name``."""
    text = prefix + _tokens_text(node)
    found: list[str] = []

    def collect(n: Any) -> None:
        tn = type(n).__name__
        pn = type(getattr(n, "parent", None)).__name__
        if pn == "ScopedNameSyntax":
            return
        if tn == "ScopedNameSyntax":
            written = re.sub(r"\s+", "", _tokens_text(n))
            found.append(written.split(".")[0])
        elif tn in ("IdentifierNameSyntax", "IdentifierSelectNameSyntax"):
            found.append(n.identifier.valueText)

    node.visit(collect)
    refs: list[dict[str, Any]] = []
    at = len(prefix)
    for name in found:
        if not name or name in _KEYWORD_NAMES:
            continue
        pattern = r"(?<![\w$.])" + r"\s*::\s*".join(map(re.escape, name.split("::"))) + r"(?![\w$])"
        m = re.compile(pattern).search(text, at)
        if m is None:
            continue
        ref: dict[str, Any] = {"at": [m.start(), m.end()], "name": name}
        if names is not None and scope is not None and name in names:
            ref["target"] = _join(scope, name)
        refs.append(ref)
        at = m.end()
    out: dict[str, Any] = {"text": text}
    if refs:
        out["refs"] = refs
    return out


def _inline_docs(decls: list[Decl], heads: list[int], trailing: list[list[str]], close: Any) -> None:
    """A comment after a member, before the next one, documents the member;
    after the last one it is leading trivia of the closing brace.

    ``heads[n]`` is the index in *decls* of the first object the *n*-th
    declaration made (``RED[3]`` and ``int x, y;`` make several), and
    ``trailing[n]`` the comments on the line before that declaration.
    """
    for n, i in enumerate(heads):
        if decls[i].is_documented:
            continue
        if n + 1 < len(trailing):
            nxt = trailing[n + 1]
        else:
            nxt = split_leading_trivia(close)[0] if close is not None else None
        if nxt:
            decls[i].raw_doc = clean_comment_block(nxt)
