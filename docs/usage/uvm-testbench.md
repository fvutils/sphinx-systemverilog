(uvm-testbench)=
# UVM testbenches

A UVM testbench has a hierarchy, but unlike an RTL design it has no *elaborated*
one. There is no `tb_top.env.agt.drv` anywhere in the compiled output: the
hierarchy exists only as statements inside `build_phase` that would, if the
simulation ran, call the factory. Documenting it therefore means reading those
statements and reporting what the source says will be built.

That distinction is not a technicality, and this page states it once so the rest
of the reference can lean on it:

> This is the testbench hierarchy **as written in `build_phase`**. It is not a
> simulation trace. Factory overrides, config-driven counts and dynamically
> named components are reported as such rather than resolved.

## Status

This feature is being built in phases; this page grows with it.

| Directive | Answers | Status |
|---|---|---|
| `sv:uvm-tree` | What does this testbench build? | **available** |
| `sv:uvm-config` | What is set through `config_db`, and does anything read it? | **available** |
| `sv:uvm-schematic` | How are the components wired together? | **available** |
| `sv:uvm-sequence` | What does this sequence do? | **available** |
| `sv:uvm-binding` | Which RTL interface does this agent drive? | **available** |
| `sv:uvm-used-by` | Which components build this one? | **available** |

Two more answers are rendered by `autosvclass` rather than by a directive of
their own, because they belong on a class's own page and have to work there
with no testbench view present: **what a class is** in UVM terms, and **which
phases it implements**. See [below](uvm-class-pages).

See [Example: a UVM testbench](../examples/uvm-testbench) for live output.

## `sv:uvm-tree`

```rst
.. sv:uvm-tree::

.. sv:uvm-tree:: my_test
   :depth: 3
   :collapse:
```

The argument names the root component. It is optional: with none, the root is
detected from a `run_test("...")` call in a top module, which is right for the
common case of one testbench per project. If the project contains several, one
is shown and the others are named beneath the tree.

| Option | Meaning |
|---|---|
| `:depth:` | Levels to show. Defaults to `sv_uvm_tree_depth` (4). Whatever is hidden is counted and reported. |
| `:collapse:` | Fold siblings that differ only in name (`agt_a, agt_b : my_agent`). The fold is keyed on everything else, so two components built under different conditions never merge. |
| `:optional:` | Render nothing, and warn about nothing, if the root does not exist. For pages shared across projects. |

Every type name is a cross-reference to that component's documentation, which is
the reason the tree is text rather than a picture.

### What the annotations mean

| Annotation | Meaning |
|---|---|
| `[conditional]` | Built inside an `if` or `case`. It may not be built. |
| `(×N)` | Built in a loop whose trip count is not a compile-time constant. The number is deliberately not guessed. |
| `[opaque]` | A boundary — see [black-boxing](uvm-blackbox). Present, not walked into. |
| `[unresolved]` | Its type could not be resolved. Nothing below it is known. |

A TLM port is not shown, because a port is not a component: UVM declares
`uvm_port_base #(IF) extends IF`, where `IF` derives from `uvm_void`. A port
owns an internal component proxy rather than being one. TLM *FIFOs* are
components, and do appear — as library boundaries.

(uvm-config)=
## `sv:uvm-config`

```rst
.. sv:uvm-config::

.. sv:uvm-config:: my_agent
   :orphans:
```

Every `uvm_config_db#(T)::set` in the project, with the `get`s that could read
it. The optional argument is a glob on the setting component's name, for a page
that documents one agent rather than a whole testbench.

| Option | Meaning |
|---|---|
| `:orphans:` | Show only settings nothing reads. |
| `:optional:` | Render nothing, and warn about nothing, if no accesses exist. |

Accesses are found wherever they are written — any method of any component, and
any `initial` block in a top module. That last one is not an edge case: the
`set` that binds a virtual interface lives outside every component, and a scan
that started from the test would miss the half of the pair that matters most.

The library's own accesses are excluded. `uvm_component::set_config_object`
calls `config_db::set`, and `uvm_sequencer_base` reads its own knobs; those are
real, and they are not what your document is about.

### Orphan detection

A `config_db` field name is a string, and a typo in one is invisible:

```systemverilog
uvm_config_db #(int)::set(this, "drv", "n_itmes", 4);   // n_items
```

That compiles, elaborates and simulates without a murmur. The driver keeps its
default and the testbench quietly does something other than what was intended.
Nothing at run time reports it. Reported here, it takes about a second to spot.

The reverse case is reported too — a `get` nothing ever sets, which means a
component whose knob can never be turned.

(uvm-orphan-caveats)=
### What the pairing does and does not use

Two decisions are worth knowing about, because they are what keeps the report
believable.

**Pairing is on the field name only, and matches globs in both directions.**
UVM allows either side to be a pattern, so `set("n_*")` pairs with
`get("n_items")` and vice versa. Scope is shown in the table but takes no part
in the match: the full scope of a `set` is `{cntxt, ".", inst_name}`, and
`cntxt`'s hierarchical path is a run-time fact — `this` inside an agent is a
different string in every testbench that instantiates it. Bringing scope into
the match could only ever *narrow* it, and a narrower match invents orphans.

**A computed field name is excluded from pairing, and counted.** Something like
`$sformatf("knob_%0d", i)` cannot be paired at all. The maximally conservative
choice would be to treat it as matching everything, and that choice is wrong:
one such access would clear every orphan in the project and the view would
never report anything. So they are set aside, and the note under the table says
how many — the finding stays useful, and its limit stays visible.

### Warnings are opt-in

```python
sv_uvm_warn_orphans = True   # default False
```

Off by default on purpose. Installing this extension must not turn a green
documentation build red over a testbench smell nobody asked about. The finding
is *always* rendered in the page; escalating it to a build warning is a
decision a project takes for itself, once, in writing.

(uvm-schematic)=
## `sv:uvm-schematic`

```rst
.. sv:uvm-schematic::

.. sv:uvm-schematic:: my_env
   :tier: my_perf_monitor=bottom, my_arbiter=top
   :order: agt_a, agt_b, sb
```

One level of a testbench, drawn: the components a container builds, the TLM
ports they declare, and the connections its `connect_phase` makes. Agents are
rendered as clusters holding their own components, because "is this agent
active?" is answered by whether it holds a driver.

The argument names the container. With none, the root is auto-detected as for
`sv:uvm-tree` and then descended: a test that contains exactly one env draws as
a single box, which helps nobody, so the default walks down while there is
exactly one child and stops at the first env — the level where wiring exists.

| Option | Meaning |
|---|---|
| `:tier:` | `name=top\|middle\|bottom`, comma-separated. Overrides the derived tier for one component. Matches an instance handle first, then a type name. |
| `:order:` | Component handles, left to right. Applies within a tier — two boxes on different ranks have no left-to-right relationship to state. |
| `:optional:` | Render nothing, and warn about nothing, if the component does not exist or builds nothing. |

**Single-level, by decision.** Depth is already served by `sv:uvm-tree`, which
handles it as text and handles it well. A nested schematic has to answer
questions that do not yet have good answers — how to aggregate edges at a
sub-env boundary, what a tier means two levels down — so it is deferred rather
than rejected.

(uvm-tiers)=
### Tiers come from UVM's taxonomy, not from configuration

The important design point is that **"agents at the bottom" costs nothing to
author.** UVM's base-class hierarchy already encodes the roles, so the default
tier falls out of what a component extends:

| Tier | Derived from | Drawn as |
|---|---|---|
| top | `uvm_sequencer`, `uvm_sequencer_base` (so: virtual sequencers) | a box |
| middle | `uvm_scoreboard`, `uvm_subscriber`, `uvm_env`, and anything the taxonomy does not place | a box |
| bottom | `uvm_agent` | a cluster of its components |
| bottom | `uvm_driver`, `uvm_monitor` | a box |

`:tier:` is the override, not the mechanism. A feature people have to configure
before it produces anything worth looking at is a feature they configure once
and abandon.

Components *inside* a cluster always take the cluster's tier. Overriding one
individually would ask Graphviz to place a node in two ranks at once, so the
option is ignored for them.

### What is drawn, and what is not

Three connection styles are read, because UVM has three:

- **`connect` calls** — `mon.ap.connect(sb.aimp)`. Identified by the lexical
  path of the called subroutine (`uvm_port_base::connect`), so a method of your
  own called `connect` is not mistaken for one.
- **Handle assignments** — `vseqr.seqr_a = agt_a.seqr`. Not a call at all. A
  virtual sequencer is the one component whose entire purpose is the
  connections it holds, so a connect-only reading would draw it with none.
- **Connections written inside a child** — an agent's own
  `drv.seq_item_port.connect(seqr.seq_item_export)` is drawn once per instance
  of that agent, because each instance really does make it.

Handle assignments are read from `connect_phase` only. A `connect` call is
unambiguous wherever it is written; an assignment is wiring only by the
convention that it happens there, and reading them from arbitrary methods would
turn every `m_parent = parent` in a constructor into an edge.

Ports come from **declared member types**, including inherited ones — a port is
not a `uvm_component` and so never appears in a hierarchy read from
`build_phase`. Inherited *library* ports are shown when something connects to
them and hidden when nothing does: real `uvm_driver` hands every driver
`seq_item_port`, `seq_item_prod_if` and `rsp_port`, of which one is the port
anybody has ever drawn. Ports your own components declare are always shown, and
whatever is hidden is counted under the diagram.

An edge whose endpoints reach outside this single-level view is reported rather
than dropped, for the same reason `[unresolved]` exists in the tree.

(uvm-sequence)=
## `sv:uvm-sequence`

```rst
.. sv:uvm-sequence:: main_seq

.. sv:uvm-sequence:: main_seq
   :depth: 2
```

One sequence's `body()`, drawn as a UML activity diagram.

This is the one view here that is not a static approximation of something
dynamic. A component tree is a reading of `build_phase` and a schematic is a
reading of `connect_phase`; both describe a run they cannot observe. A sequence
*is* a control-flow object, so an activity diagram is its natural shape rather
than an imposed one. What the diagram still cannot say is which way a branch
went — and that is a property of the run, not a limit of the reading.

The argument is required. Every other directive here can default its root from
`run_test`; there is no equivalent of "the sequence", and choosing one
alphabetically would be a guess dressed as a default.

| Option | Meaning |
|---|---|
| `:depth:` | Levels of sub-sequence expansion. `1` (the default) draws each sub-sequence as one step; `2` opens them. |
| `:optional:` | Render nothing, and warn about nothing, if the name is not a sequence. |

`:depth:` counts **sub-sequences**, not statement nesting. A sub-sequence
started three `if`s deep is one level down. Counting braces instead would make
the option mean something no reader could predict.

### The notation

| Shape | Means | Read from |
|---|---|---|
| filled circle / ringed circle | start, end | — |
| rounded box | a step | — |
| plain box | a transaction (`start_item`) | the operand's type |
| blue rounded box | a sub-sequence (`start`) | the operand's type |
| diamond | a decision | `if` / `case`, labelled with the condition as written |
| solid bar | a fork, and its join | `StatementBlockKind` |
| dashed cluster | a loop, labelled with its controlling expression | the loop statement |

Two of those rows are the reason this works as well as it does.

**Join semantics are read, not guessed.** `StatementBlockKind` distinguishes
`Sequential`, `JoinAll`, `JoinAny` and `JoinNone`, so the join bar says
`join_any` because the source says `join_any`. `join_none` gets no join bar at
all: the branches genuinely do not rejoin, and drawing one would assert a
synchronisation the source refuses.

**Fork branches keep their names.** Engineers already name fork branches
descriptively — `begin : traffic`, `begin : timeout` — and those labels survive
elaboration, so the diagram gets human-authored branch names for free.

Edges here are ranking constraints, which is the exact opposite of the rule the
[schematic](uvm-schematic) follows. There, an edge is a connection and not an
ordering, so every one carries `constraint=false`. Here an edge *is* "happens
after", and a rank is exactly that. The single exception is a loop's back-edge,
which is a real cycle and would otherwise drag the end of the body above its
start.

### Macros, and what is counted

A `` `uvm_do `` is one line of source and roughly a dozen statements after the
preprocessor is done with it. Drawing the expansion would draw a dozen boxes for
one line, so consecutive statements from the same macro **invocation** collapse
to the single step they mean, labelled with the macro's name — because a reader
looking for `start_item` in the source will find `` `uvm_do `` there instead.

Grouping is by invocation, not by macro name: two adjacent `` `uvm_do `` calls
are two transactions.

The step that survives a collapse is chosen by *type*. Real `uvm_do` declares a
`uvm_sequence_base` local and starts it alongside the `start_item` that names
your type, so the expansion offers two candidates; the library-typed one loses.
A macro that expands to nothing worth drawing — `` `uvm_info `` and its
relatives — produces no step and is not named underneath, because slang reports
the innermost macro and that name is one you never wrote.

Everything in `body()` that is not control flow — reporting, assignment,
randomization — is **counted and reported** rather than dropped. A `body()` is
mostly not control flow, and a diagram of only the constructs it understands
would be claiming the task is shorter than it is. Declarations are neither drawn
nor counted: `cfg_seq cfg;` is part of writing a task, not part of what it does.

A sequence that does not override `body()` is said rather than drawn. An empty
diagram would read as "this sequence does nothing", which is a claim about the
testbench rather than about the source.

(uvm-binding)=
## `sv:uvm-binding`

```rst
.. sv:uvm-binding::

.. sv:uvm-binding:: bridge_if
```

The virtual-interface bridge: which RTL interface instance reaches which
component, and what that interface is wired to.

This is the view this extension is in a position to produce and most tools are
not, because it elaborates **both** sides. A virtual-interface binding is a
join between two worlds through a *string*. A top module files an interface
instance in `uvm_config_db` under a field name:

```systemverilog
uvm_config_db #(virtual bridge_if)::set(null, "*", "vif", u_bus);
```

and a component, elsewhere, fetches it back by that name:

```systemverilog
if (!uvm_config_db #(virtual bridge_if)::get(this, "", "vif", vif))
```

Nothing checks that the two strings agree. A tool that reads only the RTL cannot
see the second half; a tool that reads only the classes cannot see the first.

The optional argument is a glob on the interface type, for a page documenting
one interface rather than the whole bridge.

| Option | Meaning |
|---|---|
| `:optional:` | Render nothing, and warn about nothing, if there are no matching bindings. |

### The columns

| Column | Is |
|---|---|
| Set in | The class or module the `set` is written in |
| Scope | `cntxt` and `inst_name` as UVM would join them |
| Field | The database key — the string both halves have to agree on |
| Interface | The specialization's `T`, cross-referenced |
| RTL instance | The **elaborated** path of the interface (`bridge_tb_top.u_bus`) |
| Connects to | Module instances that interface reaches, cross-referenced |
| Read by | Components whose `get` could match |

The elaborated path in *RTL instance* is what makes the join possible. `u_bus`
as written is a name in a scope; `bridge_tb_top.u_bus` is a fact about the
elaboration, and it is the form that can be matched against a port connection.

### Three failures, none of which the compiler reports

All three end the same way at run time — a null virtual interface, dereferenced
hundreds of cycles into a simulation — and none of them produce a single
compile-time diagnostic.

**A binding nothing reads.** The same typo the [config table](uvm-config)
reports, with a worse ending: an ordinary `config_db` miss leaves a component on
its default, but a virtual interface has no usable default.

**An interface wired to no RTL.** Handed to the testbench correctly and
connected to nothing. The binding is fine; the testbench is driving air.

**A handle rather than an instance.** `set(this, "*", "vif", vif)` passes on a
virtual-interface *handle*, so there is no RTL instance to name. Reported as
such rather than guessed — naming the instance the handle happens to hold at run
time would be inventing a fact the source does not contain.

### What the RTL side looks at

The instances declared **in the interface's own scope**, and no others. An
interface passed further down through a port reaches deeper modules too, and
following it would mean walking the whole hierarchy for a result that is
almost always the same one. The bound is printed under every table rather than
left implicit.

Within that scope the answer is exact. A connection through a modport
(`.bus(u_bus.mon_mp)`) resolves to the interface instance, so one rule covers
both forms, and a signal port on the same instance is not mistaken for a
binding. More than one instance on the far end is normal and all of them are
listed: "the DUT" is the obvious answer and not always the whole answer.

Pairing to components is on the field name, glob-aware in both directions, and
narrowed to `get`s that are themselves virtual interfaces — a narrowing the
config table cannot make, because it does not know the type. Scope is shown but
takes no part in the pairing, for the [same reason](uvm-orphan-caveats) it does not
there.

(uvm-overrides)=
## Factory overrides

A factory override is the one construct in UVM that makes a component tree
*lie*. `build_phase` says:

```systemverilog
drv = my_driver::type_id::create("drv", this);
```

the extraction reads `my_driver`, and the simulation builds a `fast_driver` —
because somewhere else entirely, usually in a test, somebody wrote an override.
Nothing in the agent's own source hints at it.

So `sv:uvm-tree` reports them, inline on the affected node:

```text
└── agt : my_agent
    ├── drv : my_driver   [overridden → fast_driver]
    └── mon : my_monitor  [overridden → noisy_monitor under env.agt.* conditionally]
```

**Annotated, never resolved.** The tree goes on naming the type its `create`
call names. Printing `fast_driver` there would trade one confident wrong answer
for another: whether an override applies depends on whether its statement ran,
on any later override that replaced it, and — for an inst override — on a
hierarchical path that does not exist until elaboration.

### The five ways to write one

All five are read, and they are genuinely different call shapes rather than
spellings of one:

| Written as | Notes |
|---|---|
| `set_type_override_by_type(a::get_type(), b::get_type())` | the `uvm_component` convenience wrapper |
| `factory.set_type_override_by_type(...)` | the singleton — same method name, different declaring class |
| `set_type_override("a", "b")` | by name; the arguments are strings |
| `a::type_id::set_type_override(b::get_type())` | the registry form; the type being replaced is **not an argument** |
| `set_inst_override_by_type("env.agt.drv", a::get_type(), b::get_type())` | scoped to a path |

Two of those are worth dwelling on, because both are places a plausible
implementation goes wrong.

**Argument positions are read per method, not uniformly.** UVM's own orders
disagree: `uvm_component::set_inst_override_by_type` takes the path *first* and
`uvm_factory::set_inst_override_by_type` takes it *last*. A single "the path is
argument N" rule reports one of them with the path and the original type
swapped, and both spellings compile.

**The registry form names its original nowhere.**
`my_driver::type_id::set_type_override(fast::get_type())` has one argument. The
type being replaced is the specialization's own `Tname` — the same parameter a
`type_id::create` call is read from — so an extractor that only reads arguments
reports this override backwards.

### The typo the compiler accepts

```systemverilog
set_type_override("my_monitor", "noisy_moniter");   // noisy_monitor
```

The by-name forms take strings. That line compiles, elaborates and simulates;
the override silently never applies and the testbench quietly runs the type it
meant to replace. It is marked on the node (`— no such type`) and counted under
the tree.

The type-safe `::get_type()` forms cannot fail this way, which is the argument
for preferring them, and this view makes the difference visible rather than
asserting it.

(uvm-used-by)=
## `sv:uvm-used-by`

```rst
.. sv:uvm-used-by:: my_agent
```

Every component that builds this one — the inverse of `sv:uvm-tree`, and the
counterpart to [`sv:used-by`](structure) for RTL. On a component's own page it
answers the question the tree cannot: a tree shows what a component builds, and
a reader who arrived at `my_agent` wants to know who builds *it*, under what
handle, and whether that happens unconditionally.

| Option | Meaning |
|---|---|
| `:root:` | Root the search at a named test rather than the auto-detected one. |
| `:optional:` | Render nothing, and warn about nothing, if the component does not exist. |

A component nothing builds is a **finding**, not an empty table: a class
written, registered with the factory and never instantiated. It is reported as
such — and if it is the target of a factory override, that is reported next to
it, because a deliberate override target is not dead code.

(uvm-class-pages)=
## On a class's own page

Two facts are rendered by `autosvclass` rather than by a directive here, and
that is deliberate: they belong on a class page, which may name no testbench at
all, and they must survive an index that has been pickled and reloaded with the
live compilation gone. Both are derived from stored names, so they cost nothing
and need no provider.

**What the class is** appears as a badge beside its name:

```text
class my_agent  extends uvm_agent  [component]
```

`component`, `sequence`, `sequence item`, `TLM port` or `object`. The order
those are tested in matters: every sequence *is* a `uvm_sequence_item`, so a
naive reading labels every sequence a transaction. A class that has nothing to
do with UVM gets no badge, rather than a misleading one.

**Which phases it implements** appears as a field at the top of the content:

> **UVM phases:** `build_phase`, `connect_phase`, `run_phase`

Its own overrides only — a component inherits every phase method and overrides
two or three, and listing the inherited ones would say the same thing about
every component in the testbench. Ordered by *execution*, not alphabetically:
that is the order that answers "what does this do, and when". The run-time
schedule (`reset_phase`, `main_phase` and the rest) counts, because a component
using it uses it *instead of* `run_phase`.

(uvm-node-states)=
## Three states, and why there are three

Every component in a testbench tree is reported in one of three states. This is
the part of the design worth understanding before anything else, because it is
what makes the output trustworthy.

`ok`
: The type resolved and the walk descended into it.

`opaque`
: A deliberate boundary — see [black-boxing](uvm-blackbox). The node is real
  and labelled; its contents were not looked at.

`unresolved`
: The type did not resolve, because its package was not parsed or does not
  exist. The node is real and its declared type name is reported, but nothing
  below it is known.

The alternative — dropping what cannot be resolved — produces a tree that
*looks* complete and is not. A reader has no way to tell a testbench with no
register model from one whose register model failed to parse, and the second
case is a build problem being hidden by the tool meant to explain it. So
unresolved components are shown, counted, and marked.

(uvm-blackbox)=
## Black-boxing

Some of a testbench legitimately should not be walked into:

- **Code that does not exist yet.** A register model generated from RDL or
  IP-XACT may simply be absent when the docs build, especially in CI.
- **Vendor VIP**, delivered as an encrypted or precompiled library.
- **The UVM library itself.** `uvm_component`'s own internals are noise in a
  document about *your* testbench, so they are always stopped at.

Two configuration values control the rest:

```python
# conf.py

# Glob patterns matched against a component's type name.
sv_uvm_blackbox = ["*_reg_block", "acme_vip_*"]

# Matched against the base-class chain, so one entry covers a whole family.
sv_uvm_blackbox_bases = ["uvm_reg_block"]   # the default
```

`sv_uvm_blackbox_bases` defaults to `["uvm_reg_block"]` because a register model
is the single most common thing to be generated rather than written, and so the
most common thing to be missing at doc time.

A black-boxed component is rendered as an `opaque` node — present, named and
counted. It is never dropped: the point of the setting is to say "stop here",
not "pretend this is not here".

## Configuration reference

| Value | Default | Meaning |
|---|---|---|
| `sv_uvm_root` | `""` | Root component type to elaborate from. Empty auto-detects from the `run_test("...")` argument in a top module. |
| `sv_uvm_blackbox` | `[]` | Glob patterns on the component type name. |
| `sv_uvm_blackbox_bases` | `["uvm_reg_block"]` | Base-class names; matches the whole chain. |
| `sv_uvm_tree_depth` | `4` | Default depth for `sv:uvm-tree`. `test → env → agent → driver` is 4. |
| `sv_uvm_max_components` | `5000` | Ceiling on components visited. Exceeding it reports truncation rather than hanging the build. |
| `sv_uvm_warn_orphans` | `False` | Also emit build warnings for orphaned `config_db` fields. See [above](uvm-orphan-caveats). |

## Cost

Nothing here is computed unless a UVM directive asks for it. Extracting the
component hierarchy means visiting every `build_phase` in the project, so an
RTL-only project — or any page that does not use one of these directives — pays
nothing at all. When a directive does ask, the extraction happens once per build
and is shared by every page.

The component hierarchy and the `config_db` scan are separate costs, and asking
for one does not compute the other: a page with only a config table never walks
a single `build_phase`.

`sv:uvm-schematic` reads no second structure: connections and TLM ports are
extracted alongside the components, once per component type, during the same
walk `sv:uvm-tree` uses. A tree and a schematic **rooted at the same component**
therefore cost one walk between them. Naming different roots costs one walk
each, since the memo is per root.

`sv:uvm-sequence` is a third, independent cost, and the cheapest of them: it
reads one `body()` per sequence named, memoized per sequence. A page with only
an activity diagram never walks a `build_phase` at all.

Factory overrides are not a further cost either: they ride the same expression
walk as the `config_db` scan, because descending into if-conditions is the hard
part and it is identical for both. A page with an annotated tree and a config
table pays for one scan.

`sv:uvm-binding` is not a fourth. It is built on the `config_db` scan and adds
only a look at the scope each bound interface is declared in — so a page with
both tables scans once. In particular it does **not** walk the RTL hierarchy:
the join descends one hierarchical name rather than searching for it, which is
what keeps a binding table cheap on a design where the hierarchy walk would not
be.

This is the same lazy contract the [design structure](structure) directives use,
and for the same reason.
