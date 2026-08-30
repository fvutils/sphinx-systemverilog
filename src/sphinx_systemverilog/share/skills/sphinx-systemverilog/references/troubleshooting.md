# Troubleshooting

Symptom → cause → fix. Every warning this extension emits is logged with the
Sphinx warning type `systemverilog`, so `suppress_warnings = ["systemverilog"]`
silences all of them at once — which is almost never the right response, since
most of these warnings are reporting a real gap in what got documented.

Read the info line first:

```
sphinx-systemverilog: indexed 5713 SystemVerilog object(s)
```

If that number is far below what the tree holds, the problem is the source
configuration, not any page.

---

## Nothing is documented

**`sphinx-systemverilog: source index not built`**
The extension is in `extensions` but `builder-inited` did not run, or a
directive ran in a process without the index. Do a full rebuild
(`sphinx-build -E`).

**`cannot find SystemVerilog object 'x'` / `is the extension configured with sv_source_dirs?`**
The name is not in the index. In order of likelihood:

1. Its file was never parsed — widen `sv_source_dirs`, or add the file to
   `sv_build_units`.
2. It is behind an `` `ifdef `` that is not set — add `sv_defines`.
3. Its include could not be found — add `sv_include_dirs`.
4. The name is misspelled or under-qualified. Try the fully qualified
   `pkg::class::member`.

**`sphinx-systemverilog: 'x' is a class, not a module`**
Right name, wrong directive. Use the `auto*` directive matching the kind.

**Parser diagnostics: `sphinx-systemverilog (parser): ...`**
Real syntax or elaboration errors from `pyslang`. Non-error diagnostics are
suppressed and counted (`suppressed N non-error parser diagnostic(s)`). Fix the
configuration that produced them — usually a missing include directory or a
missing `` `define ``. A build that parses with errors produces an index that
is quietly incomplete.

---

## Cross-references

**`cannot resolve sv:class reference 'x'`**
An explicit, *typed* role that resolved to nothing. Fix it: qualify the name, or
check the object is parsed.

**`... (ambiguous; candidates: a::new, b::new)`**
The bare name is defined in several places. Qualify it —
`my_pkg::my_class::new`.

**A type in a signature is not a link**
Expected and silent. Types are *inferred* references: one that names no
documented object renders as plain text. Built-in types are never looked up.
The same applies to NaturalDocs `<x>`, Doxygen `#x`, and the generic
`:sv:obj:` role, none of which warn. Do not chase these; do not suppress the
typed-role warnings to make them go away.

---

## Missing or wrong content

**Members are missing**
`:members:` is not set (or `sv_default_options` does not set it), or the
members have no doc comment and `:undoc-members:` is not set. Ports,
parameters and coverpoints are always shown; other members are not.

**A class's base class is not linked, or an inheritance diagram is empty**
Base classes must resolve to draw an edge. Parse the whole class set together —
typically a single `sv_build_units` entry rooted at the package that includes
everything.

**Doc comments render as one blob, or a section is not lifted out**
Wrong dialect. Check `sv_doc_style`, try `auto`, or set `:doc-style:` on the
directive. See `comment-styles.md` — NaturalDocs sections must be a header on
its **own line**.

**A native comment produces reST warnings**
The native dialect passes the body through unchanged, so it is the only one
that can emit broken reST. Fix the comment, or let `auto` classify it as plain
prose.

**`sphinx-systemverilog: :files: pattern matched no objects`**
The `autosvsummary` `:files:` glob selected nothing. Remember `*` and `?` stop
at `/` and a relative pattern matches a path *suffix* at a directory boundary:
`reg/*.svh` does not match `reg/sequences/x.svh` — use `reg/**/*.svh`.

**A class vanished from a library split across pages**
It fell between two `:files:` patterns. Compare the parsed index against the
built `objects.inv` in CI so this fails the build instead of disappearing
quietly (this repository does it in `scripts/check-docs-coverage.py`).

---

## Structure (RTL)

**`no instantiation hierarchy for module 'x' (is it a top-level design module?)`**
The module does not participate in an elaborated hierarchy — often because its
package or its parents were not parsed, or because the design elaborated
against the wrong configuration package. For a configurable core, list the
files for **one** configuration in `sv_build_units` rather than globbing the
directory.

**`the elaborated design is not available in this process ... a full rebuild (sphinx-build -E) will restore it`**
The elaborated design cannot live in Sphinx's cached environment, so an
incremental or parallel build can render a page in a process that never walked
it. `sphinx-build -E` restores it.

**`N deeper level(s) containing M instance(s) not shown`**
Not an error — the depth limit reporting itself. Raise `:depth:` or
`sv_instance_tree_depth` if you want more, or leave it: the message is honest
documentation.

**`N further instantiation site(s) not shown of M total`**
The `sv:used-by` cap. Raise `:limit:` or `sv_used_by_limit`; `0` removes it.

**Truncation at the instance ceiling**
`sv_structure_max_instances` (20000) was hit. Prefer narrowing
`sv_structure_tops` to the tops you actually mean over raising the ceiling — a
testbench top that pulls in the whole DUT is usually not the thing you meant to
walk.

**A utility module appears as its own top**
Correct behaviour: a module nothing instantiates is elaborated as a top,
because the elaborator has no other way to reach it. Name the real tops in
`sv_structure_tops`.

**The build is slow**
Parsing is nearly free; the hierarchy walk is not. Check whether a `show-*`
option landed in `sv_default_options`, which pays for elaboration on every
module page.

---

## UVM

**`no run_test("...") call was found in any top module. Name a root explicitly or set sv_uvm_root`**
Auto-detection failed — the top module was not parsed, or `run_test` is called
somewhere unusual. Pass the root as the directive argument or set
`sv_uvm_root`.

**`found no UVM test to document`**
No component derived from the UVM base classes was found. Usually the UVM
library itself, or the testbench package, was not parsed.

**`cannot find UVM component 'x' in the tree rooted at 'y'`**
The component exists but is not reachable from that root — check the root, or
pass `:root:` on `sv:uvm-used-by`.

**`'x' does not derive from uvm_sequence` / `cannot find a UVM sequence named 'x'`**
`sv:uvm-sequence` needs a real sequence class; check the name and that its
package is parsed.

**`has nothing to draw for 'x': its build_phase creates no components`**
Expected for a leaf. Use `:optional:` on shared pages, or point the directive
at a container.

**`the elaborated testbench is not available in this process`**
Same cause and fix as the RTL equivalent: `sphinx-build -E`.

**`[unresolved]` nodes in the tree**
The component's type did not resolve — its package was not parsed. Fix
`conf.py`. This is precisely the case the tool refuses to hide.

**`[opaque]` nodes**
Deliberate: black-boxed by `sv_uvm_blackbox` / `sv_uvm_blackbox_bases`, or the
UVM library itself. Not a problem.

**`uvm_config_db set of 'n_itmes' in X is never read by any get; check the field name for a typo`**
**A testbench bug, not a doc bug.** The set compiles, elaborates and simulates
in silence while the component keeps its default. Fix the testbench. The
converse (`... get of 'x' ... is never set by anything; the default will always
be used`) means a knob that can never be turned. These become build warnings
only when `sv_uvm_warn_orphans = True`; the finding is rendered in the page
either way.

**`found no virtual-interface bindings; a uvm_config_db#(virtual ...)::set is what this table reads`**
Either there are none, or the top module holding them was not parsed. The `set`
that binds a virtual interface usually lives in an `initial` block, outside
every component — make sure that file is in the source set.

**`UVM schematic of 'x': :tier: entry 'y' is ...`**
The `:tier:` entry matched neither an instance handle nor a type name in that
view, or the component is inside an agent cluster (where the cluster's tier
always wins).

---

## Diagrams

**A diagram is missing, with a warning**
Graphviz's `dot` is not on `PATH`. Install it (`apt-get install graphviz`).
Builds do not fail for this.

**The schematic looks plain, with a note underneath**
`dot` is older than 2.30, so `newrank` is unavailable and tier pinning was
dropped. The rest is unchanged.

**`inheritance-diagram target 'x' is not a class`**
Wrong kind of object for that directive.

---

## Configuration

**`sv_uvm_tree_depth must be an integer >= 1, not 'x'; falling back to 4`**
A bad config value degrades to the default with a warning rather than failing —
so build with `-W` if you want typos in `conf.py` to be caught.

**`sv_doc_style 'x' is not one of native, naturaldocs, doxygen, auto`**
Falls back to `native`.

**Pygments highlighting failures on UVM sources**
The SystemVerilog lexer cannot tokenize a compiler-directive backtick in every
position UVM uses one. That is a Pygments limitation, not a content problem:
`suppress_warnings = ["misc.highlighting_failure"]` is the right response, and
it is narrower than suppressing `systemverilog` warnings.
