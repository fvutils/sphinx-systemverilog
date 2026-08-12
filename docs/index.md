# sphinx-systemverilog

A [Sphinx](https://www.sphinx-doc.org) autodoc extension for **SystemVerilog**,
powered by the [`pyslang`](https://github.com/MikePopoloski/slang) parser.

It documents SystemVerilog source the way `sphinx.ext.autodoc` documents Python:
declarations and their doc comments are pulled directly from source. Multiple
comment dialects are supported — a Python-docstring-like *native* style today,
with NaturalDocs and Doxygen on the roadmap.

```{toctree}
:maxdepth: 2
:caption: Usage

getting-started
usage/directives
usage/signatures
usage/native-style
usage/naturaldocs-style
usage/doxygen-style
usage/modules
usage/diagrams
usage/whole-tree
usage/cross-referencing
usage/advanced
```

```{toctree}
:maxdepth: 1
:caption: Examples

examples/sample
examples/naturaldocs
examples/uvm
```

```{toctree}
:maxdepth: 2
:caption: UVM reference

uvm/index
```

## Status

All planned phases (1–5) are implemented: the `native`, `naturaldocs` and
`doxygen` dialects with auto-detection, classes/packages/modules (with ports &
parameters), the core domain + autodoc machinery, inheritance and instance
diagrams, whole-tree documentation, and — as of Phase 5 — structured signature
rendering with parameter lists, automatic type cross-links, and objects in the
table of contents. See the design and implementation plan under `docs/design/`
in the repository.

## Indices

- {ref}`genindex`
- {ref}`search`
