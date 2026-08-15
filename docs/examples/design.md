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
