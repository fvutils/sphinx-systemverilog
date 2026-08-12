# Whole-tree documentation

`autosvsummary` documents an entire subtree of the project-wide index in one
directive — the "parse wide, reference scope" model. It is the project's
analog of Doxygen/Exhale's full-API-tree page.

## Basic use

Document everything that was parsed:

```rst
.. autosvsummary::
```

This renders every top-level package/module (and, by default, their members)
that the extension found in `sv_source_dirs` / `sv_build_units`.

## Narrowing the scope

| Option | Effect |
|---|---|
| *argument* (a glob) | only top-level names matching the glob, e.g. `uvm_*` |
| `:packages:` | restrict to objects within the named package(s) |
| `:kinds:` | only the given kinds (`class`, `module`, `package`, …) |
| `:files:` | restrict to declarations from source files matching a path glob |
| `:exclude:` | drop the named objects |
| `:members:` / `:undoc-members:` / `:member-order:` | as for `autosvclass` |
| `:doc-style:` | dialect override |
| `:optional:` | render nothing, silently, when the scope selects nothing |

Examples:

```rst
.. Document only the classes in two packages.
.. autosvsummary::
   :kinds: class
   :packages: my_pkg, my_other_pkg

.. Document every module whose name starts with "axi_".
.. autosvsummary:: axi_*
   :kinds: module
```

Because the whole source set is parsed once into a shared index, a large tree is
documented without re-parsing per directive.

## Splitting a library across pages

One page holding a few hundred classes is slow to load and impossible to
navigate. `:files:` selects a page's slice of the index by *where the code
lives*, which for a library with any directory discipline partitions it with no
per-class curation:

```rst
.. Page 1
.. autosvsummary::
   :kinds: class
   :files: reg/*.svh

.. Page 2
.. autosvsummary::
   :kinds: class
   :files: reg/sequences/*.svh
```

Path-glob semantics, chosen so two such pages cannot silently overlap:

| Pattern | Matches |
|---|---|
| `reg/*.svh` | files directly in any `reg/` directory — **not** `reg/sequences/x.svh` |
| `reg/**/*.svh` | `reg/` and every directory below it |
| `uvm_reg.svh` | that basename, wherever it sits |
| `/abs/path/src/reg/*.svh` | a pattern starting with `/` is anchored to the absolute path |

`*` and `?` stop at a `/`; `**` crosses directories. A relative pattern matches
a path *suffix* at a directory boundary, so the same directive works whatever
absolute path the sources sit at on a given machine.

The {doc}`UVM reference <../uvm/index>` is built this way: fourteen pages, 288
classes, no hand-maintained class list. A CI check compares the parsed index
against the built `objects.inv` so a class that falls between two patterns fails
the build rather than vanishing quietly (`scripts/check-docs-coverage.py`).
