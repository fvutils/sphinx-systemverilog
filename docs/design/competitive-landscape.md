# sphinx-systemverilog — Competitive Landscape

**Status:** Research findings for review
**Date:** 2026-06-28
**Author:** competitive research (Claude, deep-research harness) with M. Ballance
**Companion to:** `docs/design/sphinx-systemverilog-design.md` (see §2 "Landscape")
**Method:** Multi-angle web research (5 search angles, 15 primary/secondary sources fetched, 25 claims adversarially verified 3-vote, 0 refuted). Sources are 2026 snapshots; GitHub stars / release dates as observed at time of research.

---

## 1. Bottom line

**No existing Sphinx tool parses SystemVerilog with a real SV front-end.** A `pyslang`-based plugin would be the only one of its kind. Every candidate "competitor" falls into one of four buckets, and each has a structural weakness this project's design already exploits:

1. **Generic-parser Sphinx domains** (lark/regex) — no semantic resolution, immature, stalled.
2. **Diagram/visualization tools** — produce images, not text API docs; not direct competitors.
3. **Right-pattern / wrong-language** — VHDL-only, or C/C++-only (Breathe/Exhale via Doxygen).
4. **Legacy Doxygen-HDL hacks** — dead since ~2018, no native SV.

**Amended 2026-08-14 after examining CVA6 (§2.6):** there is a fifth bucket, and it is the one that
matters. The only tool actually documenting a large live SystemVerilog design is a **bespoke
in-project regex script** — 655 lines of Python, hardcoded module list, 203 hand-maintained lines
recording which ports are tied off. Not a rival, but the honest answer to "what do serious projects
use today". The competition is a blank page and a weekend.

The mature, widely-adopted tooling in this space (Breathe/Exhale) **cannot reach the SystemVerilog market** because its parser (Doxygen) has no native SV support. The category is therefore **wide open** — but also **small**, which is itself the reason no mature tool exists. The strategic risk is market size and solo-maintenance, not being out-built.

---

## 2. Competitors, characterized (maturity / adoption / activity)

### 2.1 `sphinx-verilog-domain` (SymbiFlow) — closest direct rival

| Axis | Assessment |
|---|---|
| **Maturity** | Self-described "development stage." A Sphinx *domain* (directives + roles), but parsing is built on **lark** — a generic parser-generator grammar, **not** a real SV elaborator. No semantic resolution, no class/package type model, no inheritance resolution. |
| **Adoption** | Negligible. A SymbiFlow side-project; not a maintained PyPI package with a discernible user base. |
| **Activity** | Stalled. SymbiFlow itself fragmented (effort largely migrated to F4PGA), leaving this effectively abandoned. |
| **Threat** | **Low.** Validates the *shape* of the approach (custom HDL domain) while leaving the hard part — a real front-end — undone. This is the tool design §2/§31 characterizes as "regex/Verilog-specific, no SV class/package support, no semantic resolution." |

Source: `github.com/SymbiFlow/sphinx-verilog-domain`

> **Design-doc correction:** §2/§31 reference this as `sphinxcontrib-verilog`. Research found no such package; the real artifact is **`SymbiFlow/sphinx-verilog-domain`** (lark-based). The *characterization* holds; the name should be corrected.

### 2.2 Diagram / visualization tools — not competitors, potential complements

Symbolator, `sphinx-hwt`, `sphinxcontrib-hdl-diagrams`, `sphinx-wavedrom`.

| Axis | Assessment |
|---|---|
| **Maturity** | Produce **images, not text API docs**: component symbols, schematics, waveforms. Symbolator uses its own custom HDL parsers (VHDL + Verilog, *not* full SV); `sphinxcontrib-hdl-diagrams` shells out to **Yosys** (+ netlistsvg); `sphinx-hwt` depends on the HWT Python HDL library + d3 schematics; `sphinx-wavedrom` renders timing diagrams only. |
| **Adoption** | Low and fragmented across forks. |
| **Activity** | Mostly stalled/archived. The `hdl/symbolator` fork has **no published releases**; the original `kevinpt/symbolator` is dormant; `sphinx-hwt` is tied to one author's HWT ecosystem. |
| **Threat** | **Not competitors — complements.** They answer "what does this module look like," not "what does this class/method do." Phase 2/4 inheritance & instantiation diagrams overlap slightly; **integration** (e.g. emit Symbolator/hdl-diagrams nodes) is more sensible than competition. |

Sources: `hdl.github.io/symbolator`, `github.com/hdl/symbolator`, `github.com/kevinpt/symbolator`, `github.com/nobodywasishere/symbolator`, `pypi.org/project/sphinx-hwt`, `github.com/SymbiFlow/sphinxcontrib-hdl-diagrams`, `github.com/bavovanachte/sphinx-wavedrom`

### 2.3 `sphinx-vhdl` (CESNET) — the proof the approach works, wrong language

| Axis | Assessment |
|---|---|
| **Maturity** | A genuine Sphinx domain that auto-documents HDL from source — but **VHDL only.** Strongest evidence that "real-language front-end → Sphinx domain" is viable and wanted. |
| **Adoption** | Modest; institutionally backed (CESNET). |
| **Activity** | Maintained but narrowly scoped to VHDL. |
| **Threat** | **Low for SV, high as a model.** Nearest *philosophical* sibling — study its directive design and UX. It does **not** compete for SystemVerilog / UVM users. |

Source: `cesnet.github.io/sphinx-vhdl`

### 2.4 Doxygen-based HDL tooling — legacy, dead

| Axis | Assessment |
|---|---|
| **Maturity** | Doxygen has **no native SystemVerilog support.** The `doxygen-verilog` fork adds Verilog only. |
| **Adoption** | **~41 GitHub stars.** Various Verilog-AMS-via-Doxygen approaches are one-off blog hacks. |
| **Activity** | **Dead since ~2018.** |
| **Threat** | **Low — but architecturally important.** This project's architecture *is* the **Breathe/Exhale** pattern (external parser → XML/model → Sphinx domain) with Doxygen replaced by in-process `pyslang`. Breathe/Exhale are mature and widely adopted — but **only for C/C++**, because Doxygen can't do SV. The mature competition literally cannot reach this market without a front-end it doesn't have. |

Sources: `github.com/avelure/doxygen-verilog`, `onworks.net/software/app-doxverilog`, `sndegroot.blogspot.com` (Verilog-AMS/Doxygen blog), `github.com/brabect1/hdl_api_doc_test`

### 2.5 NaturalDocs — a comment dialect, not a renderer rival

NaturalDocs is what UVM ships (prebuilt ND HTML in `packages/uvm/docs/html`). The design correctly treats it as an **input dialect to read** (Phase 2), not a competing output. ND-the-generator produces its own non-Sphinx HTML and is outside the modern Python/Sphinx docs ecosystem. **Not a competitor; it's a format requirement.**

---

### 2.6 CVA6's `spec_builder.py` — the real competitor, and it is bespoke

**Date examined:** 2026-08-14 · **Source:** `github.com/openhwgroup/cva6`, `docs/scripts/`

The competitors above are general-purpose tools. The one that actually documents a large, live
SystemVerilog design is none of them: it is a **655-line bespoke Python script** that OpenHW Group
wrote for CVA6, their RISC-V application-class core. This is what a serious project does today in
the absence of a tool, and it is the most informative comparison available.

**What it does.** `spec_builder.py` extracts port tables per module and a parameter table from the
configuration struct, emitting AsciiDoc and reStructuredText that a hand-written design manual
`include::`s. `parameters_extractor.py` scrapes `config_pkg.sv`. `define_blacklist.py` records
which ports are tied off in a given configuration.

**How it works, and what that costs them:**

| Mechanism | Consequence |
|---|---|
| Ports extracted by a line regex: `^ +(?:(in\|out)put +([\S]*(?: +.* *\|)) ([\S]*)\n` | Formatting-dependent, and cannot see types, parameters or elaboration |
| The module list is **31 file paths hardcoded in Python** | Documenting a new module means editing the generator |
| `define_blacklist.py` — **203 hand-maintained lines** of "port X is tied to 0 in this config" | Knowledge the elaborator already has, re-entered by hand and able to drift |
| Config values injected into prose as AsciiDoc attributes (`{instr-per-fetch}`) | **Genuinely good** — see §2.6.2 |
| Parameter descriptions scraped from `//` comments on struct fields | Works, but only for one hardcoded struct in one hardcoded file |

**Measured head-to-head on ports.** Running both over the 29 modules in their own hardcoded list:

```
TOTAL                     856     856     +0
```

Their regex extracts **exactly the same number of ports as our parser — 856**. Credit where due:
their RTL is formatted rigorously enough that a regex works. But it gets **three port names wrong**
out of 856, and the failures show the mechanism's fragility rather than a coding slip:

- `serdiv.opcode_i` is reported as `rem`, because the line carries a trailing comment
  (`input logic [1:0] opcode_i,  // 0: udiv, 2: urem, 1: div, 3: rem`) and the greedy regex takes
  the last token.
- `id_stage.sdtrig_decoder_action_i` is reported as `sdtrig_decoder_action_i[CVA6Cfg.NrIssuePorts]`,
  with the unpacked array dimension glued into the name.

The honest reading: **the regex is not inaccurate today, it is undefended.** It holds because the
codebase is uniformly formatted, and it fails silently when that assumption breaks. That is a
maintenance liability, not a present defect — and it is the argument for a real front-end.

#### 2.6.1 What we do that they cannot

Everything structural. Their tool sees one file at a time, so the questions it cannot answer are
exactly the ones this project targets:

- **Instantiation hierarchy.** Their design manual documents module composition in hand-written
  prose and hand-drawn PNGs. We generate it: `cva6` → 11 children → 337 instances, generate paths
  and elaborated parameters included.
- **Used-by.** Absent entirely.
- **Parameter matrix.** Absent. We report, for example, that `lzc` is elaborated at six distinct
  widths across 50 sites.
- **Tied-off ports.** Their `define_blacklist.py` is the hand-written version of our `M3-IMPL-4`
  (constant-tied port detection). That 203-line file is the single strongest argument in this
  document for elaboration-based documentation: it is derivable, and they maintain it by hand.

There is also prose in their manual that *asserts* what we compute:

> "As compressed extension is enabled, {instr-per-fetch} `instr_scan` are instantiated..."

We render `gen_instr_scan[*].i_instr_scan : instr_scan (×2)` from the elaborated design. Their
sentence is true today and will not be checked by anything if it stops being true.

#### 2.6.2 What they do that we should learn from

Three things, none of which we currently have. They are recorded as proposed work, not as defeats:

1. **Configuration values substituted into narrative prose.** `{instr-per-fetch}`, `{ohg-config}`
   and ~40 more are generated from the elaborated configuration and used throughout hand-written
   text, so the prose cannot silently disagree with the build. **We have no equivalent.** A role
   that inlines an elaborated parameter — `:sv:value:`cva6:CVA6Cfg.NrIssuePorts`` — would be a
   small change with an outsized effect on doc trustworthiness, and would extend naturally to
   computed structural facts (instance counts).
2. **Struct and enum members as documented objects.** Their `parameters_extractor.py` exists
   *solely* because a packed-struct typedef's fields are not otherwise documentable. We have the
   same gap, verified: we index `config_pkg::cva6_user_cfg_t` as a typedef with **zero children**.
   For RTL a config struct is a first-class API surface and its fields carry doc comments. This is
   arguably a larger gap than anything in the module-documentation plan.
3. **A "connects to" column on every port.** Their convention is `// <description> - <SUBSYSTEM>`,
   hand-tagged. It validates that readers want to know what a port attaches to — which our
   `M3-IMPL-1` can answer from `portConnections` with the *actual* instance rather than a manual
   tag. Their manual tagging is evidence of demand, and evidence that we should rank M3 higher.

#### 2.6.3 Architectural validation

Their design manual is **hand-written prose per module with generated tables included into it**
(`include::port_frontend.adoc[]`). That is exactly the narrative-plus-autodoc split this project
assumes, arrived at independently by a large project. Our standalone structural directives
(`sv:used-by::`, `sv:instance-tree::`) support the same composition, which is worth keeping: a
design manual is not an API dump, and the generated content has to be embeddable into prose rather
than only replacing it.

**Threat assessment: none, and that is the point.** `spec_builder.py` is not distributable — it is
CVA6-specific, with hardcoded paths and a hardcoded module list. Every project doing this today is
writing its own. That is the market.

---

## 3. The moat — and the honest counterweights

**Moat (real and singular):** `pyslang` provides Python bindings to **slang, a full SystemVerilog compiler/elaborator.** No competitor has a real SV front-end. That is the difference between "regex that finds `module foo`" and resolved type hierarchies, cross-module references, parameterized classes, and UVM — i.e., the difference between a toy and `autodoc`-for-SV.

Source: `github.com/MikePopoloski/pyslang`

**Counterweights (competitive intelligence, not a victory lap):**

- **The niche is small.** The absence of a mature tool isn't only difficulty — it's limited demand. HDL teams often live in vendor tools, C-style Doxygen flows, or simply don't auto-doc. *Wide-open category ≠ large category.*
- **"No competitor" also means "no community to inherit."** sphinx-vhdl and Breathe prove the pattern works, but the SV user base must be built and supported largely from scratch. UVM-as-acceptance-test (design §11, P2-ACC) is smart precisely because it targets the one place with a real, identifiable audience.
- **`slang`/`pyslang` is both moat and dependency risk.** The §8 `SvObject` normalization (isolating `pyslang` API churn) is the correct hedge; keep that boundary strict.

**Net:** No *direct* competitor — only an architectural template to borrow from (sphinx-vhdl, Breathe/Exhale) and a field of stalled, image-only, or wrong-language tools.

**Amended after examining CVA6 (§2.6):** the more accurate statement is that the competition is
not a *tool* at all — it is **each project writing its own regex scraper**. That reframes the
opportunity: the pitch is not "better than tool X", it is "delete your `spec_builder.py`". It also
sets a concrete bar, because a bespoke script is tuned to its project and will beat a general tool
on that project's conventions unless we cover the same ground (§2.6.2).

---

## 4. Competitor scorecard

| Tool | Category | Parser | Native SV? | Maturity | Adoption | Activity | Threat |
|---|---|---|---|---|---|---|---|
| `sphinx-verilog-domain` (SymbiFlow) | Sphinx domain | lark (generic) | partial, no semantics | dev stage | negligible | stalled | **Low** |
| Symbolator | diagram | custom HDL | no | usable, narrow | low | dormant / no releases | none (complement) |
| `sphinxcontrib-hdl-diagrams` | diagram | Yosys | no | usable | low | stalled | none (complement) |
| `sphinx-hwt` | diagram | HWT lib | no | narrow | low | author-tied | none (complement) |
| `sphinx-wavedrom` | diagram (waveforms) | n/a | no | stable | moderate | maintained | none (orthogonal) |
| `sphinx-vhdl` (CESNET) | Sphinx domain | VHDL parser | **no (VHDL only)** | genuine | modest | maintained | **Low / model** |
| `doxygen-verilog` | docgen | Doxygen fork | no (Verilog only) | legacy | ~41★ | dead ~2018 | **Low** |
| Breathe / Exhale | docgen → Sphinx | Doxygen | no | **mature** | **high** | active | **Low (C/C++ only)** |
| NaturalDocs | docgen (standalone) | own | reads SV comments | mature/old | legacy | maintained | none (dialect to read) |
| **CVA6 `spec_builder.py`** | bespoke, in-project | **line regex** | Verilog-2001 subset | in production | one project | active | **none (not distributable) — but it is what the market does today** |
| **sphinx-systemverilog (this)** | Sphinx domain + autodoc | **pyslang/slang** | **yes (full)** | building | — | — | — |

---

## 5. Sources

Primary unless noted.

- `github.com/SymbiFlow/sphinx-verilog-domain`
- `cesnet.github.io/sphinx-vhdl`
- `hdl.github.io/symbolator`, `github.com/hdl/symbolator`, `github.com/kevinpt/symbolator`, `github.com/nobodywasishere/symbolator`
- `github.com/SymbiFlow/sphinxcontrib-hdl-diagrams`, `sphinxcontrib-hdl-diagrams.readthedocs.io`
- `pypi.org/project/sphinx-hwt`
- `github.com/bavovanachte/sphinx-wavedrom`
- `github.com/avelure/doxygen-verilog`, `onworks.net/software/app-doxverilog` (secondary), `sndegroot.blogspot.com` (blog)
- `github.com/brabect1/hdl_api_doc_test`
- `github.com/MikePopoloski/pyslang`
- `github.com/openhwgroup/cva6` — `docs/scripts/{spec_builder,parameters_extractor,define_blacklist,classes}.py`, `docs/design/design-manual/source/*.adoc`, `core/Flist.cva6` (examined at `master`, 2026-08-14)
