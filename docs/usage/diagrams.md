# Diagrams

Five kinds of diagram are available: **inheritance diagrams** for class
hierarchies, **instance diagrams** for the structural composition of an RTL
design, **block diagrams** for how an RTL module's instances are wired,
**UVM schematics** for how a testbench's components are wired together, and
**UVM activity diagrams** for what a sequence does. Block diagrams, and UVM
schematics in HTML, are laid out with [ELK](https://eclipse.dev/elk/) and drawn
as inline SVG; the rest render with
[`sphinx.ext.graphviz`](https://www.sphinx-doc.org/en/master/usage/extensions/graphviz.html).

## Prerequisite

ELK needs nothing extra: elkjs ships inside the package and runs in an embedded
JavaScript engine (`mini-racer`, installed as a dependency). Graphviz's `dot`
executable is needed for the other diagrams, and for schematics in non-HTML
output (LaTeX/PDF, text). It must be installed and on `PATH`:

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
margin the most expensive thing this extension does. It happens once per
change of the sources, when the [design database](database.md) is built. See
[Elaboration cost](elaboration-cost) if your design is large.

(block-diagrams)=
## Block diagrams

`sv:block-diagram` draws how one module's parts are wired: its child instances
as boxes, its own ports on the border, and each net as an edge from the port
that drives it to the ports that read it.

```rst
.. sv:block-diagram:: pipe_top
   :connections: bundled
   :order: u_fetch, u_decode, u_exec
   :hide: ^(clk|rst)
```

| Option | Meaning |
|---|---|
| `:connections:` | `nets`: one edge per net, between the named ports. `bundled`: every net from one block to another merged into one bus, labelled with the source and its signal count and width; the module itself counts as a block. `auto` (the default): `nets` up to about 40 nets, `bundled` above. |
| `:order:` | Instance names in the order the data flows through them. Feedback makes a pipeline cyclic; the layout breaks the cycles in this order, so the main path reads left to right. |
| `:hide:` | A regular expression; nets whose name matches it are not drawn. The default hides clocks and resets (`clk…`, `rst…`, `…_clk`, `…_rst_n`, …). `none` shows everything. |

Inputs are on the left of a box, outputs on the right and inouts below.
Interface ports are drawn as one thick, undirected connection rather than as
their signals. Each box links to its module's page when that module is
documented.

What the diagram can't show, it says under the picture:

- **Nets driven by logic in the module** (an `assign` or a process) have no
  driver in the database, so their readers show an unconnected input and the
  note lists them.
- **Widths** come from the declared port type when its range is constant
  (`logic [31:0]`). A range over a parameter is not evaluated, so a bus with
  one leaves the bit count out of its label.

In HTML the diagram is interactive (see [below](diagram-interaction)), and in
a bundled diagram a bus opens up: double-click it to draw its signals
individually, each between its own ports, and double-click one of them to
fold the bus back.

The block diagram is laid out by ELK only, like the HTML schematic below.
There is no Graphviz version: `sv_diagram_layout = "graphviz"` doesn't apply
to it, and LaTeX and other non-HTML output show a one-line placeholder. See
[the example](../examples/design.md) for one drawn from a small pipeline.

## UVM schematics

`sv:uvm-schematic` draws one level of a testbench: the components a container
builds, the TLM ports they declare, and the connections its `connect_phase`
makes.

```rst
.. sv:uvm-schematic:: my_env
```

Agents are drawn as boxes holding their own components; everything else is a
box with its ports on it. Data flows left to right: a port that sends sits on a
box's right side, an export or imp that receives on its left, and a driver's
`seq_item_port` faces the sequencer it pulls from. See
[`sv:uvm-schematic`](uvm-schematic) for the options.

(uvm-schematic-layout)=
### Layout: ELK, with Graphviz as the fallback

In HTML the schematic is laid out by ELK's layered algorithm and written into
the page as SVG, so it follows the page's light or dark theme and its text can
be searched. ELK places boxes by their connections, routes edges at right
angles, and lets a connection end on an agent's own port or on the boundary of
the component being drawn. Graphviz can't draw either of those, because a
cluster has no ports. A dot marks where a fan-out splits, and each box links to
its class's documentation when that class is documented in the project.

The Graphviz drawing described below is still made. It is what LaTeX, text and
other non-HTML builders render, and what HTML falls back to when ELK can't run:
set `sv_diagram_layout = "graphviz"` in `conf.py` to choose it, or it is used
automatically, with a warning and a note under each diagram, when elkjs is
missing (a source checkout where `ivpm update` hasn't been run).

Layouts are cached in the build's doctree directory, keyed by the diagram's
content, so an unchanged schematic is not laid out again.

(diagram-interaction)=
### In the browser

Both the block diagram and the HTML schematic respond to the reader:

| Action | Effect |
|---|---|
| Click a wire or a port | Highlight its net end to end and fade the rest. Shift-click adds to the highlight; click the background, or press Escape, to clear it. |
| Double-click a bus (bundled block diagram) | Expand it into its signals; double-click a signal to fold it back. **Collapse** folds them all. |
| Toolbar (top right, on hover), or ctrl+wheel | Zoom in, zoom out, fit the frame, or actual size. |
| Drag the background | Pan. Large diagrams scroll inside a frame at most 80% of the window high. |

Without JavaScript the picture is the same static SVG. Expanding a bus lays
the diagram out again in the page, with the same elkjs and renderer the build
used, so the result looks like any other drawing. Only a diagram with buses
carries what that needs: its unlaid layout graph, embedded in the page (about
240 KiB for CVA6's `cva6_pipeline`). elkjs itself (1.6 MB, copied into
`_static` as `sv-diagram-elk.js`) is loaded the first time a reader expands
a bus, not with the page.

### Why the Graphviz layout is the way it is

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
