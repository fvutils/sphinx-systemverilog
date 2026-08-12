# Example: documenting UVM

The extension documents the full [UVM](https://www.accellera.org/) library
end-to-end from its NaturalDocs-commented source — the project's Phase-2
acceptance target. A real build produces ~5,200 documented objects, 288 of them
classes, in a few seconds.

The result is published as its own section: **{doc}`../uvm/index`**. This page
covers the configuration that produces it and what to expect from a library of
that size.

## Configuration

Point the extension at `uvm_pkg.sv` as the build-unit root, with the UVM source
directory on the include path:

```python
extensions = ["sphinx_systemverilog"]

sv_build_units  = ["/path/to/uvm/src/uvm_pkg.sv"]
sv_include_dirs = ["/path/to/uvm/src"]
sv_doc_style    = "naturaldocs"
```

`uvm_pkg.sv` `` `include ``s the entire library, so a single build unit
elaborates all of UVM into one project-wide index.

What you get:

- **Inheritance** — `uvm_object extends uvm_void`, `uvm_component extends
  uvm_report_object`, etc., with {doc}`inheritance diagrams <../usage/diagrams>`.
- **Members** — `extern` method prototypes (which UVM uses throughout) are
  documented with their signatures.
- **Groups** — UVM `Group:` headers (`Seeding`, `Identification`, …) become
  labeled subsections, and `:member-order: groups` renders members in that order.
- **Prose** — detached `// Function -- NODOCS -- name` blocks, separated from
  their prototypes by `@uvm-ieee` annotations, are associated correctly, with
  `<xref>` and `~code~` markup converted.

## Splitting a large library across pages

A single page holding 288 classes is unreadable and slow to load. Select each
page's slice of the index by source path, which for a library organized like UVM
partitions it with no per-class curation:

```rst
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :files: reg/*.svh, reg/sequences/*.svh
```

See {doc}`../usage/whole-tree` for the full set of scoping options, and
{doc}`../uvm/index` for how the eleven pages of the UVM reference divide it up.

## Diagnostics

UVM elaborates with many benign lint-style warnings (width truncation, dangling
`else`, …). These are **not** surfaced as build warnings; they are counted and
reported once at INFO level. Only genuine parse errors are surfaced.
