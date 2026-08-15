# Diagrams

Two kinds of diagram are available: **inheritance diagrams** for class
hierarchies, and **instance diagrams** for the structural composition of a
design. Both render with
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
