# Example: a UVM testbench

Everything on this page is extracted live from
[`tests/fixtures/uvm_tb/`](https://github.com/fvutils/sphinx-systemverilog/tree/main/tests/fixtures/uvm_tb)
during this documentation build — the same source the test suite asserts
against. Nothing here is hand-written illustration.

The testbenches are written against a ~250-line stand-in for UVM rather than the
real library, which is why this page renders identically whether or not UVM is
installed. The mechanism being demonstrated — the
`uvm_component_registry #(T, Tname)` factory typedef — is the real one either
way, and the [corpus tests](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/corpus/test_uvm_tb_corpus.py)
verify it against the genuine library.

## The component tree

```rst
.. sv:uvm-tree:: my_test
```

```{eval-rst}
.. sv:uvm-tree:: my_test
```

Read that output against
[the source](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/basic_tb.sv),
because several of the annotations are the point of the whole feature:

`drv` and `seqr` are marked `[conditional]`
: They are built inside `if (is_active)`. They are almost always present in a
  real run, and the source does not say they always are. Showing them plainly
  would assert something the code does not.

`extra` is marked `(×N)`
: It is built in `for (int i = 0; i < n_extra; i++)`, and `n_extra` is a
  variable. There is no constant to fold, so no number is invented — even
  though the array is declared `my_agent extra[4]` and guessing `4` would look
  right here. It would stop being right the moment the count came from
  `config_db`, which is the normal way to write it.

`cov` is built with `new` rather than the factory
: A different expression kind entirely (`NewClass`, not a call). A walker
  looking only at calls would drop it silently.

`agt_a` and `agt_b` are listed separately
: They are two creation sites. `:collapse:` folds siblings that differ only in
  name.

## Depth and collapsing

```rst
.. sv:uvm-tree:: my_test
   :depth: 2
   :collapse:
```

```{eval-rst}
.. sv:uvm-tree:: my_test
   :depth: 2
   :collapse:
```

The note under the tree is not decoration. A view that stopped at depth 2 and
said nothing would read as "this testbench is two levels deep".

## Boundaries

`blackbox_tb.sv` is the case where part of a testbench should not be walked
into. This build sets:

```python
sv_uvm_blackbox = ["acme_vip_*"]        # vendor VIP
# sv_uvm_blackbox_bases defaults to ["uvm_reg_block"]
```

```{eval-rst}
.. sv:uvm-tree:: bb_test
```

Both `ral` and `vip` are present, named, and marked `[opaque]`. The register
model's fields and the VIP's driver exist and are not shown — that is the
request being honoured. What is *not* happening is the tree quietly ending at
`bb_env` with three children unaccounted for.

## Unresolved components

There is a third state, and it is the reason the other two are labelled rather
than merely omitted. When a component's type cannot be resolved at all — a RAL
package generated from RDL that has not been generated yet, a vendor package
absent from the doc build — slang discards the statement that used it. The
`create` call is not in the AST, and a walk that reads only `build_phase` would
report a tree that is short by exactly those components while looking perfectly
healthy.

That case is not rendered live here, because demonstrating it would mean putting
deliberate compilation errors into this project's own documentation build. The
[test fixture](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/missing_dep_tb.sv)
covers it, and the output looks like this:

```text
reg_test
└── env : reg_env
    ├── agt : good_agent
    └── ral : my_reg_block  [unresolved]
```

with the note:

> *1 component(s) could not be resolved (my_reg_block). Their types are not
> present in the parsed sources, so nothing below them is known. This usually
> means a generated or vendor package was not available when the docs were
> built.*

`[opaque]` and `[unresolved]` are deliberately different words. The first means
the tool was told to stop; the second means it could not get there. Collapsing
them would let a genuine build failure render as an editorial choice.

## Configuration, and what nothing reads

`config_tb.sv` is a second small testbench, written to put every shape of
`config_db` access in one place.

```rst
.. sv:uvm-config::
```

```{eval-rst}
.. sv:uvm-config::
```

The row worth looking at is `n_itmes`.

It is a typo for `n_items`, and it is
[in the fixture on purpose](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/config_tb.sv).
That line compiles. It elaborates. It simulates. `cfg_driver` never sees the
value, keeps its default, and the testbench quietly tests something other than
what was meant — with no error, no warning, and nothing in a log to grep for.
It is the most common silent bug in UVM code, and the reason is simply that the
field name is a string and nothing checks strings.

Two rows next to it are the ones a careless detector would get wrong:

`n_*` is **not** flagged
: UVM allows a glob on either side, so `set("n_*")` really can reach
  `get("n_items")`. Matching is glob-aware in both directions.

the `(computed)` row is **not** flagged
: Its field name is built with `$sformatf`, so it cannot be paired at all.
  Calling it unread would be an invention — and treating it as matching
  everything, the maximally conservative choice, would clear every orphan on
  this page. It is set aside, and the note under the table says how many were.

Below the table, `unset_depth` is reported from the other direction: `cfg_driver`
reads it and nothing anywhere sets it, so that knob can never be turned.

### Scope is shown, and not used

`cfg_agent` sets `mode` with a scope of `*`, and `cfg_tb_top` sets `vif` with an
absolute `uvm_test_top`. Both are in the table; neither takes part in the
matching. The full scope of a `set` is `{cntxt, ".", inst_name}`, and `cntxt` is
`this` — a different path in every testbench that instantiates the agent. Using
it could only narrow the match, and a narrower match manufactures orphans that
are not there.

### The setting that lives outside every component

The `vif` row is set by `cfg_tb_top`, with a `cntxt` of `null`. That access is
in an `initial` block in a module, not in any component, which is why the scan
is project-wide rather than rooted at a test. Its value column reads `u_if` —
the actual RTL interface instance, resolved to the same elaborated design the
[design structure](../usage/structure) directives walk.

## The schematic

`tlm_tb.sv` is a third testbench, shaped like the one the layout was prototyped
against: an env with two agents, a scoreboard, a coverage collector and a
virtual sequencer.

```rst
.. sv:uvm-schematic:: tlm_env
```

```{eval-rst}
.. sv:uvm-schematic:: tlm_env
```

Read it against
[the source](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/tlm_tb.sv).
Four things in that picture are the point of the feature:

The scoreboard is **above** the agents
: This is the whole reason the layout work exists. Graphviz treats every edge
  as a ranking constraint, so the analysis edge running from `mon.ap` up to
  `sb.aimp` would ordinarily drag `sb` down among the agents — which is exactly
  the failure a published attempt at this diagram ran into. Every TLM edge here
  carries `constraint=false`, so connectivity decorates the layout instead of
  deciding it.

The agents are clusters, **and** pinned to a tier
: Graphviz's default ranking cannot express that: a node cannot be inside a
  cluster and also `rank=same` with a node outside it. `newrank=true` is what
  removes the restriction, and without it this diagram is not merely uglier, it
  is inexpressible.

`vseqr` has edges at all
: Its wiring is `vseqr.seqr_a = agt_a.seqr` — an assignment, not a
  `connect` call. A walker reading only calls would draw the one component
  whose entire purpose is its connections with none.

`drv` shows `seq_item_port` and not `rsp_port`
: Neither is declared by `tlm_driver`; both come from `uvm_driver`. One is
  connected and one is not, and the note under the diagram says how many were
  left off. This rule exists because of the
  [corpus test](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/corpus/test_uvm_tb_corpus.py):
  against real UVM a driver arrives with *three* ports it never declared, and
  labelling all of them would be labelling plumbing.

Both agents are drawn from one `tlm_agent`, and each gets its own
sequencer-to-driver edge, because the source describes the type and each
instance really makes the connection. Those edges are dotted: the agent wires
them under `if (is_active)`.

### Nothing here was configured

The tier each component sits in comes from what it extends —
`uvm_sequencer` on top, `uvm_scoreboard` and `uvm_subscriber` in the middle,
`uvm_agent` at the bottom. The directive above has no options. `:tier:` and
`:order:` exist for the exceptions, and a diagram that needed them to look like
this would be a diagram nobody kept using.

## The sequence

`seq_tb.sv` is a fourth testbench, written to put every activity construct in
one `body()`.

```rst
.. sv:uvm-sequence:: main_seq
```

```{eval-rst}
.. sv:uvm-sequence:: main_seq
```

Read it against
[the source](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/seq_tb.sv).

The `if` has two arms
: Only one is written — there is no `else`. Drawing only the arm that exists
  would say the branch always runs, which is the one thing a static reading
  cannot know.

The join bar says `join_any`
: Not inferred, and not guessed from the fixture's name.
  `StatementBlockKind` distinguishes all four flavours, so the bar reports what
  the source wrote. A `join_none` elsewhere in the fixture gets no join bar at
  all: those branches genuinely do not rejoin.

The fork branches are called `traffic` and `timeout`
: Those are the names in the source — `begin : traffic`. Engineers already name
  fork branches descriptively, and the labels survive elaboration, so the
  diagram gets human-authored names for free rather than "branch 1" and
  "branch 2".

The loop says `repeat (n_bursts)`
: `n_bursts` is a variable, so there is no number to fold and none is invented.
  This is the same rule the tree applies to `(×N)`, for the same reason.

Underneath, three statements are reported as not drawn. They are an assignment
and two `$display` calls — real lines of a real `body()`, and none of them
control flow. A diagram that showed its four constructs and said nothing about
the rest would be claiming the task is four steps long.

### One level down

```rst
.. sv:uvm-sequence:: main_seq
   :depth: 2
```

```{eval-rst}
.. sv:uvm-sequence:: main_seq
   :depth: 2
```

Each sub-sequence opens into its own body. `traf_seq` uses the `` `mini_do ``
macro — a stand-in for `` `uvm_do `` — which expands to seven statements for one
line of source, and appears here as the single transaction it means, labelled
with the macro so a reader looking for `start_item` knows where it went.

That collapse is the one rule on this page the stub could not have justified on
its own. Against real UVM the macro expands to a `$cast` branch that starts a
`uvm_sequence_base` local *beside* the `start_item` naming your type, so there
are two candidates and the library-typed one has to lose. `` `mini_do `` offers
exactly one, so a rule that simply took the first would pass every fast test.
The [corpus test](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/corpus/test_uvm_tb_corpus.py)
is what holds it.

## The bridge to the RTL

`bridge_tb.sv` is a fourth testbench, and the only fixture on this page that
contains RTL as well as classes: an interface, a DUT, a passive probe, and a top
module that hands the interface to the testbench.

```rst
.. sv:uvm-binding:: bridge_*
```

```{eval-rst}
.. sv:uvm-binding:: bridge_*
```

The first row is the whole point of the table. Read left to right it says: the
top module files `bridge_tb_top.u_bus` under the field `vif`; that interface
instance is connected to `bridge_tb_top.u_dut` and `bridge_tb_top.u_probe`; and
`bridge_agent` and `bridge_test` read it back. Neither half of that sentence
references the other in the source. The only thing they share is the string
`"vif"`.

The RTL end is a live cross-reference. Documenting the two modules involved is
enough to make the *Connects to* column clickable:

```rst
.. autosvmodule:: bridge_dut
.. autosvmodule:: bridge_probe
```

```{eval-rst}
.. autosvmodule:: bridge_dut
.. autosvmodule:: bridge_probe
```

A reader who arrives at `bridge_agent` wondering what it actually drives can now
get to the module's own documentation without leaving the table. That is the
join `U5` exists for, and it is only possible because this extension elaborates
the RTL and the testbench into the same index.

The argument globs the interface type. It is used here because this doc set
compiles four unrelated fixture testbenches into one index, and `cfg_tb.sv` has
a `vif` of its own — which is a page-layout concern rather than a limitation.
Pairing is not confused by it: `uvm_config_db#(T)` is keyed on `T`, so the two
`vif` fields are correctly kept apart by their interface types.

### The three rows underneath it

Each of the remaining rows is a failure that no compiler reports and no
simulator reports until it is far too late.

`clk_vif`
: Set correctly, wired to real RTL, and read by nothing — the field name
  matches no `get` in the project. Unlike an ordinary `config_db` typo, which
  leaves a component on its default, this one leaves it holding null.

`spare_vif`
: Handed to the testbench correctly and connected to no RTL at all. The binding
  is fine; the testbench would be driving air. Note the cell reads `(nothing)`
  rather than being blank — an empty cell reads as "not analysed", and the
  finding here is that the analysis ran and the answer is none.

`vif_alias`
: The value is a virtual-interface *handle* rather than an interface instance,
  so there is no RTL instance to name. It says so instead of guessing: which
  interface that handle holds is decided when `bridge_agent`'s own `get`
  succeeds, which is a property of the run.

### The part that is bounded, and says so

The note under the table states the scope of the RTL side: the instances
declared in the interface's own scope. An interface passed further down through
a port reaches deeper modules too, and chasing it would mean walking the whole
hierarchy for an answer that is nearly always the same one. Within its scope the
result is exact — `u_probe` connects through a modport (`.bus(u_bus.mon_mp)`)
and is still resolved to the interface instance, and `bridge_dut`'s `rst` port
is correctly not mistaken for a binding.

## When the tree is lying to you

`override_tb.sv` is the last fixture on this page, and it exists to show the one
construct that makes everything above it untrustworthy. Read the tree first:

```rst
.. sv:uvm-tree:: ovr_test
```

```{eval-rst}
.. sv:uvm-tree:: ovr_test
```

Every `create` call in
[that source](https://github.com/fvutils/sphinx-systemverilog/blob/main/tests/fixtures/uvm_tb/override_tb.sv)
names the type the tree names. None of them is necessarily what runs.

`drv : ovr_driver`
: Overridden twice — globally, and again under `env.agt.drv`. The tree still
  says `ovr_driver`, because that is what the agent's source says. Substituting
  `fast_driver` would be a claim about a simulation: whether an override applies
  depends on whether its statement ran, on any later override, and for the inst
  form on a hierarchical path that does not exist until elaboration.

`mon : ovr_monitor`
: Overridden twice more, and one of the two **never fires**. It is written
  `set_type_override("ovr_monitor", "noisy_moniter")` — a typo for
  `noisy_monitor`. The by-name form takes strings, so that line compiles,
  elaborates and simulates, and the testbench quietly keeps the monitor it meant
  to replace. It is marked `— no such type` on the node and counted underneath.

The four overrides above are written four different ways, on purpose: the
component convenience wrapper, the factory singleton, the by-name form, and the
registry form. They are different call shapes rather than different spellings —
the registry form names the type it replaces *nowhere in its arguments*, and
UVM's two inst forms take the path at opposite ends of their argument lists. See
[Factory overrides](uvm-overrides).

### The other direction

```rst
.. sv:uvm-used-by:: ovr_driver
   :root: ovr_test
```

```{eval-rst}
.. sv:uvm-used-by:: ovr_driver
   :root: ovr_test
```

`:root:` is named because this doc set compiles five unrelated fixture
testbenches into one index; auto-detection picks one, and it is not this one.

And the case that reads as nothing but is a finding:

```{eval-rst}
.. sv:uvm-used-by:: fast_driver
   :root: ovr_test
```

`fast_driver` is built by nobody, by name. It is not dead code — it is what
`ovr_driver` becomes when the override fires, and the note says so rather than
leaving a reader to conclude the class is unused.

### On the class's own page

```rst
.. autosvclass:: ovr_agent
```

```{eval-rst}
.. autosvclass:: ovr_agent
```

The `[component]` badge and the phase list are rendered by `autosvclass`, not by
any directive above — they work on a page that names no testbench, and on an
index reloaded from Sphinx's cache with the live compilation gone.

## What this is not

```{note}
The tree is the hierarchy **as written in `build_phase`**. It is not a
simulation trace. Factory overrides, config-driven counts and dynamically named
components are reported as such rather than resolved.
```

See [UVM testbenches](../usage/uvm-testbench) for the directive reference and
the configuration values.
