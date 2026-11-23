(uvm-tree-export)=
# Exporting the UVM component tree

`svdb uvm-tree` works out the component tree a UVM simulation would build,
from one or more [databases](database.md), and writes it as JSON, an indented
text tree or a Graphviz graph. Factory overrides are **applied**: each
component has the type the factory would create, with the override that put
it there. Connections are resolved to full instance paths. Sphinx is not
involved, so the export also works in a script or a CI job.

By default `sv:uvm-tree` draws the tree as written, with overrides shown as
notes beside the declared types ([UVM testbenches](uvm-testbench.md)). This
export applies them instead: it answers "what would be built" rather than
"what does the source say". `sv:uvm-tree` with
[`:resolved:`](uvm-tree-resolved) draws the same tree on a page.

```text
svdb build --sphinx-conf docs/conf.py -o tb.svdb
svdb uvm-tree -d tb.svdb --format text
svdb uvm-tree -d tb.svdb -d vip.svdb --root my_test -o tree.json
```

| Option | Meaning |
|---|---|
| `-d FILE` | A database; repeat to stitch several (see [below](uvm-tree-several)). |
| `--root TYPE` | The test class, qualified (`tb_pkg::my_test`) or bare. The default is the one `run_test` names (the database's `uvm.root` record). |
| `--name NAME` | The root's instance name (default `uvm_test_top`). Inst-override paths are matched against names built from it. |
| `--format` | `json` (flat, the default), `nested` (JSON with `children` arrays), `text` or `dot`. |
| `--no-conditional` | Leave out components and connections that sit under an `if`, and overrides registered under one. |
| `--max-nodes N` | Stop after N components (default 5000). |
| `-o FILE` | Write to a file rather than standard output. |

The exit status is non-zero only when the tree cannot be built (no root, an
unreadable database). Problems found while building it are listed in the
output under `issues`.

## An example

```text
$ svdb uvm-tree -d tb.svdb --format text
uvm_test_top : st_test
├── a_cfg : a_cfg_comp
├── b_agent : st_agent
│   ├── drv : slow_drv <- st_drv  [conditional]
│   ├── mon : mon_c <- st_mon
│   └── seqr : top_seqr <- st_seqr  [conditional]
└── env : sup_env
    ├── agt_a : st_agent
    │   ├── drv : slow_drv <- st_drv  [conditional]
    ...
    └── scb : big_scb <- st_scb

links:
  env.agt_a.mon.ap -> env.scb.exp  (analysis)
  ...

overrides:
  st_drv -> fast_drv (type): applied
  st_mon -> mon_x (inst at b_agent.mon): unused
  ...

issues:
  unplaced_override: stitch_tb_pkg::st_scb -> stitch_tb_pkg::st_scb in stitch_tb_pkg::st_test.run_phase is not reached from any build_phase or constructor in this tree
```

`drv : slow_drv <- st_drv` reads "the create names `st_drv`; the factory
builds `slow_drv`".

## How the tree is worked out

The database records each component class on its own: the creates, overrides
and connections it writes, which function each is in and in what order, and
which of its own functions each function calls (see
[UVM testbench records](database.md)). The export replays them from the root
in the order UVM's build phase runs:

1. Overrides registered outside any component (a module's `initial` block)
   come first, in source order.
2. The root is created, and its constructor runs.
3. A component's `build_phase` runs: its overrides are registered and its
   children created in the order they are written. A child's constructor runs
   when it is created, so an override registered there applies at once.
4. Each child is then built the same way, **in name order** (UVM keeps a
   component's children in an array indexed by name), depth first.
5. Once everything is built, each component's `connect_phase` is replayed to
   find the links.

"`build_phase` runs" means what the language means:

- A class that defines no `build_phase` runs its base's.
- `super.build_phase(phase)` runs the base's at the point it is written.
- A helper function the phase calls (`build_agents()`, `set_overrides()`) runs
  as if it were written in place. A call to a virtual helper runs the version
  the actual type defines, so a test that redefines `set_overrides()` gets its
  own.
- An `if` or a loop around a call carries over to everything the call does.

So an override written in the test's `build_phase` **before**
`env = my_env::type_id::create(...)` changes the env's type. One written
**after** it does not change the env itself, but does reach the env's
descendants, which are built later. An override registered by a sibling that
comes earlier in name order reaches a later sibling's subtree. All three match
a simulator.

### The factory

The factory follows IEEE 1800.2 (`uvm_default_factory`):

- **Type overrides.** The newest registration wins. Overriding a type that is
  already overridden replaces the earlier entry, unless the call passed
  `replace=0`, in which case it is ignored (`override_ignored`).
- **Instance overrides** beat type overrides. Among them the **first**
  registered whose path matches wins. A path with `*` or `?` is a glob;
  without one it must match exactly.
- **Paths.** `set_inst_override_by_type("env.agt*", ...)` called on a
  component is relative to that component: called in the test, it means
  `uvm_test_top.env.agt*`. The `uvm_factory` forms take the full path as
  written. A registry form's path is relative to its `parent` argument, or
  absolute when there is none.
- **Chains.** The type an override produces is looked up again, so
  `A -> B` and `B -> C` give `C`, and an instance override can apply to a type
  that a type override produced. A loop builds the type asked for and is
  reported (`override_loop`).
- Components created with `new()` rather than the factory keep the type
  written.

## The JSON

```json
{"format": "svdb-uvm-tree", "version": 1,
 "sources": ["tb.svdb", "vip.svdb"],
 "root": {"name": "uvm_test_top", "type": "tb_pkg::my_test"},
 "nodes": [
   {"path": "uvm_test_top.env.agt.drv", "parent": "uvm_test_top.env.agt",
    "name": "drv", "handle": "drv",
    "declared": "vip_pkg::vip_driver", "type": "tb_pkg::fast_driver",
    "via": [{"kind": "type", "owner": "uvm_test_top", "replacement": "tb_pkg::fast_driver",
             "loc": {"file": "tb/my_test.sv", "line": 40}}],
    "tier": "driver",
    "ports": [{"name": "seq_item_port", "role": "port", "link": "seq_item"}],
    "loc": {"file": "vip/vip_agent.sv", "line": 51, "col": 7}}],
 "links": [
   {"source": {"path": "uvm_test_top.env.agt.drv", "port": "seq_item_port"},
    "target": {"path": "uvm_test_top.env.agt.seqr", "port": "seq_item_export"},
    "kind": "seq_item", "owner": "uvm_test_top.env.agt"}],
 "overrides": [
   {"original": "vip_pkg::vip_driver", "replacement": "tb_pkg::fast_driver",
    "kind": "type", "owner": "tb_pkg::my_test", "method": "build_phase",
    "status": "applied", "registered_by": ["uvm_test_top"],
    "applied_to": ["uvm_test_top.env.agt.drv"]}],
 "issues": []}
```

A field at its default value is left out. The format has its own version and
its own JSON Schema, `svdb/schema/svdb-uvm-tree-1.schema.json`, separate from
the database format's.

**Nodes** are listed in build order (each parent before its children,
children in name order). `type` is the class built and `declared` the class
the create names, present only when they differ. `via` lists the overrides
that took one to the other. `loc` is where the create is written. A node can
also carry:

- `conditional`: the create sits under an `if`, or is reached through a call
  that does.
- `multiplicity: "N"`: the create is in a loop. The node stands for all the
  components the loop makes, and is named `handle[*]` when the names are
  computed.
- `state`: `opaque` for a library or black-boxed component, which is not
  expanded; `unresolved` for a type no database describes.

`nested` output nests `children` arrays in place of `parent` links.

**Links** name both ends by full instance path and port. A handle that
leads to no component (one that is never created, or that an inherited
`connect_phase` names but this class does not build) makes the link
`state: unresolved`; `text` then keeps the endpoints as written.

**Overrides** lists every override in the databases, with its `status`:

| `status` | Meaning |
|---|---|
| `applied` | It changed the type of the components in `applied_to`. |
| `unused` | It was registered (by the components in `registered_by`), but no component created afterwards was built through it: nothing it matches was created, or an inst override (or a later one) took precedence. |
| `unplaced` | Nothing in this tree runs the function it is written in: another test's function, `run_phase`, a helper called through another object (`cfg.apply(this)`), or one never called. |
| `unknown_type` | It names a type that does not exist (a typo in a by-name override). |
| `unapplied` | Its path is computed, or relative to a component the extraction cannot identify. |

**Issues** have a `code`, a `message`, and a `path` or `loc` where one
applies:

| `code` | Meaning |
|---|---|
| `override_ignored` | A `replace=0` override for a type that was already overridden. |
| `override_loop` | Overrides that lead back to the type asked for. |
| `unplaced_override` | An override in a function of this tree's classes (or of a helper object) that nothing here reaches. |
| `unplaced_create` | A create in a function of this tree's classes that nothing here reaches. |
| `unknown_type` | A component whose type no database describes. |
| `unknown_port` | A link names a port its component's type does not have. |
| `abstract_instance` | A `virtual class` is built. |
| `duplicate_name` | Two children of one component have the same name. |
| `inline_cycle`, `inline_depth` | Helper calls that recurse, or nest more than 8 deep, are not followed further. |
| `ambiguous_type` | Two databases describe the same class differently (the first is used). |
| `max_nodes`, `max_depth` | The tree was cut short (`truncated` is set). |

(uvm-tree-several)=
## Several databases

A VIP and the testbench that uses it can be in separate databases:

```text
svdb uvm-tree -d tb.svdb -d vip.svdb
```

Classes are matched across databases by qualified name, so the VIP's agent is
expanded from the VIP's database, and an override written in the testbench
applies inside it. A class described in both, identically, is used once.
Described differently, the first database given wins and an
`ambiguous_type` issue says so.

## What is not modelled

The tree is worked out from source, not from a run, so some things are
approximated:

- **Conditions are not evaluated.** A create under `if (is_active)` is
  included and marked `conditional`, whatever `is_active` would be.
  `--no-conditional` leaves all such components out instead.
- **Loops are not unrolled.** A loop makes one representative node.
- **Calls through another object are not followed** (`cfg.build(this)`,
  `env.agt.configure()`): only calls on the component itself.
- **`config_db`** does not change the tree (for example
  `is_active` set through `config_db`).
- **Computed names and paths.** A `$sformatf` instance name gives the node
  its handle's name; a computed override path is not applied.
- **Overrides registered in `run_phase`** or later are listed as unplaced: by
  then the tree is built.
