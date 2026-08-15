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
hierarchy from the elaborated design. See [Diagrams](diagrams.md) for what it
covers, and [Elaboration cost](elaboration-cost) below for what it costs.

(elaboration-cost)=
## Elaboration cost

Parsing SystemVerilog is cheap. **Walking the instance hierarchy is not** — and
the two are easy to confuse, because both are "using the parser".

Measured against a synthetic design of 4680 instances:

| Step | Cost |
|---|---|
| Parse every file, resolve declarations, build the index | ~0.002 s |
| Walk the elaborated instance hierarchy | ~0.6 s |

The gap widens with design size, because the hierarchy is what multiplies: a
generate loop is one line of source and a thousand instances.

So the hierarchy is walked **only when something asks for it**:

- Building the index never walks it, no matter how large the design.
- The first structural directive on any page triggers the walk.
- Every later structural directive, on any page, reuses that one walk.
- A project that documents only classes and packages — a verification library,
  say — never pays any of it.

If no page in your project uses a structural directive, the cost is zero. You do
not need to configure anything to get that; it is the default.

### When a large design is still too slow

Two escape hatches, both applying only to the walk:

```python
# Only elaborate these tops (default: every elaborated top).
sv_structure_tops = ["soc_top"]

# Stop walking after this many instances (default: 20000).
sv_structure_max_instances = 20000
```

Hitting the instance ceiling is always reported, never silent: the diagram
renders what was walked and the build warns that it was truncated. Prefer
narrowing `sv_structure_tops` over raising the ceiling — a testbench top that
pulls in the whole DUT is usually not the thing you meant to diagram.

### Incremental and parallel builds

The elaborated design cannot be stored in Sphinx's cached environment, so it is
recomputed in whichever process needs it, and only there:

- On an **incremental rebuild**, unchanged pages reuse their cached doctrees, so
  structural directives do not re-run and nothing is walked.
- Under **parallel builds** (`-j`), each worker that renders a structural
  directive walks independently. Workers that render none walk nothing. This is
  a deliberate trade: sharing the elaborated design across processes would cost
  more than recomputing it.

If a structural directive ever reports that the elaborated design is
unavailable, a full rebuild (`sphinx-build -E`) restores it.

## Performance

The whole source set is parsed **once per build** into a shared index. Within a
single process, the index is additionally cached and keyed by source-file
modification times, so tools that rebuild repeatedly (e.g.
`sphinx-autobuild`) re-parse only when sources actually change. As a reference
point, the complete UVM library (~5700 documented objects) parses in a few
seconds.
