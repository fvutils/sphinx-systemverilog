# Directive, role and field reference

Everything the `sv` domain and the autodoc layer register. Published version:
<https://dvkit.org/fvutils/sphinx-systemverilog/usage/directives.html>

RST spelling is shown throughout. In MyST Markdown pages, use an
`` ```{eval-rst} `` block or the MyST directive syntax:

````markdown
```{eval-rst}
.. autosvclass:: my_pkg::my_transaction
   :members:
```
````

---

## 1. Autodoc directives

| Directive | Documents | Argument |
|---|---|---|
| `autosvpackage` | a package and its contents | qualified name |
| `autosvclass` | a class, its inheritance and members | qualified name |
| `autosvmodule` | a module or interface, its parameters and ports | name |
| `autosvfunction` | one function | name |
| `autosvtask` | one task | name |
| `autosvsummary` | a whole subtree of the index | optional glob |

Names may be qualified (`my_pkg::my_class`) or bare when unambiguous.

### Options shared by the five single-object directives

| Option | Value | Meaning |
|---|---|---|
| `:members:` | none, or a name list | Document members. No value = all documented members. |
| `:undoc-members:` | flag | Also include members with no doc comment. |
| `:inherited-members:` | flag | (classes) Also document members inherited from base classes, grouped under an "Inherited from `base`" rubric per base, walking the whole chain. A member redeclared locally is not repeated. |
| `:exclude-members:` | name list | Names to skip (comma or space separated). |
| `:member-order:` | `source` \| `alpha` \| `groups` | Order of members. Default `source`. `groups` honours NaturalDocs `Group:` headers. |
| `:doc-style:` | dialect name | Override the comment dialect for this directive. |
| `:show-inheritance:` | flag | (classes) Add an inheritance diagram. |
| `:show-instances:` | flag | (modules) Add the instance tree. |
| `:show-used-by:` | flag | (modules) Add the instantiation-site list. |
| `:show-parameters-used:` | flag | (modules) Add the parameter matrix. |
| `:optional:` | flag | Render nothing, and warn about nothing, when the target is not in the index. |

`:recursive:` is accepted by the parser for forward compatibility but currently
has no effect — do not rely on it.

The three `:show-*:` options each trigger a walk of the elaborated design. They
are off by default for that reason. See `config.md` on `sv_default_options`.

Ports, parameters and coverpoints are treated as public interface and are shown
even when undocumented — unlike other members, which need `:undoc-members:`.
`:member-order: groups` sorts by group name (NaturalDocs `Group:` headers),
then by source line.

### `autosvsummary`

Documents everything in scope, in one directive — the analog of a
Doxygen/Exhale full-API page.

```rst
.. autosvsummary::                 # everything parsed
.. autosvsummary:: axi_*           # top-level names matching a glob
```

| Option | Effect |
|---|---|
| *argument* | glob on top-level names |
| `:packages:` | restrict to objects in the named packages |
| `:kinds:` | only these kinds (`class`, `module`, `package`, `macro`, …) |
| `:files:` | restrict to declarations from source files matching a path glob |
| `:exclude:` | drop named objects |
| `:members:` / `:undoc-members:` / `:member-order:` | as above |
| `:doc-style:` | dialect override |
| `:optional:` | render nothing, silently, when the scope selects nothing |

**`:files:` glob semantics** (chosen so two pages cannot silently overlap):

| Pattern | Matches |
|---|---|
| `reg/*.svh` | files directly in any `reg/` directory — **not** `reg/sequences/x.svh` |
| `reg/**/*.svh` | `reg/` and everything below it |
| `uvm_reg.svh` | that basename, anywhere |
| `/abs/src/reg/*.svh` | leading `/` anchors to the absolute path |

`*` and `?` stop at `/`; `**` crosses directories; a relative pattern matches a
path *suffix* at a directory boundary, so pages are machine-independent.

This is how to split a large library across pages without a hand-maintained
class list. Verify nothing fell between two patterns (see
`troubleshooting.md`).

---

## 2. Manual domain (object) directives

Fifteen object directives, all in the `sv` domain. Autodoc emits these; write
them by hand when you want full control or are documenting something not in the
sources.

`sv:package`, `sv:module`, `sv:interface`, `sv:program`, `sv:class`,
`sv:function`, `sv:task`, `sv:property`, `sv:port`, `sv:parameter`,
`sv:typedef`, `sv:macro`, `sv:covergroup`, `sv:coverpoint`, `sv:constraint`

```rst
.. sv:class:: my_transaction
   :module: my_pkg
   :extends: uvm_sequence_item
   :virtual:

   A bus transaction.

   .. sv:function:: function bit parity(bit[31:0] mask)

      Compute the parity of the payload.

      :param mask: bits to include
      :returns: the parity bit
```

### Options

| Option | Meaning |
|---|---|
| `:module:` | Enclosing package/module, used for the qualified name. |
| `:extends:` | Base class; rendered and cross-linked. |
| `:virtual:` | Flag; renders the `virtual` qualifier. |
| `:qualifiers:` | Free-text qualifier list (`static`, `protected`, …). |
| `:source:` | Source reference for the `[source]` link. |
| `:uvm:` | UVM kind badge (`component`, `sequence`, `sequence item`, `TLM port`, `object`). Autodoc derives it from the base-class chain. |
| `:phases:` | UVM phase methods the class overrides, in execution order. |
| `:no-index:` | Do not add to the index or make referenceable. |
| `:no-index-entry:` | Referenceable, but no general-index entry. |

### Doc fields

Recognised inside any object directive's body, and produced by all three
comment dialects:

| Field names | Renders as |
|---|---|
| `:param:` / `:parameter:` / `:arg:` / `:argument:` | Parameters (typed, collapsible) |
| `:paramtype:` / `:type:` | the type of a parameter |
| `:returns:` / `:return:` | Returns |
| `:rtype:` | Return type |
| `:throws:` / `:throw:` / `:exception:` | Throws |
| `:see:` / `:seealso:` | See also |

### How signatures render

Signature text is parsed in the domain, so hand-written and autodoc-emitted
directives render identically: kind label, qualifiers, return type, name, and a
real `desc_parameterlist` with one entry per argument (direction, type, name,
unpacked dimensions, default value). Arguments split only at bracket depth zero
and outside string literals, so `int vals[$] = '{1, 2}` is one argument.

Unpacked dimensions bind to the declarator: `ref int q[$]` renders as `q[$]` but
is indexed and referenced as `q`.

Types in a signature that name a documented object are linked automatically —
return types, argument types, property types, and the `extends` base. Built-in
types (`int`, `bit`, `logic`, `string`, `void`, …) are styled as keywords and
never looked up. An unparseable signature falls back to rendering the argument
text opaquely; it never fails a build.

---

## 3. Structural directives (RTL)

Derived from the **elaborated** design. Each triggers the hierarchy walk; the
first one in a build pays for it and every later one reuses it.

```rst
.. sv:instance-tree:: soc
   :depth: 2
   :collapse:
```

| Directive | Argument | Options |
|---|---|---|
| `sv:instance-tree` | module | `:depth: N` (default `sv_instance_tree_depth`, 3), `:collapse:`, `:diagram:`, `:optional:` |
| `sv:used-by` | module | `:limit: N` (default `sv_used_by_limit`, 50; `0` = no cap), `:optional:` |
| `sv:parameter-matrix` | module | `:optional:` |
| `sv:instance-diagram` | module | *(none)* |
| `sv:inheritance-diagram` | class | `:optional:` |

Reading an instance tree:

```text
soc
├── u_narrow : cluster #(W=8, WIDE=1'b0)
│   └── g_narrow.u_leaf : leaf #(W=8)
└── u_wide   : cluster #(W=32, WIDE=1'b1)
    └── g_wide.u_lane : lane #(W=32, LANES=4)
        ├── g_lp[*].u_g : leaf #(W=32)   (×4)
        └── u_l[3:0]    : leaf #(W=32)   (×4)
```

- `g_lp[*].u_g` — inside a generate loop; `(×4)` is how many elaborated.
- `u_l[3:0]` — an instance array.
- `#(W=32)` — the **elaborated** value, not the source expression.
- `#(Cfg=cva6_cfg_t)` — struct/wide-packed parameters are shown by type, and
  distinct configurations are numbered (`cva6_cfg_t #1`) rather than merged.
- Each branch shows the body of *that* elaboration; an if-generate branching on
  a parameter genuinely gives a module different children per parameterisation.
- `:collapse:` folds siblings that share type, parameters and generate path,
  and **names** them (`u_m1, u_m2 : cl_mid #(W=8) (×2)`).
- Untaken if-generate branches are not part of the design and are not drawn.

`sv:used-by` lists each site's hierarchical path, parent module (linked),
parameter values and a `[source]` link. `sv:parameter-matrix` gives, per
parameter, each distinct elaborated value, an instance count and an example
site — which is a different question from the declared default.

Scope caveat to keep in the text you write: these views cover *the sources this
project parses*. "Not instantiated within the documented sources" is not
"unused". A module nothing instantiates is elaborated as its own top; use
`sv_structure_tops` to name the tops you mean.

---

## 4. UVM directives

Derived from `build_phase`/`connect_phase`/`body()` — see `uvm.md` for
semantics, caveats and findings.

| Directive | Argument | Options |
|---|---|---|
| `sv:uvm-tree` | optional component (default: auto-detected root) | `:depth: N` (default `sv_uvm_tree_depth`, 4), `:collapse:`, `:optional:` |
| `sv:uvm-config` | optional glob on the setting component | `:orphans:`, `:optional:` |
| `sv:uvm-schematic` | optional container (default: auto-detected, descended to the first env) | `:tier: name=top\|middle\|bottom, …`, `:order: handle, handle, …`, `:optional:` |
| `sv:uvm-sequence` | **required** sequence name | `:depth: N` (sub-sequence expansion, default 1), `:optional:` |
| `sv:uvm-binding` | optional glob on the interface type | `:optional:` |
| `sv:uvm-used-by` | **required** component | `:root:` (root the search at a named test), `:optional:` |

Root auto-detection reads the `run_test("...")` argument in a top module. With
several testbenches in one project, one is shown and the others are named
beneath — name the root explicitly to be deterministic.

---

## 5. Cross-reference roles

```rst
See :sv:class:`my_pkg::my_transaction` and :sv:func:`my_pkg::parity`.
```

| Role | Targets |
|---|---|
| `:sv:class:` | classes |
| `:sv:type:` | classes, typedefs |
| `:sv:mod:` / `:sv:module:` | modules |
| `:sv:interface:` / `:sv:program:` | interfaces / programs |
| `:sv:package:` | packages |
| `:sv:func:` / `:sv:function:` | functions |
| `:sv:task:` | tasks |
| `:sv:prop:` / `:sv:property:` | class properties |
| `:sv:port:` / `:sv:param:` / `:sv:parameter:` | ports / parameters |
| `:sv:typedef:` / `:sv:macro:` | typedefs / macros |
| `:sv:covergroup:` / `:sv:coverpoint:` / `:sv:constraint:` | coverage and constraint objects |
| `:sv:obj:` | any object — also the target of NaturalDocs `<x>` and Doxygen `#x` |

Qualified and unambiguous bare names both resolve; ambiguous bare names do not.
Unresolved **explicit** roles warn; inferred references degrade silently.

Objects are exported to `objects.inv`, so other projects can reference them via
intersphinx: `` :sv:class:`mylib:my_pkg::my_transaction` ``.

---

## 6. Table of contents and source links

Documented objects become TOC entries, nested under their container. Controlled
by Sphinx's own settings: `toc_object_entries`,
`toc_object_entries_show_parents` (`domain` shows `sig_ops::seed()`, `hide`
shows `seed()`, `all` shows `sig_pkg::sig_ops::seed()`), and
`add_function_parentheses`.

With `sv_viewcode = True` (default) every object gets a `[source]` link to a
generated highlighted listing anchored at its declaration line.

---

## 7. Extension events

Mirroring `sphinx.ext.autodoc`, for projects that need to filter or rewrite:

- `sv-autodoc-process-doc`
- `sv-autodoc-skip-member`
