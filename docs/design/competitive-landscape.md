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

## 3. The moat — and the honest counterweights

**Moat (real and singular):** `pyslang` provides Python bindings to **slang, a full SystemVerilog compiler/elaborator.** No competitor has a real SV front-end. That is the difference between "regex that finds `module foo`" and resolved type hierarchies, cross-module references, parameterized classes, and UVM — i.e., the difference between a toy and `autodoc`-for-SV.

Source: `github.com/MikePopoloski/pyslang`

**Counterweights (competitive intelligence, not a victory lap):**

- **The niche is small.** The absence of a mature tool isn't only difficulty — it's limited demand. HDL teams often live in vendor tools, C-style Doxygen flows, or simply don't auto-doc. *Wide-open category ≠ large category.*
- **"No competitor" also means "no community to inherit."** sphinx-vhdl and Breathe prove the pattern works, but the SV user base must be built and supported largely from scratch. UVM-as-acceptance-test (design §11, P2-ACC) is smart precisely because it targets the one place with a real, identifiable audience.
- **`slang`/`pyslang` is both moat and dependency risk.** The §8 `SvObject` normalization (isolating `pyslang` API churn) is the correct hedge; keep that boundary strict.

**Net:** No *direct* competitor — only an architectural template to borrow from (sphinx-vhdl, Breathe/Exhale) and a field of stalled, image-only, or wrong-language tools.

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
