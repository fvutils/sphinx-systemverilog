# Advanced constructs & performance

## Macros

`` `define `` macros are documented automatically, with the doc comment that
precedes them. They appear as `sv:macro` objects and can be documented with
`autosvsummary`:

```rst
.. autosvsummary::
   :kinds: macro
```

Each macro shows its definition (name, formal arguments, and a short body):

```{eval-rst}
.. autosvsummary::
   :kinds: macro
   :files: macros.svh
```

Disable macro extraction with:

```python
sv_document_macros = False
```

> Note: include guards (e.g. `` `define MY_PKG_SVH ``) are extracted like any
> other macro; narrow with `:exclude:` or a name glob if you don't want them.

A short macro body is shown in the signature (`` `define WIDTH 32 ``). For a
library whose macros' expansions are not part of its API, show bodies only for
constants, the macros without formals:

```python
sv_macro_body = "constants"      # or "none"; the default is "short"
```

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

So the hierarchy is walked **once per change of the sources**, when the
[design database](database.md) is built:

- A build of unchanged sources reuses the cached database and walks nothing.
- Every structural directive, on any page and in any process, reads that one
  walk.
- The walk is bounded by the settings below, so a pathological design costs a
  truncated walk, not a hung build.

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

The hierarchy is walked once, while the front end builds its database (see
[](database.md)), and stored beside it. Every process reads that copy:

- On an **incremental rebuild** of unchanged sources, the cached database is
  reused, so nothing is parsed or walked.
- Under **parallel builds** (`-j`), workers read the stored copy and walk
  nothing.

A UVM directive that names its own root (`:root:`) is the exception until the
testbench moves into the database: a process that has not parsed the sources
parses them once to answer it.

## Performance

The whole source set is parsed into a [design database](database.md), which is
cached between builds and keyed by source-file modification times, so builds
that repeat (`sphinx-autobuild`, CI on a docs-only change) parse only when
sources actually change. As a reference point, the complete UVM library (~6200
documented objects) parses and is written to the database in a few seconds.
