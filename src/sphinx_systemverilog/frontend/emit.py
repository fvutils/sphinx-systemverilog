"""Today's object model as svdb records (plan D2-IMPL-1, D2-IMPL-2).

:func:`emit` walks the :class:`~..model.objects.SvObject` trees that
:class:`~..model.builder.ModelBuilder` returns and yields one record per
object, plus the header, the file records and the parser diagnostics.  It is
the inverse of :func:`to_sv_object`, and the pair round-trips: a facade over
the database hands Sphinx the same objects the builder made.

Where the model and the schema differ, the mapping is:

* kind ``property`` is ``variable``;
* the class qualifiers ``interface`` and ``parameterized``, and a port's
  direction, are ``detail`` fields (``interface_class``, ``parameterized``,
  ``dir``) rather than qualifiers;
* ``extends`` is a ``TypeRef`` whose leading name is a ``Span``;
* ``from_macros`` (innermost first) is ``via`` (outermost first);
* ``doc_style`` is the same for every object of one build, so it is written
  once, as ``header.inputs.doc_style``;
* a ``group`` without a doc comment is a ``doc`` with empty text;
* the model's ports are all ANSI header ports and its parameters all
  ``#(...)`` parameters, so they get ``detail.ansi`` and ``detail.port_list``
  (which is how :func:`~..model.db.rendered` tells them from the body
  declarations only the database has).

Identity (§3.3): a macro defined more than once is one object, the **last**
definition, with the earlier ones in ``detail.redefined_at``.  Any other
object whose key repeats is dropped with a ``DuplicateObject`` diagnostic, and
the first one is kept, as ``SvIndex`` always did.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Iterable, Iterator

from ..model.declarations import Decl, Extras
from ..model.objects import SourceRef, SvObject
from ..svdb import SCHEMA_VERSION

#: Model kind -> schema kind, where they differ.
KIND_TO_SCHEMA = {"property": "variable"}
KIND_FROM_SCHEMA = {v: k for k, v in KIND_TO_SCHEMA.items()}

#: Name space of each root kind (§3.1).
ROOT_NS = {"package": "package", "module": "design", "interface": "design", "program": "design",
           "macro": "macro"}

_DIRS = ("input", "output", "inout", "ref")
_HEAD = re.compile(r"[A-Za-z_$\\][\w$]*(?:\s*::\s*[A-Za-z_$\\][\w$]*)*")


def header(*, doc_style: str, inputs: dict[str, Any] | None = None, origin: str | None = None,
           created: bool = True, extra_sections: dict[str, str] | None = None,
           links: list[dict] | None = None) -> dict:
    """The header record of a front-end database; *links* are the databases
    the compile was linked against (linking plan §1.5)."""
    from ..__version__ import __version__

    try:
        import pyslang

        frontend = f"pyslang {getattr(pyslang, '__version__', '')}".strip()
    except ImportError:  # pragma: no cover - the front end needs pyslang anyway
        frontend = "pyslang"
    rec: dict[str, Any] = {"r": "header", "format": "svdb", "schema": SCHEMA_VERSION,
                           "producer": {"name": "sphinx-systemverilog", "version": __version__,
                                        "frontend": frontend}}
    if created:
        rec["created"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec["role"] = "local"
    if origin:
        rec["origin"] = origin
    rec["inputs"] = {**{k: v for k, v in (inputs or {}).items() if v not in (None, "", [], {})},
                     "doc_style": doc_style}
    rec["sections"] = {"files": "complete", "objects": "complete", "docs": "complete", "bodies": "complete",
                       "diagnostics": "complete", **(extra_sections or {})}
    if links:
        rec["links"] = links
    return rec


def emit(roots: Iterable[SvObject], *, doc_style: str, diagnostics: Iterable[str] = (),
         suppressed: int = 0, inputs: dict[str, Any] | None = None, origin: str | None = None,
         created: bool = True, extras: Extras | None = None,
         extra_sections: dict[str, str] | None = None, uvm: Any = None,
         origin_of: Any = None, links: list[dict] | None = None) -> Iterator[dict]:
    """Records for *roots*: header, files, `` `include `` edges, units, objects in tree order,
    macro bodies, imports, ``uvm.*`` (from *uvm*, a :class:`~.uvm.UvmViews`), diagnostics.

    *extras* (:func:`~..model.declarations.extract`) adds the declarations the
    object model does not carry, in source order among their siblings, and
    fills in ``detail`` of the objects it does.

    *origin_of* maps a source file to its ``sv_external_sources`` origin label
    (or ``None``); objects declared in such a file are flagged ``external``.
    """
    extras = extras or Extras()
    files: dict[str, str] = {}
    objects: list[dict] = []
    bodies: list[dict] = []
    problems: list[dict] = []

    def fid(path: str) -> str:
        if path not in files:
            files[path] = f"f{len(files) + 1}"
        return files[path]

    def loc(ref: SourceRef | None) -> dict | None:
        if ref is None or not ref.is_valid:
            return None
        return {"file": fid(ref.file), "line": ref.line, "col": max(ref.column, 0)}

    def where(ref: SourceRef | None) -> str:
        return f"{ref.file}:{ref.line}" if ref is not None and ref.is_valid else "<unknown>"

    def visit(siblings: list, ns: str, parent: str | None) -> None:
        kept = _dedupe(siblings, parent is None, problems, where, loc)
        for pos, (obj, extra) in enumerate(kept):
            rec = _object(obj, ns if parent is not None else ROOT_NS.get(obj.kind, "design"), parent, pos, loc)
            if rec["kind"] == "macro" and obj.location is not None:
                macro = extras.macros.get((obj.location.file, obj.location.line, obj.location.column), {})
                if "params" in macro:
                    rec.setdefault("detail", {})["params"] = macro["params"]
                if "body" in macro:
                    bodies.append({"r": "body", "of": f"macro:{rec['qname']}", "text": macro["body"]})
            if obj.location is not None:
                attrs = extras.attrs.get((obj.location.file, obj.location.line, obj.location.column))
                if attrs:
                    rec["attrs"] = attrs
                if (obj.location.file, obj.location.line, obj.location.column) in extras.protected_decls:
                    rec["flags"] = [*rec.get("flags", []), "protected"]
                origin = origin_of(obj.location.file) if origin_of is not None else None
                if origin is not None:
                    rec["flags"] = ["external", *rec.get("flags", [])]
                    rec["origin"] = origin
            if extra:
                rec.setdefault("detail", {})["redefined_at"] = extra
            if not isinstance(obj, Decl):
                patch = extras.details.get(rec["qname"])
                if patch:
                    rec["detail"] = {**patch, **rec.get("detail", {})}
            objects.append(rec)
            kids = list(obj.children)
            if not isinstance(obj, Decl):
                kids = _merge(kids, extras.children.get(rec["qname"], []))
            visit(kids, rec["ns"], rec["qname"])

    # Root-level declarations the object model does not carry (``checker``).
    visit(_merge(list(roots), extras.children.get("", [])), "", None)
    imports = []
    for rec in extras.imports:
        rec = dict(rec)
        at = loc(rec.pop("loc", None))
        if at:
            rec["loc"] = at
        imports.append(rec)
    includes = [{"r": "include", "from": fid(a), "to": fid(b), "line": line}
                for a, b, line in extras.includes]
    units = [{**rec, "files": [fid(f) for f in rec["files"]]} for rec in extras.units]
    uvm_records = []
    if uvm is not None:
        from . import uvm as uvm_mod

        uvm_records = uvm_mod.records(uvm, loc)
        extra_sections = {**(extra_sections or {}), **uvm.sections()}
    yield header(doc_style=doc_style, inputs=inputs, origin=origin, created=created,
                 extra_sections=extra_sections, links=links)
    for path, i in files.items():
        rec = _file(i, path)
        if extras.protected.get(path):
            rec["protected"] = extras.protected[path]
        yield rec
    yield from includes
    yield from units
    yield from objects
    yield from bodies
    yield from imports
    yield from uvm_records
    for message in diagnostics:
        if message and message.strip():
            yield {"r": "diag", "severity": "error", "code": "Parser", "message": message}
    yield from problems
    if suppressed:
        yield {"r": "diag", "severity": "note", "code": "Suppressed",
               "message": f"{suppressed} non-error parser diagnostic(s) suppressed"}


def _dedupe(siblings, roots: bool, problems, where, loc) -> list[tuple[SvObject, list]]:
    """Apply the §3.3 identity rules to one list of siblings."""
    macros: dict[str, list[SvObject]] = {}
    for obj in siblings:
        if obj.kind == "macro":
            macros.setdefault(obj.qualified_name or obj.name, []).append(obj)
    out: list[tuple[SvObject, list]] = []
    seen: dict[tuple[str, str], SvObject] = {}
    for obj in siblings:
        qname = obj.qualified_name or obj.name
        if obj.kind == "macro":
            defs = macros[qname]
            if obj is defs[-1]:
                out.append((obj, [l for l in (loc(d.location) for d in defs[:-1]) if l]))
            continue
        # Siblings share a name space, except roots (§3.1).
        key = (ROOT_NS.get(obj.kind, "design") if roots else "", qname)
        first = seen.get(key)
        if first is not None:
            problems.append({"r": "diag", "severity": "warning", "code": "DuplicateObject",
                             "message": f"{qname} ({obj.kind}) at {where(obj.location)} repeats the {first.kind} "
                                        f"at {where(first.location)}; the first is kept"})
            continue
        seen[key] = obj
        out.append((obj, []))
    return out


def _merge(legacy: list, extra: list) -> list:
    """*extra* inserted among *legacy* by source position; *legacy* keeps its
    own order, which is what Sphinx renders."""
    if not extra:
        return legacy

    def where(o):
        ref = o.location
        return (ref.file, ref.line, ref.column) if ref is not None and ref.is_valid else None

    rest = sorted(extra, key=lambda o: (where(o) is None, where(o) or ("", 0, 0)))
    out: list = []
    j = 0
    for obj in legacy:
        here = where(obj)
        while j < len(rest) and here is not None and where(rest[j]) is not None \
                and where(rest[j])[0] == here[0] and where(rest[j]) < here:
            out.append(rest[j])
            j += 1
        out.append(obj)
    out.extend(rest[j:])
    return out


def _decl(obj: Decl, ns: str, parent: str | None, pos: int, loc) -> dict:
    rec: dict[str, Any] = {"r": "object", "kind": obj.kind, "ns": ns, "qname": obj.qualified_name,
                           "name": obj.name}
    if parent is not None:
        rec["parent"] = parent
    if obj.scope is not None:
        rec["scope"] = obj.scope
    rec["pos"] = pos
    here = loc(obj.location)
    if here:
        rec["loc"] = here
    if obj.from_macros:
        rec["via"] = [{"macro": m} for m in reversed(obj.from_macros)]
    if obj.signature:
        rec["sig"] = obj.signature
    if obj.qualifiers:
        rec["quals"] = list(obj.qualifiers)
    if obj.flags:
        rec["flags"] = list(obj.flags)
    if obj.raw_doc is not None or obj.group:
        doc: dict[str, Any] = {"text": obj.raw_doc or ""}
        if obj.group:
            doc["group"] = obj.group
        rec["doc"] = doc
    if obj.detail:
        rec["detail"] = obj.detail
    return rec


def _object(obj: SvObject, ns: str, parent: str | None, pos: int, loc) -> dict:
    if isinstance(obj, Decl):
        return _decl(obj, ns, parent, pos, loc)
    kind = KIND_TO_SCHEMA.get(obj.kind, obj.kind)
    qname = obj.qualified_name or obj.name
    rec: dict[str, Any] = {"r": "object", "kind": kind, "ns": ns, "qname": qname, "name": obj.name}
    if parent is not None:
        rec["parent"] = parent
    rec["pos"] = pos
    here = loc(obj.location)
    if here:
        rec["loc"] = here
    if obj.from_macros:
        rec["via"] = [{"macro": m} for m in reversed(obj.from_macros)]
    if obj.signature:
        rec["sig"] = obj.signature
    quals = list(obj.qualifiers)
    detail: dict[str, Any] = {}
    if obj.kind == "class":
        if "parameterized" in quals:
            quals.remove("parameterized")
            detail["parameterized"] = True
        if "interface" in quals:
            quals.remove("interface")
            detail["interface_class"] = True
        if "virtual" in quals:
            detail["virtual"] = True
    if obj.kind == "port":
        # The object model has only ANSI header ports, and only header parameters.
        detail["ansi"] = True
        if quals and quals[0] in _DIRS:
            detail["dir"] = quals.pop(0)
    if obj.kind == "parameter":
        detail["port_list"] = True
    if obj.extends:
        detail["extends"] = type_ref(obj.extends, getattr(obj, "extends_target", None))
    if quals:
        rec["quals"] = quals
    if obj.raw_doc is not None or obj.group:
        doc: dict[str, Any] = {"text": obj.raw_doc or ""}
        if obj.group:
            doc["group"] = obj.group
        rec["doc"] = doc
    if detail:
        rec["detail"] = detail
    return rec


def type_ref(text: str, target: str | None = None) -> dict:
    """A ``TypeRef`` for *text*, with its leading name as a ``Span`` (naming
    *target*, a qualified name, when given)."""
    ref: dict[str, Any] = {"text": text}
    m = _HEAD.match(text)
    if m:
        name = re.sub(r"\s+", "", m.group(0))
        span: dict[str, Any] = {"at": [0, m.end()], "name": name}
        if target:
            span["target"] = target
        ref["refs"] = [span]
    return ref


def _file(i: str, path: str) -> dict:
    rec: dict[str, Any] = {"r": "file", "id": i, "path": path}
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    rec["lang"] = ext if ext in ("sv", "svh", "v", "vh") else "other"
    return rec


# -- the way back ------------------------------------------------------------------


def to_sv_object(obj: Any, *, doc_style: str | None, doc: Any = None) -> SvObject:
    """An :class:`SvObject` (without children) from a :class:`svdb.Object`
    and its :class:`svdb.database.Doc`; the inverse of the mapping above."""
    detail = obj.detail or {}
    kind = KIND_FROM_SCHEMA.get(obj.kind, obj.kind)
    quals = list(obj.quals)
    if kind == "class":
        quals = (["parameterized"] if detail.get("parameterized") else []) + \
                (["interface"] if detail.get("interface_class") else []) + quals
    if kind == "port" and detail.get("dir"):
        quals.insert(0, detail["dir"])
    extends = detail.get("extends")
    raw_doc = group = None
    if doc is not None:
        group = doc.group
        raw_doc = doc.text if doc.text or group is None else None
    location = None
    if obj.loc is not None and obj.loc.path:
        location = SourceRef(obj.loc.path, obj.loc.line, obj.loc.col or 0)
    return SvObject(kind=kind, name=obj.name, qualifiers=quals, signature=obj.sig or "",
                    extends=extends["text"] if extends else None, raw_doc=raw_doc, doc_style=doc_style,
                    location=location, group=group, qualified_name=obj.qname,
                    from_macros=tuple(reversed(obj.via)))
