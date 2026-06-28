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
| `:exclude:` | drop the named objects |
| `:members:` / `:undoc-members:` / `:member-order:` | as for `autosvclass` |
| `:doc-style:` | dialect override |

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
