# The design database

Everything this extension documents goes through a **design database** (an
`.svdb` file, SQLite inside). The parser front end writes it, and every
directive, role and diagram reads from it. Most projects never notice it is
there: it is built and cached for you. This page covers the cases where you do
want to know about it:
- builds that run often;
- parallel builds;
- documentation that refers to code this project does not parse.

The format itself, and the Python API, are described in [](svdb-api.md).

## One-shot mode (the default)

On each build, at `builder-inited`, the extension:

1. computes a digest of everything the parse depends on: the files that would
   be parsed, every `sv_*` setting that affects the parse, and the modification
   time of every candidate source file;
2. looks for `<doctreedir>/svdb/<digest>.svdb`;
3. if it is absent, parses the sources, elaborates the design and the UVM
   testbench, writes the database and a snapshot of those views beside it, and
   removes the entries of earlier digests.

So a build of unchanged sources parses nothing, and a source edit costs one
parse and one hierarchy walk, in the build that sees it first.

The cache lives with the doctrees, not the HTML, so publishing the HTML
directory never publishes it. `sphinx-build -E` keeps it; deleting
`<doctreedir>` (or `make clean`) removes it.

```python
# Build the database in memory on every build, and keep nothing on disk.
sv_db_cache = False
```

```{note}
Before the database, the instance hierarchy was walked only when a structural
directive asked for it. It is now walked once when the database is built, so
that every process can render structure without the parser: parallel readers,
and incremental builds whose environment Sphinx reloaded. A project with no
structural directive pays that walk once per source change, bounded by
`sv_structure_max_instances` and `sv_uvm_max_components`.
```

## What the database holds

The database holds more than the pages render. Besides everything the
directives document, the front end records:

- the declarations in a module, interface or program body: nets (every
  built-in net type, `interconnect`, user-defined nettypes, implicit nets),
  variables, `localparam`s, typedefs, nettypes, tasks and functions;
- modports (each port's direction and expression, imported and exported
  tasks, clocking blocks), clocking blocks with their clocking variables and
  skews, and which block is the default or global clocking;
- for an interface port, the interface and modport it names (`bus_if.mst`),
  or that it is generic (`interface bus`);
- instances (`params` and `conns` in every connection mode, including `.*`
  expanded against a known definition; `state: unresolved` when the
  definition is not in this compilation, with its connections still
  recorded), `for`/`if`/`case` generate constructs (every arm, including one
  never taken) and genvars; a `bind`-created instance is parented to the
  *target* definition, with `detail.bind` naming the scope that wrote it;
- the elaborated design, as `elab` records (one per definition and parameter
  set, with its sites and their instance counts) and `top` records; read
  them with `Database.tree()`, `Database.elaborations()`, or the raw
  records. An `elab`'s `generate` list says which if/case arm was taken (and
  how many iterations a for-loop ran); an instance inside an arm that was
  never taken still appears, as a `sites` entry with `present: false`;
- built-in gate instances (`and g1(...)`, `of_kind: gate`) are recorded only
  when `sv_structure_gates` opts in (section `structure.gates`), because a
  gate-level netlist can be huge;
- non-ANSI ports, as one object per port with the net type of its second
  declaration;
- package-level parameters and nettypes;
- enum literals (with their evaluated values, and `RED[3]` expanded to
  `RED0`…`RED2`) and struct or union fields, under their typedef, or under the
  variable whose type is declared inline;
- for every declared type: the text as written, its form (`builtin`, `enum`,
  `struct`, `class`, `typedef`, `virtual_interface`, …), the name it refers
  to (resolved to an object where there is one), and what a typedef resolves
  to; subroutine return types and arguments;
- `let` declarations (package- or module-scoped), and a concurrent assertion
  written directly as a module item (`assert`/`assume`/`cover`/`restrict
  property`), labeled or not, with its clock and `disable iff`; an
  *immediate* or deferred assertion is recorded when it sits in a labelled
  process, a named block or a task or function;
- a covergroup's `sample` arguments, a coverpoint's sampled expression,
  `iff` and type, and `cross`/`bins` (`bins`/`illegal_bins`/`ignore_bins`,
  arrays and the default bin). Covergroup `extends` (1800-2023) is not
  recorded: this build's parser does not accept the syntax.

These are there for tools that read the database (`svdb query`, the
[Python API](svdb-api.md)); directives for them come in a later release. An
interface or module that nothing instantiates is still read, with default
parameter values: the front end elaborates it on its own, apart from the
design.

## UVM testbench records

When the sources contain a UVM testbench, the database also holds what the
UVM directives show: the component tree, TLM connections, `uvm_config_db`
traffic, factory overrides, virtual-interface bindings and sequence bodies.
The directives read them from the database, so a page built from a warm cache
does not parse anything. Every record's `r` starts with `uvm.`; each one
carries one of the testbench views field for field. Type names are references
(`{"name": "my_env"}`), source positions are locations (`{"file", "line",
"col"}`), and a field at its default value is left out.

| `r` | One per | Main fields |
|---|---|---|
| `uvm.root` | testbench (one record) | `root`, `root_origin` (`run_test`, `config`, `directive`), `root_candidates`, `component_count`, `truncated` |
| `uvm.type` | component type in the tree | `type`, `tier` (`test`, `env`, `agent`, `driver`, ...), `chain` (base classes up to `uvm_void`), `ports` (TLM ports and exports: `name`, `type`, `link`, `declared_by`) |
| `uvm.child` | creation site in a `build_phase` | `owner` (the type that builds it), `inst_name`, `handle`, `type` |
| `uvm.conn` | `connect()` or handle assignment in a `connect_phase` | `owner`, `kind`, `source` and `target` (`path`, `port`, `type`, `component`) |
| `uvm.config` | `uvm_config_db` `set` or `get` | `id` (referred to by `uvm.binding`), `owner`, `method`, `action`, `cntxt`, `scope`, `field`, `type`, `value`, `virtual_interface` |
| `uvm.override` | factory override | `owner`, `method`, `original`, `replacement` |
| `uvm.binding` | virtual interface handed to the testbench | `interface_type`, `field`, `instance_path`, `set` and `consumers` (`uvm.config` ids), `drivers` (`path`, `port`, `type`) |
| `uvm.sequence` | sequence class | `type`, `chain`, `declared_by`, `overridden`, `body` (the sequence's activity as a nested list of nodes with `kind`: `item`, `sequence`, `fork`, `branch`, `loop`, `decision`, `delay`, `action`) |

For example, from a small testbench:

```text
{"r": "uvm.root", "root": {"name": "my_test"}, "root_candidates": ["my_test"], "root_origin": "run_test", "component_count": 8}
{"r": "uvm.child", "owner": {"name": "my_test"}, "inst_name": "env", "handle": "env", "type": {"name": "my_env"}, "loc": {"file": "f1", "line": 136, "col": 13}}
{"r": "uvm.override", "owner": {"name": "ovr_test"}, "method": "build_phase", "original": {"name": "ovr_item"}, "replacement": {"name": "big_item"}, "loc": {"file": "f2", "line": 121, "col": 7}}
{"r": "uvm.binding", "interface_type": {"name": "bridge_if"}, "field": "vif", "instance_path": "bridge_tb_top.u_bus", "set": "c4", "consumers": ["c1", "c3"], "drivers": [{"path": "bridge_tb_top.u_dut", "port": "bus", "type": {"name": "bridge_dut"}}]}
```

Some answers are worked out when the database is read rather than stored:
which `get` each `set` reaches, which types build a given component, and
where a type is used. They are derived from the records above, so they can
never disagree with them.

The records describe one testbench: the one `run_test("...")` names, or the
one `sv_uvm_root` (`svdb build --uvm-root`) chooses. `svdb export` writes them
after the design records; select them with `svdb sql`, or with
`grep '"r":"uvm\.'` on the exported NDJSON.

## Parallel builds

`sphinx-build -j N` parses at most once, in the main process, before the
readers start. The readers open the database read-only. One case still parses
inside a reader: a UVM directive that names its own root (`sv:uvm-tree:: my_env`)
when the cache was already warm. The database holds the testbench seen from
its default root only, so that reader parses once to answer it.

## Pre-built databases

`svdb build` runs the same front end outside Sphinx:

```console
$ svdb build --source-dir vip/src -I vip/include -D VIP_SIM -o vip.svdb
$ svdb build --sphinx-conf docs/conf.py -o design.svdb    # reuse the sv_* settings
```

With `--sphinx-conf`, the `conf.py` is executed from its own directory, and the
flags given beside it override its values. `svdb import` makes a database from
NDJSON written by another tool.

List pre-built databases in `sv_databases`. They are read **after** the
project's own sources, in order, so a name defined in both resolves to the
project's object:

```python
sv_databases = [
    "_db/vip.svdb",                                  # relative to conf.py
    {"path": "/tools/acme/acme_uvc.svdb", "role": "local"},
]
```

Objects from a listed database can be documented (`autosvclass`) and
referenced (`` :sv:class:`acme_pkg::acme_item` ``) like local ones. A path that
does not exist, or a file that is not a database of a supported layout, stops
the build with a configuration error. A `role: external` database describes
components documented elsewhere: its objects are link targets and diagram
ports, not pages of your own (see {doc}`external`).

A pre-built database brings objects and documentation comments. It does not
bring the elaborated design or the UVM testbench views: those come from the
sources this project parses.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `sv_db_cache` | `True` | Keep the front end's database in `<doctreedir>/svdb/` between builds. |
| `sv_databases` | `[]` | Pre-built databases read after the sources: paths (relative to `conf.py`) or `{"path": ..., "role": "local" \| "external"}`. |

## CI pattern

A design that several documentation projects share can be parsed once:

```console
$ svdb build --sphinx-conf rtl/docs/conf.py -o artifacts/rtl.svdb
$ svdb validate artifacts/rtl.svdb
```

Each consumer then lists `artifacts/rtl.svdb` in `sv_databases` and parses only
its own sources. Rebuild the artifact when the shared sources change. The
database records its inputs in its header (`svdb export rtl.svdb | head -1`),
which tells you which configuration it was built with.
