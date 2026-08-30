---
name: sphinx-systemverilog
description: Write Sphinx documentation for SystemVerilog and UVM source with the sphinx-systemverilog extension - conf.py setup (sv_source_dirs, sv_build_units, sv_doc_style), the autosvclass/autosvmodule/autosvsummary directives, the sv domain directives and roles, RTL structure views (instance tree, used-by, parameter matrix, instance diagram), UVM testbench views (component tree, config_db table, schematic, sequence activity diagram, virtual-interface bindings, factory overrides), the native/NaturalDocs/Doxygen doc-comment dialects, and diagnosing SystemVerilog documentation build warnings. Use when a Sphinx project lists sphinx_systemverilog in extensions, when a page contains an autosv* or sv: directive, or when asked to document SystemVerilog, RTL or UVM source with Sphinx.
---

# sphinx-systemverilog

A Sphinx autodoc extension for SystemVerilog, powered by the `pyslang` parser.
It documents SystemVerilog the way `sphinx.ext.autodoc` documents Python:
declarations and their doc comments come straight from source.

## The model: parse wide, reference narrow

Sources are parsed **once per build** into a project-wide index. Every
directive then resolves names against that one index. Consequences worth
internalising before writing anything:

- Do not add sources per page. Configure the whole source set once in
  `conf.py`; a page names *objects*, never files.
- A cross-file base class, a type in a signature, an interface bound to a
  testbench — all resolve only if both ends were parsed into the same index.
- Parsing is nearly free. **Walking the elaborated hierarchy is not**, which is
  why every structural and UVM view is opt-in.

## Setting up conf.py

```python
extensions = ["sphinx_systemverilog"]      # add "myst_parser" for .md pages

sv_source_dirs = ["../rtl", "../verif"]    # recursively scanned for .sv/.svh
sv_include_dirs = ["../rtl/include"]       # +incdir paths
sv_doc_style = "auto"                      # native | naturaldocs | doxygen | auto
```

Checklist, in order:

1. **Pick `sv_source_dirs` or `sv_build_units`.** Directory scanning is right
   for a self-contained tree. Use `sv_build_units` — an explicit list of root
   files — whenever the tree holds **mutually exclusive configuration
   packages** (CVA6 ships ten `*_config_pkg.sv` files, one per target) or a
   library rooted at a single include-everything file (`uvm_pkg.sv`). Globbing
   such a directory parses conflicting definitions and the hierarchy comes out
   silently incomplete. Both settings may be used together.
2. **Pick a dialect.** `native` for new code, `naturaldocs` for UVM-style code,
   `doxygen` for `@brief`-style code, `auto` to sniff per comment. `auto` is
   right for a mixed tree. See `references/comment-styles.md`.
3. **Do not put `show-*` options in `sv_default_options`** unless you mean to
   pay for hierarchy elaboration on every module page.
4. **Install Graphviz** (`dot` on `PATH`) only if you want diagrams. Without
   it, builds still pass; diagrams are skipped with a warning.

Full list of the 19 `sv_*` values: `references/config.md`.

## Choosing a directive

| You want to document | Use |
|---|---|
| a package, class, module, function or task | `autosvpackage`, `autosvclass`, `autosvmodule`, `autosvfunction`, `autosvtask` |
| a whole library or a slice of one | `autosvsummary` (glob argument, `:packages:`, `:kinds:`, `:files:`) |
| one declaration, written by hand | `sv:class::`, `sv:module::`, `sv:function::`, … (15 object directives) |
| what an RTL module is built from / used by / parameterised at | `sv:instance-tree`, `sv:used-by`, `sv:parameter-matrix` |
| a class hierarchy or module graph as a picture | `sv:inheritance-diagram`, `sv:instance-diagram` |
| a UVM testbench | `sv:uvm-tree`, `sv:uvm-config`, `sv:uvm-schematic`, `sv:uvm-sequence`, `sv:uvm-binding`, `sv:uvm-used-by` |
| a reference to any of the above | `:sv:class:`, `:sv:mod:`, `:sv:func:`, `:sv:obj:`, … |

```rst
.. autosvclass:: my_pkg::my_transaction
   :members:
   :show-inheritance:
```

Every option of every directive: `references/directives.md`.

## Documenting RTL structure

A module's declaration is the least interesting thing about it — its ports are
right there in the source. What only the **elaborated** design knows:

```rst
.. autosvmodule:: lane
   :members:
   :show-instances:          .. what it is built from
   :show-used-by:            .. every site that instantiates it
   :show-parameters-used:    .. the values it is really elaborated at
```

The same three views exist as standalone directives (`sv:instance-tree`,
`sv:used-by`, `sv:parameter-matrix`) for pages that are not a module page.

Prefer the **text** instance tree over `:diagram:`: it stays readable at depth,
needs no Graphviz, is full-text searchable, diffs cleanly, and every type name
in it is a cross-reference. Reach for the diagram only for a shallow top-level
overview.

Truncation is always reported, never silent ("2 deeper level(s) … not shown").
When you see that, raise `:depth:`/`:limit:` deliberately — or leave it, since
the message itself is honest documentation.

## Documenting a UVM testbench

> The single most important fact: a UVM hierarchy is **a reading of
> `build_phase`**, not a simulation trace. There is no elaborated
> `tb_top.env.agt.drv` anywhere. Factory overrides, conditional builds and
> loop-built components are *annotated*, never resolved.

```rst
.. sv:uvm-tree::                  .. root auto-detected from run_test("...")
.. sv:uvm-config::                .. every config_db set/get, and the orphans
.. sv:uvm-schematic:: my_env      .. one level of wiring, agents as clusters
.. sv:uvm-sequence:: main_seq     .. one body() as a UML activity diagram
.. sv:uvm-binding::               .. virtual interface: RTL instance -> component
.. sv:uvm-used-by:: my_agent      .. who builds this component
```

Node annotations you must read literally: `[conditional]`, `(×N)`, `[opaque]`
(a black-boxed boundary — present, not walked into), `[unresolved]` (the type
did not resolve; its package was probably not parsed), and
`[overridden → other_type]`.

`autosvclass` additionally renders, on a component's own page, a UVM kind badge
(`component`, `sequence`, `sequence item`, `TLM port`, `object`) and the list of
phase methods the class itself overrides.

Two findings this produces are testbench bugs, not doc bugs: an orphaned
`config_db` field (a typo in a field-name string that compiles and simulates
happily) and a virtual interface bound to nothing. Report them; do not silence
them. Details, options and caveats: `references/uvm.md`.

## Writing doc comments in the source

The doc comment is the contiguous comment block immediately above a
declaration; a trailing `// …` on the same line documents that declaration.

```systemverilog
// Compute the parity of the data payload.
//
// :param mask: bits to include in the calculation
// :returns: the computed parity bit
function bit parity(bit [31:0] mask);
```

That is the `native` dialect — the body **is** reStructuredText. Under
NaturalDocs use `Function: name` headers, `Parameters:` sections, `<symbol>`
and `~code~`; under Doxygen use `@brief`, `@param`, `@return`. One example of
each, plus the `auto` detection rule: `references/comment-styles.md`.

## Rules that are easy to get wrong

1. **`sv_build_units` for anything configurable.** See the checklist above. A
   wrong choice here produces a doc set that looks complete and is not.
2. **Structural and UVM views cost; declarations do not.** Nothing walks a
   hierarchy or a `build_phase` unless a directive on some page asks for it.
   Asking once per build is free thereafter; asking in `sv_default_options` is
   a project-wide decision.
3. **Two kinds of unresolved reference.** An explicit **typed** role
   (`` :sv:class:`x` ``) that resolves to nothing **warns** — fix or qualify
   it. A reference *inferred* from a signature type, a NaturalDocs `<x>` or a
   Doxygen `#x` — and the deliberately untyped `` :sv:obj:`x` `` — degrades to
   plain text **silently**, which is normal. Never suppress the first kind;
   never chase the second.
4. **Qualify ambiguous names.** `new` is defined by every class and resolves in
   no project; write `my_pkg::my_class::new`.
5. **A UVM tree reports, it does not resolve.** Do not "fix" a tree by
   substituting an override's target type.
6. **`:optional:` is for pages that must render identically with or without a
   source set** (a vendor library, a generated register model). It suppresses
   the *warning*, not a real problem — do not sprinkle it to quieten a build.

## Verifying your work

```bash
sphinx-build -b html docs docs/_build/html      # normal build
sphinx-build -E -b html docs docs/_build/html   # full rebuild: rebuilds the
                                                # elaborated design too
sphinx-build -W ...                             # warnings become errors
```

Read the `indexed N SystemVerilog object(s)` line: if `N` is far below what the
tree holds, the source configuration is wrong, not the pages. For a generated
reference split across pages, check that nothing fell between two `:files:`
globs by comparing the parsed index against the built `objects.inv` (this
repository does it in `scripts/check-docs-coverage.py`).

## Reference files

| File | Covers |
|---|---|
| `references/directives.md` | Every directive, argument and option: `auto*`, `autosvsummary` scoping, the 15 `sv:` object directives, structure, diagrams, UVM, roles, doc fields. |
| `references/config.md` | All 19 `sv_*` config values with defaults, plus the Sphinx settings that interact with this domain. |
| `references/comment-styles.md` | `native`, `naturaldocs`, `doxygen` and `auto`, with rules and examples. |
| `references/uvm.md` | The six UVM views in depth: node states, black-boxing, orphan pairing, tiers, sequence notation, factory overrides. |
| `references/troubleshooting.md` | Build symptom → cause → fix. |

Canonical published documentation: <https://dvkit.org/fvutils/sphinx-systemverilog/>
