# Design structure

A module's own declaration is the least interesting thing you can say about it.
Its ports and parameters are right there in the source; what an engineer
actually wants to know is *who instantiates this, with what parameters, and what
is it built from*. None of that exists in any single file — it exists only in
the **elaborated** design.

Three directives expose it:

| Directive | Answers |
|---|---|
| `sv:instance-tree` | What is this module built from? |
| `sv:used-by` | What uses this module, and can I change it? |
| `sv:parameter-matrix` | Which parameter values is it actually used at? |

All three are also available as options on `autosvmodule`
(`:show-instances:`, `:show-used-by:`, `:show-parameters-used:`).

> **None of them is on by default.** Each triggers a walk of the elaborated
> hierarchy, which is the most expensive thing this extension does. See
> [Elaboration cost](elaboration-cost).

## Instance tree

```rst
.. sv:instance-tree:: soc
```

```text
soc
├── u_narrow : cluster #(W=8, WIDE=1'b0)
│   └── g_narrow.u_leaf : leaf #(W=8)
└── u_wide   : cluster #(W=32, WIDE=1'b1)
    └── g_wide.u_lane : lane #(W=32, LANES=4)
        ├── g_lp[*].u_g : leaf #(W=32)   (×4)
        └── u_l[3:0]    : leaf #(W=32)   (×4)
```

Every type name is a cross-reference to that module's documentation.

### Why text rather than a picture

Text is the default deliberately. It stays readable at depth where a graph
becomes a hairball, it needs no Graphviz installed, Sphinx's full-text search
indexes it, it diffs cleanly in review, and each type name can be a link. Pass
`:diagram:` for the Graphviz view where a picture genuinely helps — usually a
shallow, top-level structural overview.

### Reading the tree

- `g_lp[*].u_g` — an instance inside a generate loop. The `[*]` marks it as one
  line of source that elaborated several times; the `(×4)` says how many.
- `u_l[3:0]` — an instance array, likewise one line producing four instances.
- `#(W=32)` — the **elaborated** parameter values. If the source says
  `#(.W(BUS_W))`, the tree shows what `W` actually became.
- `#(Cfg=cva6_cfg_t)` — a parameter whose value is a struct or a wide packed
  type is shown **by type**, not by value. A configuration struct elaborates to
  a single enormous integer (CVA6's is 17268 bits), which would bury every
  other value on the line. Two different configurations remain two different
  elaborations, and the parameter matrix numbers them (`cva6_cfg_t #1`,
  `cva6_cfg_t #2`) rather than merging them.
- Each branch shows the body of *that* elaboration. A module instantiated twice
  with different parameters can have genuinely different children — an
  if-generate branching on a parameter is the common case — and the tree shows
  each as it really elaborated rather than the union of both.

### Options

| Option | Meaning |
|---|---|
| `:depth: N` | Levels to show. Default `sv_instance_tree_depth` (3). |
| `:collapse:` | Fold structurally identical siblings onto one line. |
| `:diagram:` | Render as a Graphviz graph instead of text. |
| `:optional:` | Render nothing, silently, if there is nothing to show. |

A real SoC hierarchy is thousands of nodes, so the depth limit exists to keep
the page useful. What it hides is always reported:

```text
2 deeper level(s) containing 10 instance(s) not shown — raise :depth: (currently 1).
```

With `:collapse:`, siblings that share a type, parameterization and generate
path fold onto one line and are **named**, not just counted:

```text
cl_top
└── u_m1, u_m2 : cl_mid #(W=8)   (×2)
    ├── u_a, u_b, u_c : cl_leaf #(W=8)   (×3)
    └── u_wide        : cl_leaf #(W=64)
```

Note that `u_wide` did not fold in with the others: it differs by parameter, and
that is exactly the kind of difference you want the tree to keep.

(instantiated-by)=
## Instantiated by

The reverse map — for a module, every site that instantiates it:

```rst
.. sv:used-by:: leaf
```

Each entry gives the full hierarchical path, the parent module (linked), the
parameter values at that site, and a `[source]` link to the instantiation line.

This is the highest-value view per line of code, and it is impossible for any
file-at-a-time documentation tool to produce: the information does not exist in
`leaf.sv`.

| Option | Meaning |
|---|---|
| `:limit: N` | Sites to list. Default `sv_used_by_limit` (50); `0` for no cap. |
| `:optional:` | Render nothing, silently, if there is nothing to show. |

A heavily reused leaf module can have hundreds of instantiation sites, which
would bury its own documentation. The cap exists for that, and what it hid is
always stated:

```text
5 further instantiation site(s) not shown of 8 total — raise :limit: or sv_used_by_limit.
```

(parameter-matrix)=
## Parameter matrix

Which values a module is actually used at, across the whole design:

```rst
.. sv:parameter-matrix:: leaf
```

| Parameter | Value | Instances | Example site |
|---|---|---|---|
| `W` | `32` | 5 | `soc.u_wide.g_wide.u_lane.g_lp[0].u_g` |
| | `8` | 1 | `soc.u_narrow.g_narrow.u_leaf` |

This is distinct from the parameter's declared default, and that distinction is
the point: a default tells you what happens if nobody overrides it, while this
tells you what the design does. It answers questions like "is anyone still using
the 8-bit configuration?" and "if I change this default, what breaks?"

## A note on scope

Every one of these views is derived from the sources this project parses, and
each says so. "Not instantiated **within the documented sources**" is not the
same claim as "unused" — for a reusable IP block, the instantiations that matter
may well live in a design you are not documenting here.

If a module you expect to see is missing, widen `sv_source_dirs` or
`sv_build_units` rather than assuming the design is what you see.

Two consequences worth knowing:

**A module that nothing instantiates is elaborated as its own top.** That is
correct — the elaborator has no other way to reach it — but it means a utility
module unused in the configuration you built will appear alongside your real
design top. Use `sv_structure_tops` to name the tops you mean.

**For a real design, pointing `sv_source_dirs` at a directory is often not
enough.** Configurable cores commonly ship several mutually exclusive
configuration packages — CVA6 has ten `*_config_pkg.sv` files, one per target —
and globbing the directory parses all of them, so elaboration picks up
conflicting definitions and the hierarchy comes out incomplete. List the files
for the configuration you are documenting via `sv_build_units` instead:

```python
sv_build_units = [...]      # the files for one configuration
sv_include_dirs = ["core/include", "vendor/common_cells/include"]
```

## On an `autosvmodule` page

```rst
.. autosvmodule:: lane
   :members:
   :show-instances:
   :show-used-by:
   :show-parameters-used:
```

Each option adds its section under a heading. To turn them on across a whole
project, put them in `sv_default_options` — that is an explicit choice to pay
for elaboration on every module page, so make it deliberately.

```python
sv_default_options = {"show-used-by": True}
```
