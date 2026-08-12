# UVM reference

A complete API reference for the [UVM](https://www.accellera.org/) class library,
generated from the UVM 1800.2-2020 sources by this extension — no hand-written
class documentation anywhere in it.

It exists for two reasons. It is the project's largest correctness test: UVM is
250k lines of SystemVerilog whose doc comments use NaturalDocs conventions,
`extern` prototypes separated from their bodies, and `// Function -- NODOCS --`
blocks detached from the declarations they describe. And it is the honest demo —
the output below is what you get by pointing the extension at a library and
running `sphinx-build`.

:::{only} not have_uvm
**This build has no UVM sources**, so the reference pages are empty. Run
`ivpm update -a` to fetch the UVM release into `packages/uvm` and rebuild; the
pages then populate without any configuration change.
:::

## How it is built

```python
# docs/conf.py
extensions = ["sphinx_systemverilog"]

sv_build_units  = ["packages/uvm/src/uvm_pkg.sv"]
sv_include_dirs = ["packages/uvm/src"]
sv_doc_style    = "auto"
```

`uvm_pkg.sv` `` `include ``s the entire library, so one build unit elaborates all
of UVM into a single project-wide index — around 5,200 objects, of which 288 are
documented classes. Pages then take their slice of that index by source path:

```rst
.. autosvsummary::
   :kinds: class
   :files: base/uvm_report_*.svh
```

Selecting by file rather than by name is what keeps this reference complete
without a hand-maintained class list: the pages partition UVM's own directory
layout, and a CI check fails the build if any documented class stops appearing
in the output (see {doc}`../usage/whole-tree`).

UVM elaborates with many benign lint-style diagnostics (width truncation,
dangling `else`). These are counted and reported once at INFO level rather than
raised as build warnings; only genuine parse errors surface.

## Contents

```{toctree}
:maxdepth: 1

hierarchy
core
policies
recording
components
sequences
phasing
factory
reporting
tlm
registers
memories
register-access
register-sequences
```
