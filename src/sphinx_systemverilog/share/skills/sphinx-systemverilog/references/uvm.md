# UVM testbench documentation

Six directives plus two class-page renderings. Published version:
<https://dvkit.org/fvutils/sphinx-systemverilog/usage/uvm-testbench.html>

## The governing fact

A UVM testbench has a hierarchy but no *elaborated* one. `tb_top.env.agt.drv`
exists nowhere in the compiled output — the hierarchy exists only as statements
inside `build_phase` that would, if the simulation ran, call the factory.

> Everything here is the testbench **as written in `build_phase`**. It is not a
> simulation trace. Factory overrides, config-driven counts and dynamically
> named components are *reported as such* rather than resolved.

Say this on the page when it matters, and never "fix" the output by resolving
what it deliberately leaves annotated.

---

## Node states

Every component is in exactly one of three states. This is what makes the
output trustworthy:

| State | Means |
|---|---|
| `ok` | The type resolved and the walk descended into it. |
| `opaque` | A deliberate boundary (black-boxed). Real, labelled, not looked into. |
| `unresolved` | The type did not resolve — its package was not parsed, or does not exist. The node and its declared type name are reported; nothing below it is known. |

Unresolved nodes are **shown, counted and marked** rather than dropped.
Dropping them would make a testbench whose register model failed to parse look
identical to one that has no register model.

If you see `[unresolved]`, the fix is almost always in `conf.py`: the package
was not in `sv_source_dirs`/`sv_build_units`.

## Black-boxing

```python
sv_uvm_blackbox = ["*_reg_block", "acme_vip_*"]   # glob on the type name
sv_uvm_blackbox_bases = ["uvm_reg_block"]          # matches the base-class chain
```

For code that legitimately should not be walked into: a register model
generated from RDL/IP-XACT and absent at doc time (the default base covers
this), vendor VIP delivered precompiled, and the UVM library itself (always
stopped at, no configuration needed). A black-boxed component renders as
`[opaque]` — present and counted, never dropped.

---

## `sv:uvm-tree`

```rst
.. sv:uvm-tree::
.. sv:uvm-tree:: my_test
   :depth: 3
   :collapse:
```

Argument optional: with none, the root is detected from a `run_test("...")`
call in a top module. If a project has several testbenches, one is shown and the
others named beneath — name the root explicitly to be deterministic.

| Option | Meaning |
|---|---|
| `:depth:` | Levels shown; default `sv_uvm_tree_depth` (4). What is hidden is counted and reported. |
| `:collapse:` | Fold siblings differing only in name (`agt_a, agt_b : my_agent`). Keyed on everything else, so components built under different conditions never merge. |
| `:optional:` | Render nothing, warn about nothing, if the root does not exist. |

Annotations:

| Annotation | Meaning |
|---|---|
| `[conditional]` | Built inside an `if` or `case` — it may not be built. |
| `(×N)` | Built in a loop whose trip count is not a compile-time constant. The number is deliberately not guessed. |
| `[opaque]` | A black-boxed boundary. |
| `[unresolved]` | Type could not be resolved. |
| `[overridden → T]` | A factory override targets this node (see below). |

TLM **ports** are not components and do not appear: UVM declares
`uvm_port_base #(IF) extends IF`, with `IF` deriving from `uvm_void`, and a port
owns an internal proxy rather than being a component. TLM **FIFOs** are
components and do appear, as library boundaries.

Every type name is a cross-reference — the reason the tree is text.

---

## `sv:uvm-config`

```rst
.. sv:uvm-config::
.. sv:uvm-config:: my_agent
   :orphans:
```

Every `uvm_config_db#(T)::set` in the project with the `get`s that could read
it. The optional argument is a glob on the setting component's name.

| Option | Meaning |
|---|---|
| `:orphans:` | Show only settings nothing reads. |
| `:optional:` | Render nothing, silently, if no accesses exist. |

Accesses are found wherever written — any method of any component, and any
`initial` block in a top module. That last is essential: the `set` that binds a
virtual interface lives outside every component. The library's own accesses
(`uvm_component::set_config_object`, `uvm_sequencer_base`'s own knobs) are
excluded as noise.

### Orphan detection — a real finding

```systemverilog
uvm_config_db #(int)::set(this, "drv", "n_itmes", 4);   // n_items
```

That compiles, elaborates and simulates in silence; the driver keeps its
default and the testbench quietly does the wrong thing. The reverse — a `get`
nothing sets — means a knob that can never be turned. Both are reported.

**Report these; do not silence them.** They are testbench bugs surfaced by the
documentation build, and fixing them means editing the testbench.

### What the pairing uses

- **Field name only**, glob-aware in **both** directions (`set("n_*")` pairs
  with `get("n_items")` and vice versa).
- **Scope is displayed but takes no part in the match.** A `set`'s full scope is
  `{cntxt, ".", inst_name}`, and `cntxt`'s hierarchical path is a run-time fact
  — `this` inside a reusable agent is a different string in every testbench.
  Matching on it could only narrow, and a narrower match invents orphans.
- **A computed field name** (`$sformatf("knob_%0d", i)`) cannot be paired at
  all, so it is excluded and counted under the table. Treating it as matching
  everything would clear every orphan in the project.

### Warnings are opt-in

```python
sv_uvm_warn_orphans = True   # default False
```

The finding is always rendered in the page. Escalating it to a build warning is
a project's own decision — installing a documentation extension must not turn a
green build red over a testbench smell nobody asked about.

---

## `sv:uvm-schematic`

```rst
.. sv:uvm-schematic::
.. sv:uvm-schematic:: my_env
   :tier: my_perf_monitor=bottom, my_arbiter=top
   :order: agt_a, agt_b, sb
```

One level of a testbench: the components a container builds, the TLM ports they
declare, and the connections its `connect_phase` makes. Agents render as
clusters holding their components — "is this agent active?" is answered by
whether it holds a driver.

With no argument the root is auto-detected as for `sv:uvm-tree`, then descended
while there is exactly one child, stopping at the first env — the level where
wiring exists.

| Option | Meaning |
|---|---|
| `:tier:` | `name=top\|middle\|bottom`, comma-separated. Matches an instance handle first, then a type name. |
| `:order:` | Component handles, left to right, **within a tier**. |
| `:optional:` | Render nothing, silently, if the component does not exist or builds nothing. |

**Single-level by decision** — depth is `sv:uvm-tree`'s job, and it does it well
as text.

### Tiers are derived, not configured

| Tier | Derived from | Drawn as |
|---|---|---|
| top | `uvm_sequencer`, `uvm_sequencer_base` (so: virtual sequencers) | box |
| middle | `uvm_scoreboard`, `uvm_subscriber`, `uvm_env`, and anything unplaced | box |
| bottom | `uvm_agent` | cluster of its components |
| bottom | `uvm_driver`, `uvm_monitor` | box |

`:tier:` is an override, not the mechanism — the default layout is right
without configuration. Components inside a cluster always take the cluster's
tier; overriding one individually is ignored, because it would ask Graphviz to
rank a node twice.

### What is read

Three connection styles, because UVM has three:

- **`connect` calls** — `mon.ap.connect(sb.aimp)`, identified by the lexical
  path of the called subroutine (`uvm_port_base::connect`), so your own method
  named `connect` is not mistaken for one.
- **Handle assignments** — `vseqr.seqr_a = agt_a.seqr`. Read from
  `connect_phase` **only**: an assignment is wiring by convention, and reading
  them from arbitrary methods would turn every `m_parent = parent` into an edge.
- **Connections written inside a child** — an agent's own
  `drv.seq_item_port.connect(seqr.seq_item_export)`, drawn once per instance of
  that agent.

Ports come from **declared member types**, including inherited ones. Inherited
*library* ports are shown when something connects to them and hidden when
nothing does (a real `uvm_driver` has three, of which one is ever drawn); ports
your own components declare are always shown. Whatever is hidden is counted
under the diagram. An edge reaching outside the single-level view is reported
rather than dropped.

### Layout note

Every TLM edge carries `constraint=false` so connectivity decorates the layout
instead of fighting it; containment decides ranks; tiers are pinned with
`rank=same`, which needs `newrank=true` (Graphviz ≥ 2.30). With an older `dot`
the tier pinning is dropped and the diagram says so underneath.

---

## `sv:uvm-sequence`

```rst
.. sv:uvm-sequence:: main_seq
   :depth: 2
```

One sequence's `body()` as a UML activity diagram. **The argument is
required** — there is no "the sequence" to default to.

| Option | Meaning |
|---|---|
| `:depth:` | Levels of **sub-sequence** expansion (not statement nesting). `1` (default) draws each sub-sequence as one step; `2` opens them. |
| `:optional:` | Render nothing, silently, if the name is not a sequence. |

| Shape | Means | Read from |
|---|---|---|
| filled / ringed circle | start, end | — |
| rounded box | a step | — |
| plain box | a transaction | `start_item`, typed from the operand |
| blue rounded box | a sub-sequence | `start`, typed from the operand |
| diamond | a decision | `if` / `case`, labelled with the condition as written |
| solid bar | fork and join | `StatementBlockKind` |
| dashed cluster | a loop, labelled with its controlling expression | the loop statement |

- **Join semantics are read, not guessed**: `join_any` says `join_any` because
  the source does; `join_none` gets no join bar at all, because the branches
  genuinely do not rejoin.
- **Fork branch names survive**: `begin : traffic` labels the branch.
- Edges here **are** ordering constraints — the opposite of the schematic's
  rule. Only a loop's back-edge carries `constraint=false`.

### Macro collapse

A `` `uvm_do `` is one line of source and about a dozen statements after
preprocessing. Consecutive statements from the same macro **invocation**
collapse to one step labelled with the macro name — grouping is by invocation,
so two adjacent `` `uvm_do `` calls are two transactions. The surviving step is
chosen by type: `uvm_do` starts a `uvm_sequence_base` local alongside the
`start_item` naming your type, and the library-typed candidate loses. A macro
that expands to nothing worth drawing (`` `uvm_info `` and relatives) produces
no step and is not named.

Everything in `body()` that is not control flow — reporting, assignment,
randomization — is **counted and reported** under the diagram rather than
dropped. Declarations are neither drawn nor counted. A sequence that does not
override `body()` is *said* rather than drawn, because an empty diagram would
read as "this sequence does nothing".

---

## `sv:uvm-binding`

```rst
.. sv:uvm-binding::
.. sv:uvm-binding:: bridge_if
```

The virtual-interface bridge: which RTL interface instance reaches which
component, and what that interface is wired to. A binding is a join between two
worlds through a **string**:

```systemverilog
uvm_config_db #(virtual bridge_if)::set(null, "*", "vif", u_bus);          // top module
if (!uvm_config_db #(virtual bridge_if)::get(this, "", "vif", vif)) ...    // component
```

Nothing checks the two strings agree. The optional argument is a glob on the
interface type; `:optional:` behaves as elsewhere.

| Column | Is |
|---|---|
| Set in | The class or module the `set` is written in |
| Scope | `cntxt` and `inst_name` as UVM would join them |
| Field | The database key both halves must agree on |
| Interface | The specialization's `T`, cross-referenced |
| RTL instance | The **elaborated** path (`bridge_tb_top.u_bus`) |
| Connects to | Module instances that interface reaches |
| Read by | Components whose `get` could match |

### Three failures, none of which the compiler reports

All three end as a null virtual interface hundreds of cycles into a simulation:

1. **A binding nothing reads** — the `config_db` typo, with a worse ending: a
   virtual interface has no usable default.
2. **An interface wired to no RTL** — handed over correctly, connected to
   nothing. The testbench is driving air.
3. **A handle rather than an instance** — `set(this, "*", "vif", vif)` passes a
   handle, so there is no RTL instance to name. Reported as such, not guessed.

The RTL side looks at instances declared **in the interface's own scope** and no
others; the bound is printed under every table. Within that scope it is exact: a
connection through a modport (`.bus(u_bus.mon_mp)`) resolves to the interface
instance, and a signal port on the same instance is not mistaken for a binding.
More than one instance on the far end is normal and all are listed.

Pairing to components is on the field name, glob-aware both ways, and narrowed
to `get`s that are themselves virtual interfaces. Scope is shown but not
matched, for the same reason as in the config table.

---

## `sv:uvm-used-by`

```rst
.. sv:uvm-used-by:: my_agent
   :root: my_test
```

Every component that builds this one — the inverse of `sv:uvm-tree`, and the
right thing to put on a component's own page: a reader who arrived at
`my_agent` wants to know who builds *it*, under what handle, and whether that
happens unconditionally.

A component nothing builds is a **finding**, not an empty table — a class
written, registered with the factory, and never instantiated. If it is the
target of a factory override, that is reported next to it, because a deliberate
override target is not dead code.

---

## Factory overrides

The one construct that makes a component tree *lie*: `build_phase` says
`my_driver::type_id::create(...)` and the simulation builds a `fast_driver`,
with nothing in the agent's source hinting at it. So overrides are reported
inline on the affected node:

```text
└── agt : my_agent
    ├── drv : my_driver   [overridden → fast_driver]
    └── mon : my_monitor  [overridden → noisy_monitor under env.agt.* conditionally]
```

**Annotated, never resolved.** Whether an override applies depends on whether
its statement ran, on any later override replacing it, and — for an inst
override — on a hierarchical path that does not exist until elaboration.
Printing the target type would trade one confident wrong answer for another.

All five spellings are read:

| Written as | Note |
|---|---|
| `set_type_override_by_type(a::get_type(), b::get_type())` | the `uvm_component` wrapper |
| `factory.set_type_override_by_type(...)` | the singleton — same name, different declaring class |
| `set_type_override("a", "b")` | by name; arguments are strings |
| `a::type_id::set_type_override(b::get_type())` | registry form; the replaced type is **not an argument**, it is the specialization's own `Tname` |
| `set_inst_override_by_type("env.agt.drv", a::get_type(), b::get_type())` | scoped to a path |

Argument positions are read **per method**: `uvm_component::set_inst_override_by_type`
takes the path first and `uvm_factory::set_inst_override_by_type` takes it last,
and both spellings compile.

The by-name forms take strings, so `set_type_override("my_monitor", "noisy_moniter")`
compiles and silently never applies. It is marked on the node (`— no such type`)
and counted under the tree — which is the practical argument for preferring the
`::get_type()` forms.

---

## On a class's own page

Rendered by `autosvclass`, from stored names, so they work with no testbench
view present and survive a pickled index:

**A UVM kind badge** beside the name — `component`, `sequence`,
`sequence item`, `TLM port` or `object`. A class unrelated to UVM gets no badge
rather than a misleading one. (Order matters: every sequence *is* a
`uvm_sequence_item`, so a naive reading would label every sequence a
transaction.)

```text
class my_agent  extends uvm_agent  [component]
```

**Which phases it implements**, as a field:

> **UVM phases:** `build_phase`, `connect_phase`, `run_phase`

Its own overrides only, ordered by **execution**, not alphabetically. The
run-time schedule (`reset_phase`, `main_phase`, …) counts, because a component
using it uses it *instead of* `run_phase`.

---

## Cost

Nothing here is computed unless a UVM directive asks for it, and each cost is
separate:

| Cost | Paid by | Shared |
|---|---|---|
| Component walk (every `build_phase`) | `sv:uvm-tree`, `sv:uvm-schematic`, `sv:uvm-used-by` | once per root, per build |
| `config_db` scan (also carries factory overrides) | `sv:uvm-config`, `sv:uvm-binding` | once per build |
| One `body()` read | `sv:uvm-sequence` | memoized per sequence |

A tree and a schematic rooted at the **same** component cost one walk between
them; different roots cost one walk each. `sv:uvm-binding` adds only a look at
the scope each bound interface is declared in — it does **not** walk the RTL
hierarchy. An RTL-only project pays none of this.

`sv_uvm_max_components` (default 5000) caps the walk; exceeding it reports
truncation rather than hanging the build.

---

## A component page, end to end

```rst
.. autosvclass:: my_pkg::my_agent
   :members:
   :show-inheritance:

.. rubric:: Built by

.. sv:uvm-used-by:: my_agent

.. rubric:: Wiring

.. sv:uvm-schematic:: my_agent

.. rubric:: Configuration

.. sv:uvm-config:: my_agent
```
