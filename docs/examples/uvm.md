# Example: documenting UVM

The extension documents the full [UVM](https://www.accellera.org/) library
end-to-end from its NaturalDocs-commented source. This is the project's Phase-2
acceptance target and is exercised by the `corpus` test suite.

> This page describes the configuration and expected results rather than
> embedding the whole UVM reference, so the project's own documentation builds
> without the (large) UVM sources present. With the configuration below, a real
> build produces ~3700 documented objects in a few seconds.

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

## Documenting classes

```rst
.. autosvclass:: uvm_object
   :members:
   :show-inheritance:

.. autosvclass:: uvm_component
   :members:
```

What you get:

- **Inheritance** — `uvm_object extends uvm_void`, `uvm_component extends
  uvm_report_object`, etc., with an inheritance diagram.
- **Members** — `extern` method prototypes (which UVM uses throughout) are
  documented with their signatures.
- **Groups** — UVM `Group:` headers (`Seeding`, `Identification`, …) become
  labeled subsections.
- **Prose** — detached `// Function -- NODOCS -- name` blocks, separated from
  their prototypes by `@uvm-ieee` annotations, are associated correctly, with
  `<xref>` and `~code~` markup converted.

## Documenting the whole library at once

Rather than listing classes by hand, generate the entire UVM API tree with a
single {doc}`whole-tree <../usage/whole-tree>` directive:

```rst
.. autosvsummary::
   :packages: uvm_pkg
   :kinds: class
```

## Diagnostics

UVM elaborates with many benign lint-style warnings (width truncation, dangling
`else`, …). These are **not** surfaced as build warnings; they are counted and
reported once at INFO level. Only genuine parse errors are surfaced.
