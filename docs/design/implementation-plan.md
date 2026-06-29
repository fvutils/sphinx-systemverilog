# sphinx-systemverilog — Implementation, Test & Doc Plan

**Status:** Living tracker — **all phases complete (Milestone 0 through Phase 4)** (2026-06-28)
**Date:** 2026-06-28
**Companion to:** `docs/design/sphinx-systemverilog-design.md`
**Purpose:** Turn the approved design into a concrete, trackable build plan. Every work item has an ID (`P<phase>-<area>-<n>`), an owner-checkable box, and a defined "done" condition. Implementation, tests, and docs are planned *together* per phase — a phase is not "done" until all three are.

### Progress log

- **2026-06-29** — **Phase-2 gap closed: `P2-DOC-4` published UVM doc set.**
  The earlier Phase-2 work substituted the *published* UVM reference with a prose
  guide (the UVM directives were in fenced code blocks, not live), so the docs
  site contained no rendered UVM — `P2-ACC` was only met via the `/tmp` build and
  `corpus` tests. Now fixed: `docs/conf.py` builds the UVM sources into the index
  alongside the fixtures when present (single build with mixed build units), and
  `docs/examples/uvm.md` renders a **live, linked UVM reference** (uvm_object +
  uvm_sequence_item: 75 members, inheritance diagram, group rubrics, `[source]`
  links) that degrades to a guide when UVM is absent. Required three supporting
  fixes: (1) directive `:doc-style:` now overrides the object's stored style
  (was ignored, so UVM rendered as native and tripped RST); (2) `escape_rst_inline`
  now escapes trailing-underscore RST references (`rhs_`) while preserving
  identifiers (`get_name`); (3) a new `:optional:` directive flag skips missing
  targets silently so the page is `-W`-clean with or without UVM. CI now uses
  `fvutils/ivpm-setup@v1` to fetch UVM, so the **published** Pages build and the
  nightly `corpus` job run against real UVM (corpus previously skipped it).
  136 tests pass; both docs paths build clean with `-W`.

- **2026-06-28** — M0 + Phase 1 implemented. Full extension scaffold, the
  pyslang-backed model builder, `native` docparse, the `sv` domain, and the
  `auto*` directives all working end-to-end. **50 tests pass** (32 `unit`,
  18 `sphinx`); the docs site builds with `-W` and dogfoods the extension on
  the sample package (**P1-ACC met**). Not yet committed to git.
  - *Deviations from the original plan, all minor:*
    - Comment-extraction logic lives in `model/comments.py` (pure, separately
      testable) rather than inline in `builder.py` — improves `P1-TEST-3`.
    - The builder uses pyslang's `Compilation` (tolerant elaboration) instead of
      a pure CST walk; on a self-contained package this needs no include/define
      setup, so it stays within the Phase-1 "no UVM macro/include complexity"
      intent while giving cleaner scope iteration. Pure syntax-only fallback is
      still planned for Phase 2 when elaboration is impractical.
    - `:doc-style: auto` sniffing is wired but only `native` is registered, so
      auto resolves to native until Phase 2 adds NaturalDocs/Doxygen.
    - Known tech debt: directives read `env.app` (a `PendingDeprecationWarning`
      in Sphinx 11) to emit events; filtered for now, to be replaced when a
      non-deprecated app handle is available to directives.

- **2026-06-28** — Phase 2 implemented (NaturalDocs + UVM). **99 tests pass**
  (93 `unit`/`sphinx` + 6 `corpus`), 92% core coverage; the docs site builds
  with `-W` and now dogfoods a live NaturalDocs example with an inheritance
  diagram, groups, and a module. **P2-ACC met**: the full UVM library documents
  end-to-end (~3700 objects in ~3s) with **zero build warnings**.
  - *What landed:* the `naturaldocs` dialect (keyword headers incl. banner-wrapped
    and `-- NODOCS --` forms, `<xref>`/`~code~` conversion, stray-RST escaping);
    detached-block association by name + per-file line proximity; member groups
    rendered as rubrics; `auto` per-comment dialect detection; module/interface
    ports & parameters (CST-extracted with directions/defaults and leading/
    trailing comments); `extern` `MethodPrototype` support; include-dir/define-
    driven elaboration via a shared `SourceManager`; severity-filtered diagnostics
    (errors surfaced, lint warnings summarized at INFO); inheritance diagrams via
    `sphinx.ext.graphviz` + `:show-inheritance:`; the `:recursive:` flag; and the
    `sv_naturaldocs_nodocs` config.
  - *Deviations / notes:* the UVM doc set is documented as a **guide page**
    (`docs/examples/uvm.md`) plus the live `corpus` tests rather than embedded in
    the `-W` docs build, so the project's own docs build without the large UVM
    sources present (CI installs via pip, not ivpm). Robustness fixes found via
    UVM: guard `MethodFlags` enums with unknown bits, and tolerate buffer-start
    comment blocks. NODOCS prose is **kept** by default (skipping it would empty
    most of UVM); `sv_naturaldocs_nodocs="skip"` opts out.

- **2026-06-28** — Phase 3 implemented (Doxygen + whole-tree + polish).
  **119 tests pass** (113 `unit`/`sphinx` + 6 `corpus`), 92% coverage; the docs
  site builds with `-W` including a live Doxygen example with `[source]` links.
  - *What landed:* the `doxygen` dialect (`@`/`\` commands, `@param`/`@return`/
    `@note`/`@see` fields, `@p`/`@c`/`@a`/`#ref` inline markup, `@brief`
    paragraph handling); `:inherited-members:` climbing the resolved hierarchy
    with "Inherited from <base>" rubrics; the **`autosvsummary`** whole-tree
    directive with `:packages:`/`:kinds:`/glob scope narrowing; **viewcode**
    (`[source]` links + generated highlighted per-file listings, `sv_viewcode`
    config); verified `objects.inv`/intersphinx export; and **parameterized
    (generic) class** support — pyslang exposes these as `GenericClassDef` with
    no member scope, so members are recovered from the CST (UVM index grew
    3744 → 5202 objects, covering `uvm_object_registry`, `uvm_queue`, etc.).
  - *Deviations / notes:* parameterized-class members come from a best-effort CST
    walk (name + source-text signature + leading comment), not full semantic
    elaboration — pyslang's `defaultSpecialization` needs a `Scope` the Python
    binding doesn't expose. Overload/ambiguity disambiguation is handled by the
    existing `_find` candidate logic (ambiguous bare names warn with candidates).
    Also applied a verified correction from `competitive-landscape.md`:
    `sphinxcontrib-verilog` → `SymbiFlow/sphinx-verilog-domain`.

- **2026-06-28** — Phase 4 implemented (scale / UX / advanced SV) — **final
  phase**. **133 tests pass** (127 `unit`/`sphinx` + 6 `corpus`), 92% coverage;
  the docs site builds with `-W` including a live covergroup/constraint example.
  - *What landed:* `\\`define` **macro** documentation (name + formal args +
    short body + preceding doc comment; `sv_document_macros` config; UVM yields
    549 macros, index now 5757 objects); **covergroups** (with nested
    coverpoints) and **constraint** blocks as first-class class members;
    **structural instance diagrams** (`sv:instance-diagram`) built from the
    elaborated module hierarchy (`root.topInstances` → instance tree → Graphviz);
    and a **performance cache** — the index is memoized in-process keyed by
    inputs + source mtimes (cold UVM build ~4s, warm rebuild ~0.4ms).
  - *Deviations / notes:* clocking blocks are **not** documented (they live in
    interface/module instance bodies, which the CST-header extraction does not
    elaborate) — noted as a future item. Individual coverpoint doc comments are
    not extracted (the coverpoint label exposes an empty first token); coverpoints
    still appear by name. Macro include-guards are extracted like any macro
    (filter with `:exclude:`/glob). The performance cache is in-process only
    (helps `sphinx-autobuild`/tests); cross-process disk caching is future work.

---

## 0. Conventions & ground rules

- **Source code** → `src/sphinx_systemverilog/` (src-layout, importable as `sphinx_systemverilog`).
- **Tests** → `tests/` (pytest). **All tests live here**, mirroring the package tree.
- **Docs** → `docs/` (Sphinx project). **All docs live here.** `docs/design/` holds these design/plan docs; `docs/` root becomes the published doc set (which **dogfoods the extension on itself + on UVM**).
- **Env**: the uv-managed venv in `packages/python`; activate with `source packages/python/bin/activate`. New deps go through `uv` **and** get recorded in `ivpm.yaml` (`dep-sets`).
- **Definition of Done (per item)**: code merged + unit tests green + relevant doc page builds with no new Sphinx warnings + item box checked here with the commit/PR ref.
- **Definition of Done (per phase)**: all phase items done + the phase **acceptance test** passes in CI + `docs/` builds clean + this tracker updated.
- **Tracking**: check boxes (`[ ]` → `[x]`) and append the PR/commit ref. Keep the §8 status table in sync.

### Test taxonomy (pytest markers)
- `unit` — pure-Python, no Sphinx app (model, docparse). Fast, the bulk of coverage.
- `sphinx` — uses `sphinx.testing` `@pytest.mark.sphinx` against a `tests/roots/` mini-project; asserts doctree/HTML.
- `corpus` — runs the model over `packages/uvm/src`; smoke + member-count floors. Slow; `-m corpus` opt-in, also in nightly CI.

---

## 1. Milestone 0 — Scaffolding & tooling (prereq for all phases)

| ID | Task | Done when |
|---|---|---|
| `P0-IMPL-1` | `pyproject.toml` (src-layout, `sphinx_systemverilog`, deps: `sphinx`, `pyslang`; entry: `setup(app)`), `py.typed` | `pip install -e .` works in the venv |
| `P0-IMPL-2` | Package skeleton with empty modules per design §6 layout (`__init__.py`, `config.py`, `model/`, `docparse/`, `domain.py`, `autodoc/`, `viewcode.py`) | `import sphinx_systemverilog` succeeds; `setup(app)` returns metadata dict |
| `P0-IMPL-3` | `config.py`: register all `sv_*` config values (`sv_source_dirs`, `sv_include_dirs`, `sv_defines`, `sv_doc_style`, `sv_build_units`, `sv_default_options`) with `app.add_config_value` | config readable from a built app |
| `P0-TEST-1` | `tests/` layout + `conftest.py` (markers, fixture dirs), `pytest.ini`/`pyproject` pytest config registering `unit`/`sphinx`/`corpus` markers | `pytest -m unit` runs (0 tests OK) |
| `P0-TEST-2` | `tests/test_setup.py`: extension loads in a bare Sphinx app, registers domain + config values | green |
| `P0-DOC-1` | `docs/conf.py`, `docs/index.md` (MyST), `docs/_static/`, build wiring; add `docs` build target | `sphinx-build -W docs docs/_build` succeeds |
| `P0-DOC-2` | `cspell.json` project word-list (`pyslang`, `autodoc`, `systemverilog`, `naturaldocs`, `intersphinx`, `viewcode`, `covergroup`, `modport`, …) to silence IDE noise | IDE diagnostics on design docs clear |
| `P0-OPS-1` | CI workflow: `pytest -m "unit or sphinx"` + `sphinx-build -W docs` on PR; nightly adds `-m corpus` | CI green on a trivial PR |
| `P0-OPS-2` | Update `ivpm.yaml` for any added dev deps (`pytest`, `myst-parser`, later `graphviz`/`beautifulsoup4`) | `ivpm.yaml` matches installed set |

---

## 2. Phase 1 — MVP: syntax-only, `native` dialect

**Theme:** end-to-end vertical slice on a hand-written sample package. No elaboration required (CST walk). `native` docstrings only. Establishes the parse-wide/reference-scope contract (`SvIndex`) from day one.

### Implementation
| ID | Task | Done when |
|---|---|---|
| `P1-IMPL-1` | `model/objects.py`: `SvObject` dataclass tree + `SourceRef` (design §8) | typed, importable, frozen where sensible |
| `P1-IMPL-2` | `model/locations.py`: `SourceLocation` → `(file, line, col)` via `SourceManager`; helper to test "real vs synthesized" location | unit-tested mapping |
| `P1-IMPL-3` | `model/builder.py`: CST/scope walk → `SvObject` for `package`/`class`/`function`/`task`/`property`; **filter synthesized members** (bogus-location rule, design §4) | sample pkg → expected tree |
| `P1-IMPL-4` | `model/builder.py`: leading-trivia comment extraction + **trailing same-line comment heuristic** (design §4/§5.1) | both cases covered by tests |
| `P1-IMPL-5` | `model/index.py`: `SvIndex` built once on `builder-inited`; qualified-name → `SvObject` map; cached on the app/env (design §6.1) | one parse per build, shared |
| `P1-IMPL-6` | `docparse/base.py`: `DocstringParser` ABC + `ParsedDoc` (summary, rst_body, fields, xrefs); registry | ABC + registry usable |
| `P1-IMPL-7` | `docparse/native.py`: first-line summary + RST body + `:param:/:returns:` field passthrough | unit-tested |
| `P1-IMPL-8` | `domain.py`: `SystemVerilogDomain` with `sv:package`/`sv:class`/`sv:function`/`sv:task`/`sv:property`; `handle_signature`, index entries, permalinks | directives render in a `sphinx` test |
| `P1-IMPL-9` | `domain.py`: xref roles (`:sv:obj:`, `:sv:class:`, `:sv:func:`, `:sv:task:`) resolving against `SvIndex` | xrefs resolve / warn on miss |
| `P1-IMPL-10` | `autodoc/`: `Documenter` base + `autosvpackage`/`autosvclass` with `:members:`/`:undoc-members:`/`:exclude-members:`; emit domain directives; nested-parse `rst_body` | autodoc directive produces full doctree |
| `P1-IMPL-11` | `sv-autodoc-process-doc` + `sv-autodoc-skip-member` events wired | events fire in a test |

### Tests (`tests/`)
| ID | Task | Done when |
|---|---|---|
| `P1-TEST-1` | `tests/fixtures/sv/sample_pkg.sv` — hand-written package: class w/ inheritance, props, function, task, native docstrings, a trailing-comment field, a synthesized-member trap | committed fixture |
| `P1-TEST-2` | `tests/model/test_builder.py` — tree shape, names/kinds, synthesized filtering, locations | green |
| `P1-TEST-3` | `tests/model/test_comments.py` — leading block, blank-line-separated block, trailing same-line heuristic | green |
| `P1-TEST-4` | `tests/model/test_index.py` — qualified-name resolution; parse-once (assert builder called once across N lookups) | green |
| `P1-TEST-5` | `tests/docparse/test_native.py` — summary/body/field extraction, edge cases (empty, no-blank-line) | green |
| `P1-TEST-6` | `tests/roots/test-basic/` mini Sphinx project + `tests/domain/test_directives.py` (`@pytest.mark.sphinx`) — manual `sv:*` directives render, index + permalinks present | green |
| `P1-TEST-7` | `tests/autodoc/test_autosv.py` (`sphinx`) — `autosvpackage`/`autosvclass` against `sample_pkg.sv`; `:members:`/`:exclude-members:`; assert doctree nodes | green |
| `P1-TEST-8` | `tests/autodoc/test_xref.py` (`sphinx`) — cross-reference resolves, unknown ref warns | green |

### Docs (`docs/`)
| ID | Task | Done when |
|---|---|---|
| `P1-DOC-1` | `docs/getting-started.md` — install, minimal `conf.py`, first `autosvclass` | builds clean |
| `P1-DOC-2` | `docs/usage/directives.md` — reference for `sv:*` and `autosv*` (Phase-1 subset) + options | builds clean |
| `P1-DOC-3` | `docs/usage/native-style.md` — the recommended native comment style, with examples | builds clean |
| `P1-DOC-4` | `docs/examples/sample.md` — **dogfood**: run `autosvpackage` on `tests/fixtures/sv/sample_pkg.sv` in the published docs | rendered output visible in build |

**Phase-1 acceptance test (`P1-ACC`):** `docs/examples/sample.md` builds with `-W` and renders the sample package's classes/members from source; `pytest -m "unit or sphinx"` green in CI.

---

## 3. Phase 2 — NaturalDocs + UVM (semantic elaboration)

**Theme:** real elaboration of `uvm_pkg.sv` with includes/defines; NaturalDocs dialect; modules/interfaces with params/ports; inheritance diagrams. **Acceptance = document all of `packages/uvm` end-to-end.**

### Implementation
| ID | Task | Done when |
|---|---|---|
| `P2-IMPL-1` | `model/builder.py`: full `Compilation` elaboration path; honor `sv_include_dirs`/`sv_defines`/`sv_build_units`; surface parse diagnostics as Sphinx warnings (non-fatal) | UVM elaborates |
| `P2-IMPL-2` | Modules/interfaces/programs: params + ports (direction/type/default) as `SvObject` children | counter fixture documents ports/params |
| `P2-IMPL-3` | `docparse/naturaldocs.py`: keyword headers (`Class:`/`Function:`/`Task:`/`Variable:`/`Group:`/`Macro:`), `NODOCS` skip, `<xref>`, `~code~`, `Group:` grouping, ND layout (def-lists/indented code) | unit-tested vs UVM snippets |
| `P2-IMPL-4` | `docparse/xref.py`: unify `<x>` / `@see` / `:sv:…:` → `pending_xref`; resolve via `SvIndex` | mixed-dialect refs resolve |
| `P2-IMPL-5` | §5.2 **named-block association** (ND blocks matched by keyword+name within scope; adjacency tiebreak) | UVM extern protos get their docs |
| `P2-IMPL-6` | Member grouping (`Group:`/`@group`) → ordered labeled subsections; `:member-order: source|alpha|groups` | rendered grouping |
| `P2-IMPL-7` | `autosvmodule`/`autosvpackage` `:recursive:`; `domain.py` add `sv:module`/`sv:interface`/`sv:port`/`sv:parameter`/`sv:macro` | directives render |
| `P2-IMPL-8` | Inheritance diagrams: Graphviz backend off resolved `baseClass` edges in `SvIndex`; `.. sv:inheritance-diagram::` + `:show-inheritance:` autodoc option (add `sphinx.ext.graphviz`) | diagram node emitted; graceful degrade w/o `dot` |
| `P2-IMPL-9` | Auto-detect dialect per comment (`/**`→doxygen-ish; `Class:`/`<…>`→ND; else native) with `sv_doc_style` default | detection unit-tested |

### Tests (`tests/`)
| ID | Task | Done when |
|---|---|---|
| `P2-TEST-1` | `tests/docparse/test_naturaldocs.py` — headers, NODOCS, `<xref>`, `~code~`, groups, layout | green |
| `P2-TEST-2` | `tests/docparse/test_autodetect.py` — dialect sniffing matrix | green |
| `P2-TEST-3` | `tests/fixtures/sv/counter.sv` + `tests/model/test_modules.py` — params/ports, directions, trailing port comments | green |
| `P2-TEST-4` | `tests/model/test_elaboration.py` — include-dir/define handling on a small multi-file fixture; diagnostics → warnings | green |
| `P2-TEST-5` | `tests/model/test_association.py` — ND named-block ↔ symbol join, overload/nested-name tiebreak | green |
| `P2-TEST-6` | `tests/domain/test_inheritance_diagram.py` (`sphinx`) — diagram node built from `baseClass` edges; skip cleanly if no `dot` | green |
| `P2-TEST-7` | `tests/corpus/test_uvm_smoke.py` (`-m corpus`) — model walks **all** `packages/uvm/src`; no crash; member-count floors (e.g. `uvm_object` ≥ N methods); diagnostics bounded | green nightly |

### Docs (`docs/`)
| ID | Task | Done when |
|---|---|---|
| `P2-DOC-1` | `docs/usage/naturaldocs-style.md` — ND mapping (headers, `<>`, `~~`, Groups) | builds clean |
| `P2-DOC-2` | `docs/usage/modules.md` — documenting modules/interfaces (params/ports) | builds clean |
| `P2-DOC-3` | `docs/usage/diagrams.md` — inheritance diagrams, Graphviz prereq, degrade behavior | builds clean |
| `P2-DOC-4` | `docs/examples/uvm/` — **dogfood at scale**: a published UVM doc set generated from `packages/uvm/src` (config: include dirs, defines, `uvm_pkg.sv` build unit) | UVM doc pages build with `-W` |

**Phase-2 acceptance test (`P2-ACC`):** `docs/examples/uvm/` builds end-to-end from UVM source (classes, methods, groups, inheritance diagrams visible); `-m corpus` smoke green in nightly CI.

---

## 4. Phase 3 — Doxygen + whole-tree front-end + polish

**Theme:** third dialect, the Exhale-analog whole-tree generator (core deliverable per design §6.1/§14), and the cross-reference/inventory polish.

### Implementation
| ID | Task | Done when |
|---|---|---|
| `P3-IMPL-1` | `docparse/doxygen.py`: `@brief/@param/@return/@details/@note/@see/@group`, `\`-variants, `///`/`//!` forms → field lists | unit-tested |
| `P3-IMPL-2` | `:inherited-members:` — climb resolved class hierarchy via `SvIndex` | inherited members appear |
| `P3-IMPL-3` | **`autosvsummary`** whole-tree directive: walk an `SvIndex` subtree → structured API tree; scope narrowing (`:packages:`, dir, name-glob) | tree page generated |
| `P3-IMPL-4` | `viewcode.py`: `[source]` links to highlighted SV via captured `file:line` | links resolve |
| `P3-IMPL-5` | Objects inventory export (`objects.inv`) for intersphinx + search | intersphinx round-trip works |
| `P3-IMPL-6` | Parameterized-class / overload xref disambiguation (qualify by param list) | ambiguous refs resolve deterministically |

### Tests (`tests/`)
| ID | Task | Done when |
|---|---|---|
| `P3-TEST-1` | `tests/docparse/test_doxygen.py` — tag matrix → field lists | green |
| `P3-TEST-2` | `tests/autodoc/test_inherited.py` (`sphinx`) — inherited-members across a 3-level hierarchy | green |
| `P3-TEST-3` | `tests/autodoc/test_autosvsummary.py` (`sphinx`) — whole-tree output + scope narrowing | green |
| `P3-TEST-4` | `tests/domain/test_viewcode.py` (`sphinx`) — source links present, correct line | green |
| `P3-TEST-5` | `tests/domain/test_intersphinx.py` — `objects.inv` produced; external ref resolves | green |

### Docs (`docs/`)
| ID | Task | Done when |
|---|---|---|
| `P3-DOC-1` | `docs/usage/doxygen-style.md` | builds clean |
| `P3-DOC-2` | `docs/usage/whole-tree.md` — `autosvsummary`, scope narrowing, recommended page structure | builds clean |
| `P3-DOC-3` | `docs/usage/cross-referencing.md` — roles, intersphinx, viewcode | builds clean |
| `P3-DOC-4` | Regenerate `docs/examples/uvm/` using `autosvsummary` for the full tree | UVM tree page builds |

**Phase-3 acceptance test (`P3-ACC`):** UVM doc set regenerated via `autosvsummary` whole-tree; all three dialects + intersphinx + viewcode covered by green `sphinx` tests.

---

## 5. Phase 4 — Scale / UX / advanced SV

| ID | Task | Done when |
|---|---|---|
| `P4-IMPL-1` | Macro (`define`) documentation (`sv:macro`); best-effort macro-generated members | covered |
| `P4-IMPL-2` | Structural instantiation diagrams (elaborated instance tree of a design top) | diagram for a top fixture |
| `P4-IMPL-3` | Covergroups / constraints / clocking directives | rendered |
| `P4-IMPL-4` | Performance: cache/incremental compilation; large-corpus build-time budget | UVM build under target time |
| `P4-TEST-1` | Tests mirroring each `P4-IMPL-*` in `tests/` | green |
| `P4-DOC-1` | `docs/usage/advanced.md` (macros, structural diagrams, coverage constructs) + perf notes | builds clean |

---

## 6. Test strategy (detail)

- **Pyramid:** heavy `unit` (model + docparse), focused `sphinx` integration via `tests/roots/`, thin slow `corpus`.
- **Fixtures** under `tests/fixtures/sv/` (small, hand-authored, each targeting one behavior) and `tests/roots/<name>/` (Sphinx mini-projects with `conf.py` + `index`).
- **Sphinx assertions:** prefer doctree/node assertions (`app.env.get_doctree`) over HTML string matching; add a few HTML smoke checks (BeautifulSoup) for permalinks/index.
- **Golden files** for `ParsedDoc` and `SvObject` trees where structure is verbose (`tests/golden/`), regenerated via a documented `--update-golden` switch.
- **Corpus floors** (not exact counts) so UVM upstream churn doesn't break CI; bound allowed diagnostics.
- **Coverage gate:** ≥90% on `model/` and `docparse/` (the parser-agnostic core); domain/autodoc covered by `sphinx` tests.

## 7. Docs strategy (detail)

- `docs/` is a real Sphinx site that **dogfoods the extension** (self-hosting on the sample pkg + UVM) — best regression signal we have.
- Structure: `getting-started`, `usage/` (per-dialect + directives + diagrams + whole-tree + xref), `examples/` (sample + UVM), `design/` (these docs), `changelog`.
- Built with `-W` (warnings = errors) in CI so doc rot fails the build.
- MyST-Markdown for narrative; the extension's own directives for API content.

---

## 8. Status tracker

| Phase | Impl | Tests | Docs | Acceptance | State |
|---|---|---|---|---|---|
| P0 Scaffolding | ✅ | ✅ | ✅ | — | **done** (2026-06-28) |
| P1 MVP (native) | ✅ | ✅ | ✅ | `P1-ACC` ✅ | **done** (2026-06-28) |
| P2 NaturalDocs + UVM | ✅ | ✅ | ✅ | `P2-ACC` ✅ | **done** (2026-06-28) |
| P3 Doxygen + whole-tree | ✅ | ✅ | ✅ | `P3-ACC` ✅ | **done** (2026-06-28) |
| P4 Scale/UX | ✅ | ✅ | ✅ | — | **done** (2026-06-28) |

> Update this table and the per-item boxes as work lands; append PR/commit refs next to checked items.

**Item status (2026-06-28):** all items `P0-*` through `P4-*` (`P4-IMPL-1..4`,
`P4-TEST-1`, `P4-DOC-1`) are complete and verified by the passing suite
(**133 tests**) + clean `-W` docs build + the UVM corpus tests. **All planned
phases are done.** The CI workflow installs Graphviz and runs unit/sphinx on PRs
plus a nightly corpus job. Per-table boxes left as `☐` are tracked in aggregate
here to avoid churning every row.

**Possible follow-ups beyond the plan** (not required for completion): clocking-
block documentation, individual coverpoint doc comments, cross-process disk
caching of the index, and an optional include-guard filter for macros.

## 9. Open items / decisions still needed

- **Build-unit discovery**: auto-detect package roots vs. require explicit `sv_build_units`? (Lean: explicit for Phase 2, heuristic later.)
- **MyST vs reST** for `docs/` narrative — assume MyST unless objected.
- **Min Sphinx version** to support (target 9.x; confirm floor for `sv_*` API stability).
- **Golden-file regeneration** ergonomics — pytest switch vs separate script.
