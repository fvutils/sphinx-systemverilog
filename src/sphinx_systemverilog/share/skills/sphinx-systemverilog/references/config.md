# Configuration reference

Every `sv_*` value the extension registers, plus the Sphinx settings that
interact with this domain. All are set in `conf.py`. Published version:
<https://dvkit.org/fvutils/sphinx-systemverilog/getting-started.html>

---

## Sources and parsing

| Value | Default | Type | Meaning |
|---|---|---|---|
| `sv_source_dirs` | `[]` | list | Directories scanned recursively for `.sv`/`.svh`. Relative paths resolve against `conf.py`'s directory. |
| `sv_include_dirs` | `[]` | list | Additional `+incdir` paths for the preprocessor. |
| `sv_defines` | `{}` | dict | Preprocessor `` `define `` values (name → value) applied during elaboration. |
| `sv_build_units` | `[]` | list | Explicit root files to parse, instead of (or as well as) scanning directories. |
| `sv_doc_style` | `"native"` | str | Default comment dialect: `native`, `naturaldocs`, `doxygen`, `auto`. An invalid value warns and falls back to `native`. |
| `sv_naturaldocs_nodocs` | `"include"` | str | UVM `-- NODOCS --` blocks: `include` the prose (marker stripped) or `skip` the block. |
| `sv_document_macros` | `True` | bool | Extract and document `` `define `` macros. Include guards are extracted like any other macro; narrow with `:exclude:` or a glob. |

### `sv_source_dirs` versus `sv_build_units`

Use `sv_build_units` when the tree contains **mutually exclusive configuration
packages**, or when a library is rooted at one include-everything file:

```python
sv_build_units = ["../rtl/core/cv64a6_imafdc_sv39_config_pkg.sv", ...]
sv_include_dirs = ["../rtl/core/include", "../vendor/common_cells/include"]
```

Globbing such a directory parses every configuration at once, elaboration hits
conflicting definitions, and the hierarchy comes out incomplete — with no error
that says so. The two settings combine: files listed in `sv_build_units` are
parsed into the same index as everything scanned from `sv_source_dirs`.

---

## Output and defaults

| Value | Default | Type | Meaning |
|---|---|---|---|
| `sv_default_options` | `{}` | dict | Options applied to every `auto*` directive, e.g. `{"members": True}`. |
| `sv_viewcode` | `True` | bool | Generate highlighted source listings and `[source]` links. |

`sv_default_options` takes the option names without colons; flags take `True`.
Directive-level options override it.

```python
sv_default_options = {"members": True, "undoc-members": True}
```

Putting `show-instances`, `show-used-by` or `show-parameters-used` here turns on
hierarchy elaboration for **every** module page. That is a legitimate choice,
but it is a project-wide cost decision — make it deliberately, and write down
why.

---

## RTL structure (all lazy)

Consulted only when a structural directive actually asks for the hierarchy.

| Value | Default | Type | Meaning |
|---|---|---|---|
| `sv_structure_tops` | `[]` | list | Restrict the hierarchy walk to these top modules. Empty = every elaborated top. |
| `sv_structure_max_instances` | `20000` | int (≥1) | Ceiling on instances visited. Exceeding it renders what was walked and warns about truncation. |
| `sv_instance_tree_depth` | `3` | int (≥1) | Default `:depth:` for `sv:instance-tree`. |
| `sv_used_by_limit` | `50` | int (≥0) | Default `:limit:` for `sv:used-by`; `0` disables the cap. |

Prefer narrowing `sv_structure_tops` over raising
`sv_structure_max_instances`: a module nothing instantiates is elaborated as
its own top, so an unused utility module appears next to your real design top,
and a testbench top that drags in the whole DUT is usually not what you meant.

---

## UVM testbench (all lazy)

| Value | Default | Type | Meaning |
|---|---|---|---|
| `sv_uvm_root` | `""` | str | Root component type to elaborate from. Empty auto-detects from the `run_test("...")` argument in a top module. |
| `sv_uvm_blackbox` | `[]` | list | Glob patterns matched against a component's **type name**. Matches render as `[opaque]` nodes — present, named, counted, not walked into. |
| `sv_uvm_blackbox_bases` | `["uvm_reg_block"]` | list | As above, but matched against the whole base-class chain, so one entry covers a family. |
| `sv_uvm_tree_depth` | `4` | int (≥1) | Default `:depth:` for `sv:uvm-tree` (`test → env → agent → driver` is 4). |
| `sv_uvm_max_components` | `5000` | int (≥1) | Ceiling on components visited; exceeding it reports truncation rather than hanging the build. |
| `sv_uvm_warn_orphans` | `False` | bool | Also emit build warnings for orphaned `config_db` fields. The finding is always rendered in the page regardless. |

```python
sv_uvm_blackbox = ["*_reg_block", "acme_vip_*"]
sv_uvm_blackbox_bases = ["uvm_reg_block"]
```

The UVM library's own internals are always stopped at, with no configuration.

Turn `sv_uvm_warn_orphans` on only as a project decision: it makes a testbench
smell fail a `-W` build, which is valuable *and* is not something installing a
documentation extension should do to you by default.

---

## Validation

`sv_structure_max_instances`, `sv_instance_tree_depth`, `sv_used_by_limit`,
`sv_uvm_tree_depth` and `sv_uvm_max_components` are checked at `config-inited`:
a non-integer, a bool, or a value below the floor (1, or 0 for
`sv_used_by_limit`) warns and falls back to the default. `sv_doc_style` is
checked against the four dialect names.

So a typo here degrades to the default with a warning rather than failing —
which means a `-W` build is what actually catches it.

---

## Sphinx settings that interact

| Setting | Why it matters here |
|---|---|
| `extensions` | Must list `"sphinx_systemverilog"`. `sphinx.ext.graphviz` is set up automatically. Add `"myst_parser"` for Markdown pages. |
| `toc_object_entries` | `False` suppresses documented objects in the sidebar. |
| `toc_object_entries_show_parents` | `domain` (default) → `sig_ops::seed()`; `hide` → `seed()`; `all` → `sig_pkg::sig_ops::seed()`. |
| `add_function_parentheses` | `False` drops `()` from function/task TOC entries. |
| `intersphinx_mapping` | Lets other projects reference this one's objects (`` :sv:class:`mylib:pkg::cls` ``). |
| `suppress_warnings` | Pygments cannot always tokenize compiler-directive backticks in UVM sources; `["misc.highlighting_failure"]` keeps that out of a `-W` build. Do **not** reach for this to silence `systemverilog`-type warnings. |
| `nitpicky` / `-W` | Recommended for a doc set that must stay honest — but read `troubleshooting.md` first for which warnings are real. |

---

## A worked `conf.py`

```python
import os

extensions = ["myst_parser", "sphinx_systemverilog"]

_here = os.path.dirname(__file__)
_rtl = os.path.abspath(os.path.join(_here, "..", "rtl"))

sv_source_dirs = [os.path.join(_rtl, "ip")]
sv_build_units = [os.path.join(_rtl, "top", "soc_config_pkg.sv")]
sv_include_dirs = [os.path.join(_rtl, "include")]
sv_doc_style = "auto"

sv_default_options = {"members": True}
sv_structure_tops = ["soc_top"]

# UVM testbench
sv_uvm_blackbox = ["acme_vip_*"]        # vendor VIP, precompiled
# sv_uvm_blackbox_bases defaults to ["uvm_reg_block"] - covers a generated RAL

myst_enable_extensions = ["colon_fence", "deflist"]
```
