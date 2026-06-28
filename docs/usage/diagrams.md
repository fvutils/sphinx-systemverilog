# Inheritance diagrams

Class inheritance diagrams are rendered with
[`sphinx.ext.graphviz`](https://www.sphinx-doc.org/en/master/usage/extensions/graphviz.html),
using the `extends` relationships resolved from your source.

## Prerequisite

Graphviz's `dot` executable must be installed and on `PATH`:

```bash
# Debian/Ubuntu
sudo apt-get install graphviz
```

If `dot` is missing, the build still succeeds — the diagram is skipped with a
warning rather than failing.

## Usage

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
