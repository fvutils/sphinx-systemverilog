# Diagrams

Four kinds of diagram are available: **inheritance diagrams** for class
hierarchies, **instance diagrams** for the structural composition of an RTL
design, **UVM schematics** for how a testbench's components are wired together,
and **UVM activity diagrams** for what a sequence does. All render with
[`sphinx.ext.graphviz`](https://www.sphinx-doc.org/en/master/usage/extensions/graphviz.html).

## Prerequisite

Graphviz's `dot` executable must be installed and on `PATH`:

```bash
# Debian/Ubuntu
sudo apt-get install graphviz
```

If `dot` is missing, the build still succeeds — the diagram is skipped with a
warning rather than failing.

## Inheritance diagrams

Class inheritance diagrams use the `extends` relationships resolved from your
source.

Add `:show-inheritance:` to an `autosvclass` directive:

```rst
.. autosvclass:: nd_pkg::nd_leaf
   :members:
   :show-inheritance:
```

Or place a diagram anywhere with the standalone directive:

```rst
.. sv:inheritance-diagram:: nd_pkg::nd_leaf
```

The diagram shows the target class (highlighted), its chain of base classes, and
any classes that derive from it, with arrows pointing from derived to base.

> Because base classes must be resolvable to draw an edge, parse the **whole**
> class set together (e.g. via `sv_build_units` rooted at a package), so
> cross-file bases resolve.

## Instance diagrams

For RTL, `sv:instance-diagram` renders which module instantiates which, taken
from the **elaborated** design rather than from the text of the source:

```rst
.. sv:instance-diagram:: rtl_top
```

Edges are labeled with the instance name; the target module is highlighted. The
directive works for modules that participate in an elaborated hierarchy — a
top-level design module and its children.

### What counts as a child

Because the hierarchy comes from elaboration, the diagram reflects the design
that actually exists rather than the one the source appears to describe:

- **Generate blocks are included.** Instances inside `generate` / `for` /
  `if` blocks are labeled with their generate path, e.g. `g_lp[*].u_g`. A
  `for`-generate is one line of source and is drawn once, with the iteration
  count folded into the label.
- **Instance arrays are included.** `leaf u_l [3:0] (...)` is drawn once as
  `u_l[3:0] (×4)`.
- **Branches that did not elaborate are excluded.** The untaken side of an
  `if`-generate is not part of the design, so it is not drawn. A module
  instantiated under two different parameterizations may therefore contribute
  different children in each.
- **Parameters are resolved.** `#(.W(BUS_W))` reports the value `W` actually
  took, not the expression that produced it.

Earlier releases matched only plain instances at the top of a module body, so a
module whose children all sat inside a `generate` — a common shape in real RTL —
rendered as having no children at all. That is fixed.

### Cost

Reading the hierarchy means walking the elaborated design, which is by a wide
margin the most expensive thing this extension does. It happens **only when a
directive asks for it**, and at most once per build. See
[Elaboration cost](elaboration-cost) if your design is large.

## UVM schematics

`sv:uvm-schematic` draws one level of a testbench: the components a container
builds, the TLM ports they declare, and the connections its `connect_phase`
makes.

```rst
.. sv:uvm-schematic:: my_env
```

Agents are drawn as clusters holding their own components; everything else is a
box with its ports on it. See [`sv:uvm-schematic`](uvm-schematic) for the
options and [the tier taxonomy](uvm-tiers).

### Why this diagram is laid out the way it is

Worth a paragraph, because a naive graph of the same data produces a picture
nobody recognizes. That is not hypothetical: a DVCon paper (O'Keeffe, Beattie &
Lorenzo, CréVinn) generated hierarchy diagrams with `dot` successfully and then
found its *connectivity* diagrams unreadable, concluding that "edges and edge
labels are not optimised". This layout was designed against that result.

The problem is that Graphviz treats every edge as a **ranking constraint**. An
analysis connection running from a monitor up to a scoreboard therefore ranks
the scoreboard *below* the monitor, dragging it down among the agents. The
diagram is correct and unreadable.

The fix is to separate structure from connectivity:

- containment decides the ranks;
- every TLM edge carries `constraint=false`, so it decorates the layout instead
  of fighting it;
- tiers are pinned with `rank=same`, which needs `newrank=true` because a node
  otherwise cannot be both inside a cluster and ranked with something outside
  it — and agents are asked to be exactly that;
- siblings are ordered with invisible weighted chains, which is what removes the
  remaining crossings.

`newrank` needs Graphviz 2.30 or later (released 2013). If the available `dot`
is older, the tier pinning is dropped and the rest is emitted unchanged — a
plainer layout rather than DOT your `dot` cannot lay out. The diagram says so
underneath when that happens.

## UVM sequence activity diagrams

`sv:uvm-sequence` draws one sequence's `body()` in UML activity notation:

```rst
.. sv:uvm-sequence:: main_seq
```

See [`sv:uvm-sequence`](uvm-sequence) for the options, the shape vocabulary and
the macro-collapse rule.

### The layout rule is the opposite one

Worth stating next to the section above, because the two diagrams reach
opposite conclusions from the same Graphviz behaviour.

A TLM connection is not an ordering, so letting it rank the nodes is what
produced the unreadable result the schematic is designed against — hence
`constraint=false` on every edge there.

A sequence's edges *are* an ordering. "This step happens after that one" is
precisely what a rank expresses, so the default behaviour is right and nothing
is switched off. Containment does not have to be rescued from connectivity here
because the two are the same thing.

The one exception is a loop's back-edge, which is a genuine cycle: left as a
constraint it drags the end of the body above its start, so it alone carries
`constraint=false`. That is the whole of what the schematic's layout work
contributes here.
