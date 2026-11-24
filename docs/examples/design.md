# Example: an RTL design

Everything on this page is generated from `tests/fixtures/design/` — a small but
structurally complete design: a top, an if-generate that branches on a
parameter, a for-generate loop, an instance array, and one module elaborated at
two different widths.

The source is five short files. None of them, on its own, contains any of the
information below.

```systemverilog
// lane.sv — a generate loop and an instance array
module lane #(parameter int W = 8, parameter int LANES = 2) (...);
  generate
    for (genvar g = 0; g < LANES; g++) begin : g_lp
      leaf #(.W(W)) u_g (...);
    end
  endgenerate

  leaf #(.W(W)) u_l [3:0] (...);
endmodule
```

## What the design is built from

```{eval-rst}
.. sv:instance-tree:: soc
```

Note what this shows that the source does not: `u_narrow` and `u_wide` are the
same module, `cluster`, but they elaborate to **different children** because
their if-generate branches on the `WIDE` parameter. The `#(W=32)` values are
resolved, not copied from the instantiation text.

### Folding identical siblings

`soc` has no two children alike, so `:collapse:` would change nothing there.
A second fixture, `tests/fixtures/design_collapse/`, does — `cl_mid` holds three
identical `cl_leaf` instances plus one that differs only by parameter:

```{eval-rst}
.. sv:instance-tree:: cl_top
```

With `:collapse:`:

```{eval-rst}
.. sv:instance-tree:: cl_top
   :collapse:
```

The folded entries are **named**, not merely counted, and `u_wide` stays on its
own line because its parameter differs — which is precisely the difference worth
seeing.

## What uses `leaf`

`leaf.sv` is 15 lines and says nothing about who instantiates it. The elaborated
design says this:

```{eval-rst}
.. sv:used-by:: leaf
```

Four of those come from a single line inside a generate loop, and one stands for
all four elements of an instance array.

## Which parameter values are in use

```{eval-rst}
.. sv:parameter-matrix:: leaf
```

## The same views on a module page

```rst
.. autosvmodule:: lane
   :members:
   :show-instances:
   :show-used-by:
```

```{eval-rst}
.. autosvmodule:: lane
   :members:
   :show-instances:
   :show-used-by:
```

## As a diagram

The tree is text by default because it stays readable at depth. For a shallow
structural overview a picture can be clearer:

```{eval-rst}
.. sv:instance-tree:: soc
   :diagram:
```

## What is connected to what

The instance tree says what a module is built from; `sv:block-diagram` says how
the parts are wired. It draws one module: its child instances as boxes, its own
ports on the border, and each net as an edge from the port that drives it to
the ports that read it. This one is drawn from `tests/fixtures/rtl_block/`, a
four-stage pipeline with a controller feeding back into it:

```{eval-rst}
.. sv:block-diagram:: pipe_top
```

Four things in that picture come from the database rather than from reading
the instantiations one by one:

- **Every connection style resolves to the same nets.** `u_fetch` connects
  `.clk` implicitly and `u_ctrl` connects everything with `.*`; both are drawn
  like the named connections around them.
- **Directions come from the child modules**, so outputs sit on the right of a
  box and inputs on the left, and the `stall` and `flush` feedback from
  `u_ctrl` runs back against the flow.
- **The interface port `cfg`** is drawn as one thick, undirected connection
  rather than as its signals.
- **`pc_in` has no driver in the picture**, because it is driven by an
  `assign` in `pipe_top`, which the database doesn't record. The note under
  the diagram says so rather than leaving a silent gap.

Clocks and resets are hidden by default: they reach every block and say nothing
about the dataflow.

### Bundled

A real module has far more nets than this one. `:connections: bundled` merges
every net from one block to another into one bus, labelled with the source and
its signal count and width (`u_fetch (3, 65b)`: three signals, 65 bits). The
module itself counts as a block. Above about 40 nets this is what the default
picks; here it is asked for explicitly:

```{eval-rst}
.. sv:block-diagram:: pipe_top
   :connections: bundled
   :order: u_fetch, u_decode, u_exec
```

`:order:` lists the blocks in the order the data flows through them. Feedback
paths make a pipeline cyclic, and the layout breaks those cycles in that order,
so the main path reads left to right.

Both pictures respond to the mouse. Click a wire or a port to follow its net,
and double-click the `u_fetch (3, 65b)` bus to open it into `instr`,
`instr_valid` and `pc`, each between its own ports; double-click one of those to
close it again. See [In the browser](diagram-interaction) for the rest.
