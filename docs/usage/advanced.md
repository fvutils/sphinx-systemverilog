# Advanced constructs & performance

## Macros

`` `define `` macros are documented automatically, with the doc comment that
precedes them. They appear as `sv:macro` objects and can be documented with
`autosvsummary`:

```rst
.. autosvsummary::
   :kinds: macro
```

Each macro shows its definition (name, formal arguments, and a short body).
Disable macro extraction with:

```python
sv_document_macros = False
```

> Note: include guards (e.g. `` `define MY_PKG_SVH ``) are extracted like any
> other macro; narrow with `:exclude:` or a name glob if you don't want them.

## Covergroups & constraints

Inside a class, **covergroups** (with their coverpoints) and **constraint
blocks** are documented as first-class members:

```{eval-rst}
.. autosvclass:: cov_pkg::cov_item
   :members:
```

Covergroups render with kind `covergroup` and their coverpoints nested beneath;
constraints render as `constraint <name>`. Both pick up their leading doc
comments.

## Structural instance diagrams

For RTL designs, `sv:instance-diagram` renders a module's instantiation
hierarchy (which module instantiates which), using the elaborated design:

```rst
.. sv:instance-diagram:: rtl_top
```

Edges are labeled with the instance name; the target module is highlighted.
Like inheritance diagrams, this needs Graphviz's `dot` and degrades gracefully
without it. The directive only works for modules that participate in an
elaborated hierarchy (a top-level design module and its children).

## Performance

The whole source set is parsed **once per build** into a shared index. Within a
single process, the index is additionally cached and keyed by source-file
modification times, so tools that rebuild repeatedly (e.g.
`sphinx-autobuild`) re-parse only when sources actually change. As a reference
point, the complete UVM library (~5700 documented objects) parses in a few
seconds.
