# sphinx-systemverilog — Design & Approach

**Status:** Draft for review
**Date:** 2026-06-28
**Author:** design spike (Claude) with M. Ballance
**Goal:** A Sphinx extension that autodocuments SystemVerilog source the way `sphinx.ext.autodoc` documents Python — pulling declarations and their doc comments directly from source via the `pyslang` parser, supporting NaturalDocs, Doxygen, and a Python-docstring-like comment style.

---

## 1. Executive summary / recommendation

Build a **custom Sphinx _domain_ (`sv`) plus a thin autodoc layer**, rather than trying to extend `sphinx.ext.autodoc` directly.

- **Domain (`sphinx.domains.Domain`)** — gives us object description directives (`sv:class`, `sv:module`, `sv:function`, …), a cross-reference role system (`:sv:class:`uvm_object``), an index, and proper search/permalink integration. This is exactly what the built-in `py`, `c`, `cpp`, and `js` domains do, and it is the supported way to teach Sphinx a new language.
- **Autodoc layer** — a small set of `auto*` directives (`autosvmodule`, `autosvclass`, `autosvpackage`, …) that run `pyslang`, extract declarations + comments, and *emit* the domain directives. This mirrors `sphinx.ext.autodoc` conceptually but does **not** subclass it.

**Why not reuse `sphinx.ext.autodoc`?** `autodoc` is deeply wired to Python's runtime object model — it `import`s the target module and introspects live Python objects (`inspect`, `__doc__`, `__mro__`, signatures). SystemVerilog has no runtime to import; everything comes from static parsing. The `Documenter` class hierarchy assumes Python semantics at almost every turn. The *valuable, reusable* parts of autodoc are the **ideas** (a registry of documenters, member discovery, `:members:`/`:undoc-members:` options, docstring → RST processing, event hooks), not the code. We reimplement those ideas against `pyslang`. The C/C++ ecosystem proved this path twice: the built-in `cpp` domain and Breathe both go their own way rather than extending `autodoc`.

The technical core is **validated** — see §4. `pyslang` exposes both a lossless syntax tree (comments preserved as trivia) and an elaborated semantic AST (resolved symbols with source locations). We can walk symbols, find their declaration syntax, and recover the attached doc comment.

---

## 2. Landscape: how this is done elsewhere

| Tool | Approach | Lesson for us |
|---|---|---|
| `sphinx.ext.autodoc` (Python) | Imports module, runtime introspection, `Documenter` registry emits `py` domain directives | Reuse the *architecture* (documenter registry, member options, autodoc-process-docstring events), not the code. |
| Built-in `c` / `cpp` domains | Hand-written parser + custom domain; **no** autodoc — you write directives manually | A domain alone is viable but tedious; we want autodoc on top. |
| **Breathe** (Doxygen → Sphinx) | Doxygen parses C/C++/etc. to XML; Breathe renders XML into a custom domain | Closest analog. Validates "external parser → custom domain." We replace Doxygen-XML with direct `pyslang`. |
| **Exhale** | Drives Doxygen + Breathe to build a full API tree page | Good model for a future "document the whole tree" front-end. |
| `SymbiFlow/sphinx-verilog-domain` / similar | lark-based generic parser, unmaintained, no SV class/package semantics, no type resolution (see `competitive-landscape.md`) | Why we build fresh on a real SV front-end (`pyslang`/slang). |
| **NaturalDocs** (what UVM ships) | Standalone generator, its own HTML. UVM `packages/uvm/docs/html` is prebuilt ND output | We must *read* ND comment syntax, but we render through Sphinx, not ND. |

**Conclusion:** the proven pattern is *external language front-end → normalized model → custom Sphinx domain*. `pyslang` is our front-end; the novelty is doing it in-process (no XML round-trip) and supporting multiple comment dialects.

---

## 3. Comment/doc styles to support

The same SV codebase in the wild uses at least three conventions. We support all three with a pluggable **doc-comment parser** selected per-project (config) or auto-detected per-comment.

### 3.1 NaturalDocs (UVM's style) — primary target
Observed directly in `packages/uvm/src`:

```systemverilog
// CLASS: uvm_object
//
// The uvm_object class is the base class for all UVM data and hierarchical
// classes. Its primary role is to define a set of methods for such common
// operations as <create>, <copy>, <compare>, <print>, and <record>.

// Function: get_name
//
// Returns the name of the object, as provided by the ~name~ argument in the
// <new> constructor or <set_name> method.

// Group: Seeding
```

Salient ND features we must handle:
- **Keyword headers**: `Class:`, `Function:`, `Task:`, `Variable:`, `Group:`, `Topic:`, `Macro:` — a line like `// CLASS: name` introduces a documented symbol. (UVM uses an extended `CLASS -- NODOCS -- name` form to *suppress* docs for the IEEE-extracted subset — we treat `NODOCS` as "skip".)
- **`<symbol>`** inline cross-references → become `:sv:obj:`symbol`` roles.
- **`~code~`** inline → inline literal/code.
- **`Group:`** headers → logical grouping of members (maps cleanly to a section / `..rubric`).
- **Definition lists, indented code blocks** (ND's layout rules).

ND comments are detached "documentation blocks" associated by the *header keyword + name*, **not** strictly by adjacency. This matters: §5 covers the association strategy.

### 3.2 Doxygen
```systemverilog
/**
 * @brief Compute the parity of the address.
 * @param addr  The address to check.
 * @return The parity bit.
 */
```
Tags: `@brief @param @return @details @note @see @file @class @group` plus `\`-prefixed variants and `///`/`//!` line forms. Maps naturally onto field lists (`:param addr:`, `:returns:`).

### 3.3 Python-docstring-like / "native" (recommended default for new code)
A simple, low-ceremony style — the immediately-preceding `//` or `/* */` block is the doc, first line is the summary, with optional reStructuredText/field-lists:
```systemverilog
// Compute the parity of the address.
//
// :param addr: the address to check
// :returns: the parity bit
function bit parity(bit[31:0] addr);
```
This is the most natural fit for Sphinx because the body is already RST. It is the recommended convention for greenfield SV docs.

### 3.4 Strategy
A `DocstringParser` interface with three implementations (`naturaldocs`, `doxygen`, `native`). Project picks a default via `conf.py` (`sv_doc_style = "naturaldocs"`); individual blocks can be auto-detected by cheap signature sniffing (`/**` → doxygen; `Class:`/`Function:`/`<…>` → naturaldocs; else native). Each parser's job: **raw comment text → (summary, body-as-RST, structured fields, xref tokens)**. Cross-reference normalization (`<x>`, `@see x`, `:sv:…:`x``) is unified downstream.

---

## 4. Technical validation of `pyslang` (done — it works)

Environment: `pyslang 11.0.0`, `sphinx 9.1.0` in `packages/python` (uv-managed).

`pyslang` exposes two complementary layers:

1. **`pyslang.syntax` — lossless concrete syntax tree (CST).** Comments are preserved as **trivia** on tokens (`TriviaKind.LineComment`, `TriviaKind.BlockComment`). `SyntaxTree.fromText/fromFile/fromFiles/fromBuffers`. This is where doc comments live.
2. **`pyslang.ast` — elaborated semantic model.** `Compilation()` + `addSyntaxTree(...)` gives resolved symbols: `getPackages()`, `getDefinitions()` (modules/interfaces/programs), and scope iteration for members. Each symbol has `.name`, `.kind`, `.location`, `.syntax` (back-pointer to its CST node), and `.isScope` for recursion.

**Validated facts (each run against `pyslang` directly during this spike):**

- **Symbol traversal**: `for member in scope:` iterates a package/class/module scope. Classes, class properties, subroutines (functions/tasks), modules, params, ports all enumerable.
- **Doc-comment recovery**: `symbol.syntax.getFirstToken().trivia` yields the leading comments — including blank-line-separated multi-line blocks — immediately above a declaration. Verified on a class (`// A simple transaction class.` / `// This models a bus transaction.`) and members.
- **Source-location resolution**: `tree.sourceManager.getFileName(sym.location)`, `.getLineNumber(...)`, `.getColumnNumber(...)` → file/line/col for `.. sourcecode`/`viewcode`-style links.
- **Compiler-synthesized members** (e.g. injected `randomize`, `pre_randomize`, `srandom` on every class) carry **out-of-range bogus locations** (`SourceLocation(268435455, 68719476735)`). **Filter rule:** keep only symbols whose location maps into a real source buffer / whose `.syntax` is non-null. Proven necessary.
- **Trailing inline comments** (`input logic clk, // the clock`) attach as the **leading trivia of the _next_ token**, not the declarator they visually annotate. **Heuristic required:** if a comment trivia starts on the same source line as the *end* of the preceding declarator, reassign it as that declarator's trailing doc. Proven behavior.
- **Diagnostics**: `tree.diagnostics()` / `comp.getAllDiagnostics()` available — we surface parse errors as Sphinx warnings (non-fatal; document what parsed).

**Worked example** (abridged from the spike):
```python
from pyslang.syntax import SyntaxTree
from pyslang.ast import Compilation
from pyslang.parsing import TriviaKind

tree = SyntaxTree.fromFile("uvm_object.svh")
sm   = tree.sourceManager
comp = Compilation(); comp.addSyntaxTree(tree)

for pkg in comp.getPackages():
    for sym in pkg:                       # scope iteration
        if sym.syntax is None:            # skip synthesized
            continue
        tok = sym.syntax.getFirstToken()
        doc = [t.getRawText() for t in tok.trivia
               if t.kind in (TriviaKind.LineComment, TriviaKind.BlockComment)]
        file = sm.getFileName(sym.location)
        line = sm.getLineNumber(sym.location)
        # -> (sym.kind, sym.name, file:line, doc[])  ==> feed DocstringParser
```

**Risks / open items on the parser side:**
- **`define` macros and `\`include`-heavy headers (`.svh`)**: UVM is built almost entirely from macros and an include chain rooted at `uvm_pkg.sv`. To elaborate semantically we must parse with the right **include dirs** and **macro defines**, and likely parse the *package roots* rather than individual `.svh` files. Provide `sv_include_dirs`, `sv_defines`, and explicit "build unit" file lists in config. Where full elaboration is impractical, we can fall back to **syntax-only** extraction (CST walk without `Compilation`) which still yields declarations + comments, just without cross-module type resolution.
- **Macro-defined declarations** (e.g. UVM's `\`uvm_object_utils`): these expand to members that have no nice source comment. Acceptable to document the macro invocation as-is or skip; revisit later.

---

## 5. Comment-to-symbol association

Three association modes, in priority order:

1. **Adjacency (native / doxygen default)** — the doc block is the leading-trivia comment immediately preceding the declaration (the §4 mechanism). Trailing same-line comments handled by the reassignment heuristic.
2. **Named blocks (NaturalDocs)** — ND blocks (`// Function: get_name`) are matched to symbols **by keyword+name** within the enclosing scope, because ND intentionally separates the doc block from the prototype (UVM puts `extern function ...` lines elsewhere). Algorithm: collect all ND blocks per file (from raw trivia scan), index by `(kind, name)`, then join to symbols during traversal. Adjacency is the tie-breaker when names collide (overloads, same name in nested scopes).
3. **Explicit (`:no-index:` / in-directive content)** — author writes docs in the `.rst` directive body; source comment is ignored/augmented.

`Group:`/`@group` headers create ordered member groupings rendered as labeled subsections.

---

## 6. Architecture

```
                       ┌─────────────────────────────────────────┐
   .sv / .svh ───────► │  sv_model  (pyslang front-end)           │
                       │  - parse (syntax + optional elaboration) │
                       │  - traverse symbols, filter synthesized  │
                       │  - extract raw doc trivia + locations    │
                       │  - emit a normalized SvObject tree       │
                       └──────────────────┬──────────────────────┘
                                          │  SvObject (kind, name, sig,
                                          │  raw_doc, style?, loc, children)
                       ┌──────────────────▼──────────────────────┐
                       │  docparse  (DocstringParser registry)    │
                       │  naturaldocs | doxygen | native          │
                       │  raw_doc -> (summary, rst_body, fields,   │
                       │              xrefs)                       │
                       └──────────────────┬──────────────────────┘
                                          │
   ┌──────────────────────────────────────▼────────────────────────────┐
   │  sphinx_systemverilog  (the extension)                             │
   │                                                                    │
   │  domain.py    SystemVerilogDomain(Domain)                          │
   │               - directives: sv:package sv:module sv:interface       │
   │                 sv:class sv:function sv:task sv:property sv:port     │
   │                 sv:parameter sv:typedef sv:covergroup sv:constraint  │
   │               - roles: sv:obj sv:class sv:mod ... (xref)            │
   │               - index + object inventory (intersphinx-ready)        │
   │                                                                    │
   │  autodoc.py   Documenter registry (auto* directives)               │
   │               - autosvpackage / autosvmodule / autosvclass / ...    │
   │               - :members: :undoc-members: :inherited-members:       │
   │                 :recursive: :include: :exclude:                      │
   │               - runs sv_model + docparse, emits domain directives   │
   │                                                                    │
   │  events       sv-autodoc-process-doc (mirror autodoc-process-       │
   │               docstring), sv-autodoc-skip-member                    │
   └────────────────────────────────────────────────────────────────────┘
```

### 6.1 Project-wide source index ("parse wide, reference scope")

Per the resolved design direction (§14), the extension follows the Python-autodoc mental model: **parse a broad source set once into a project-wide index, then let each directive reference a documentation _scope_ into that index.** This is what makes whole-tree generation natural rather than bolted-on.

- **One index per build.** On `builder-inited`, `model/builder.py` parses everything in `sv_source_dirs` / `sv_build_units` into a single elaborated `SvIndex` — a name-resolved map of every package/module/interface/class and its members (qualified names → `SvObject`). Compilation is cached and shared across all directives, so a 1000-file design is parsed once, not per page. This is the analog of Python's importable module namespace.
- **Directives reference _into_ the scope.** `.. autosvclass:: uvm_pkg::uvm_object` resolves a qualified name against the index; xref roles (`:sv:class:`uvm_object``) resolve the same way. No directive re-parses source.
- **Whole-tree front-end.** A single `.. autosvsummary::` / "document everything under this scope" directive walks a subtree of the index and emits a structured API tree (the Exhale analog), because the full index is already in memory. Scope can be narrowed (`:packages: uvm_pkg`, a directory, a name glob) so a doc set references only the slice it cares about — wide parse, scoped reference.
- **Inventory.** The same index backs the objects inventory for intersphinx/search (§10), so the parse-once index is the single source of truth for resolution, rendering, and cross-references.

### Module layout (initial)
```
src/sphinx_systemverilog/
  __init__.py            # setup(app): register domain, directives, config, events
  config.py              # sv_source_dirs, sv_include_dirs, sv_defines,
                         #   sv_doc_style, sv_build_units, sv_default_options
  model/
    builder.py           # pyslang -> SvObject tree (the §4 engine)
    index.py             # SvIndex: project-wide parse-once name->SvObject map (§6.1)
    objects.py           # SvObject dataclasses (Package, Module, Class, Routine...)
    locations.py         # SourceLocation -> file:line, viewcode support
  docparse/
    base.py              # DocstringParser ABC, ParsedDoc dataclass
    naturaldocs.py
    doxygen.py
    native.py
    xref.py              # unify <x>/@see/:sv:..: -> pending_xref
  domain.py              # SystemVerilogDomain, object directives, roles, index
  autodoc/
    documenters.py       # Documenter base + per-kind subclasses
    directives.py        # auto* directive classes (incl. autosvsummary whole-tree)
  viewcode.py            # optional: link to highlighted SV source
tests/
  sv/                    # fixture .sv files (incl. a trimmed UVM subset)
  test_model.py test_docparse_*.py test_domain.py test_autodoc.py
```

---

## 7. Directives & roles (user-facing surface)

**Manual domain directives** (always available, autodoc emits these):
```rst
.. sv:class:: uvm_object
   :extends: uvm_void
   :virtual:

   Base class for all UVM data and hierarchical classes.

   .. sv:function:: string get_name()

      Returns the instance name of the object.
```

**Autodoc directives** (the headline feature):
```rst
.. autosvpackage:: uvm_pkg
   :members:
   :recursive:

.. autosvclass:: uvm_object
   :members:
   :inherited-members:
   :doc-style: naturaldocs

.. autosvmodule:: counter
   :members:                 # params + ports
```

**Options** (autodoc parity): `:members:` `:undoc-members:` `:inherited-members:` `:exclude-members:` `:recursive:` `:doc-style:` `:no-index:` `:member-order: (source|alpha|groups)`.

**Cross-reference roles**: `:sv:class:` `:sv:mod:` `:sv:func:` `:sv:task:` `:sv:port:` `:sv:param:` `:sv:obj:` (generic). Inventory is exported so **intersphinx** works across projects.

**Config (`conf.py`)**:
```python
extensions = ["sphinx_systemverilog"]
sv_source_dirs   = ["../packages/uvm/src"]
sv_include_dirs  = ["../packages/uvm/src"]
sv_defines       = {"UVM_NO_DEPRECATED": "1"}
sv_build_units   = ["uvm_pkg.sv"]          # roots to elaborate
sv_doc_style     = "naturaldocs"           # default dialect
sv_default_options = {"members": True, "member-order": "source"}
```

---

## 8. Object model (`SvObject`)

A normalized, parser-agnostic node consumed by both manual review and autodoc:
```python
@dataclass
class SvObject:
    kind: str            # 'package'|'module'|'interface'|'program'|'class'
                         #  |'function'|'task'|'property'|'port'|'parameter'
                         #  |'typedef'|'covergroup'|'constraint'|'modport'|...
    name: str
    qualifiers: list[str]      # virtual, static, local, protected, rand, pure...
    signature: str             # rendered prototype (return type, args, port dir)
    extends: str | None        # class inheritance / interface
    raw_doc: str | None        # untouched comment text
    doc_style: str | None      # override / detected
    location: SourceRef        # file, line, col
    children: list[SvObject]
    group: str | None          # NaturalDocs/Doxygen group membership
```
This decoupling means the `pyslang` specifics live only in `model/builder.py`; everything downstream is stable if `pyslang`'s API shifts.

---

## 9. SV-specific concerns (beyond Python autodoc)

- **Modules/interfaces**: document **parameters** and **ports** (with direction `input/output/inout`, type, default) — no Python analog; render as param/port field lists.
- **Inheritance**: `extends`/`implements`; `:inherited-members:` must climb the resolved class hierarchy (available via the AST type symbols).
- **Overloads / parameterized classes** (`uvm_object_registry#(T,Tname)`): qualify names with parameter lists; xref disambiguation.
- **`virtual`/`pure virtual`/`extern`**: surface as qualifiers; `extern` prototypes vs out-of-block bodies — associate the doc from whichever carries it.
- **Macros (`define`)**: document the macro itself (`sv:macro`); macro-generated members are best-effort.
- **Coverage/constraints/clocking**: first-class SV constructs worth a directive each, low priority.
- **Multi-file packages**: a package spans many `.svh` includes — model must aggregate members across files under one package object.

---

## 10. Rendering & integration

- Each `SvObject` → a domain directive node; signature via the domain's `handle_signature` (proper desc nodes, permalinks, index entries).
- `ParsedDoc.rst_body` is parsed as **reStructuredText** through Sphinx's nested-parse, so authors can use full RST/MyST inside comments (native style), while ND/Doxygen are normalized into RST first.
- **viewcode-style** "[source]" links using the captured `file:line` (optional `sphinx_systemverilog.viewcode`).
- Emit an **objects inventory** so `intersphinx` and search index work; cross-project SV references become possible.
- `sv-autodoc-process-doc` event lets users post-process extracted docs (mirrors `autodoc-process-docstring`).

---

## 11. Phased delivery plan

**Phase 0 — spike (DONE in this doc).** Proven: parse, traverse, extract comments, resolve locations, filter synthesized members, identify trailing-comment + macro/include risks.

**Phase 1 — MVP, syntax-only, `native` dialect.** *(dialect priority confirmed: native first)*
- `model/builder.py` via CST walk (no full elaboration needed) → `SvObject` for package/class/function/task/property.
- `model/index.py`: project-wide `SvIndex` built once on `builder-inited`, even if scope is small (§6.1) — establishes the parse-wide/reference-scope contract from day one.
- `native` DocstringParser only.
- `sv` domain with `sv:class`/`sv:function`/`sv:task`/`sv:property` + xref roles + index.
- `autosvclass`, `autosvpackage` with `:members:` (resolve names against `SvIndex`).
- Golden tests on small fixtures. **Deliverable: document a hand-written sample package end-to-end.**

**Phase 2 — NaturalDocs + UVM.**
- `naturaldocs` parser (headers, `<xref>`, `~code~`, `Group:`).
- Named-block association (§5.2). Include-dir/define config; elaborate `uvm_pkg.sv` into the `SvIndex`.
- Modules/interfaces (params/ports); class inheritance diagrams via Graphviz (off the resolved `baseClass` edges in the `SvIndex`).
- **Acceptance test (confirmed): document `packages/uvm` end-to-end** — build a published doc set from the UVM source, not just a subset, exercising the project-wide index at real scale.

**Phase 3 — Doxygen + whole-tree front-end + polish.**
- `doxygen` parser, auto-detect, `:inherited-members:`, `:recursive:`, viewcode, intersphinx inventory, member ordering/groups.
- **`autosvsummary` whole-tree generation** (Exhale analog, §6.1) — promoted from "later" to a core deliverable per the resolved design direction: walk an index subtree and emit a structured API tree, with scope narrowing.

**Phase 4 — scale/UX.**
- Macro handling, parameterized-class xref disambiguation, covergroups/constraints, structural instantiation diagrams, performance (cache/incremental compilations).

---

## 12. Testing

- **Unit**: each DocstringParser (raw → ParsedDoc) with table-driven cases per dialect.
- **Model**: fixture `.sv`/`.svh` → expected `SvObject` tree (incl. synthesized-member filtering, trailing-comment heuristic).
- **Integration**: `sphinx-build` on a `tests/roots/` mini-project; assert generated HTML/doctree via `sphinx.testing` (`@pytest.mark.sphinx`).
- **Corpus smoke test**: run the model over all of `packages/uvm/src`; assert no crashes and a member-count floor. Surfaces parser/elaboration gaps early.

---

## 13. Dependencies / packaging

- Runtime deps: `sphinx`, `pyslang` (already in `ivpm.yaml` / `packages/python`). No new deps for Phase 1.
- Add `docutils` pin compatible with Sphinx 9.x if needed (transitively present).
- If we add dev tooling (e.g. `myst-parser` for docs-of-the-tool, or `beautifulsoup4` for HTML test assertions), install via `uv` **and** record in `ivpm.yaml` `dep-sets`.
- Package as `sphinx-systemverilog` (PyPI), entry via `setup(app)` in `src/sphinx_systemverilog/__init__.py`; `pyproject.toml` with `src/` layout.

---

## 14. Key decisions for review

1. **Custom domain + bespoke autodoc layer** (not extending `sphinx.ext.autodoc`). — recommended, §1.
2. **Three pluggable doc dialects**, `native` as the recommended default for new code; `naturaldocs` is the priority for UVM. — §3.
3. **Two-layer pyslang use**: prefer full `Compilation` elaboration; **fall back to syntax-only** when include/macro setup is impractical. — §4.
4. **Phase 1 ships syntax-only + native** to derisk fast, before tackling UVM's macro/include complexity. — §11.
5. **Normalized `SvObject` model** isolates `pyslang` API churn. — §8.

Resolved (M. Ballance, 2026-06-28):
- **Dialect priority** — `native` (greenfield) is the first target; NaturalDocs/UVM follows in Phase 2. Phase 1 ships `native` only, as planned in §11.
- **UVM acceptance test** — documenting `packages/uvm` end-to-end is the **Phase-2 acceptance test**. Codified in §11.
- **Whole-tree generation** — **in scope** as a core design goal, not a someday-extra. The chosen model mirrors Sphinx/Python autodoc: build a **project-wide index** by parsing a wide source set once, then let directives *reference a documentation scope* into that index (document all of a package, a file, or a named subtree). See §6.1 and §11 (whole-tree front-end promoted to Phase 3).
```
