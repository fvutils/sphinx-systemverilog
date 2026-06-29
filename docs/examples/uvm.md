# Example: documenting UVM

The extension documents the full [UVM](https://www.accellera.org/) library
end-to-end from its NaturalDocs-commented source — the project's Phase-2
acceptance target. A real build produces ~5700 documented objects in a few
seconds.

:::{only} have_uvm
This page is **generated live** from the UVM sources in this repository (fetched
by ivpm into `packages/uvm`). Scroll to {ref}`uvm-reference` for the rendered
output.
:::

:::{only} not have_uvm
This rendering is shown only when the (large) UVM sources are present. They are
not in this build, so the page describes the configuration and expected results;
run `ivpm update -a` to fetch UVM and the reference renders below.
:::

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

(uvm-reference)=

## Rendered UVM reference

When the UVM sources are present, the classes below are pulled directly from
them (otherwise this section is empty — run `ivpm update -a` to fetch UVM).

```{eval-rst}
.. autosvclass:: uvm_object
   :members:
   :show-inheritance:
   :doc-style: naturaldocs
   :optional:

.. autosvclass:: uvm_sequence_item
   :members:
   :doc-style: naturaldocs
   :optional:
```
