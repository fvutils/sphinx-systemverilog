<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icons/png/logo-horizontal-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/icons/png/logo-horizontal.png">
  <img src="assets/icons/png/logo-horizontal.png" alt="sphinx-systemverilog" width="440">
</picture>

**A Sphinx autodoc extension for SystemVerilog, powered by [`pyslang`](https://github.com/MikePopoloski/slang).**

[![Docs](https://img.shields.io/badge/docs-dvkit.org-38BDF8)](https://dvkit.org/fvutils/sphinx-systemverilog/)
[![Source](https://img.shields.io/badge/source-git.dvkit.org-6366F1)](https://git.dvkit.org/fvutils/sphinx-systemverilog)
[![PyPI](https://img.shields.io/pypi/v/sphinx-systemverilog?color=0EA5A4)](https://pypi.org/project/sphinx-systemverilog/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pyslang.readthedocs.io/)
[![License](https://img.shields.io/badge/license-Apache--2.0-FBBF24)](LICENSE)

</div>

A [Sphinx](https://www.sphinx-doc.org) autodoc extension for **SystemVerilog**, powered by
the [`pyslang`](https://github.com/MikePopoloski/slang) parser.

It documents SystemVerilog source the way `sphinx.ext.autodoc` documents Python: declarations
and their doc comments are pulled directly from source, supporting multiple comment dialects
(a Python-docstring-like *native* style, NaturalDocs, and Doxygen).

📖 **Documentation:** <https://dvkit.org/fvutils/sphinx-systemverilog/>

> **Status:** early development. See `docs/design/` for the design and implementation plan.

## Installation

```bash
pip install sphinx-systemverilog
```

## Quick start

```python
# docs/conf.py
extensions = ["sphinx_systemverilog"]
sv_source_dirs = ["../rtl"]
sv_doc_style = "native"
```

```rst
.. autosvclass:: my_pkg::my_transaction
   :members:
```

## Documenting a design, not just its files

For RTL, the extension goes beyond what any single file says and documents the
**elaborated** design — which is where the interesting information lives:

```rst
.. sv:instance-tree:: soc
```

```text
soc
├── u_narrow : cluster #(W=8, WIDE=1'b0)
│   └── g_narrow.u_leaf : leaf #(W=8)
└── u_wide   : cluster #(W=32, WIDE=1'b1)
    └── g_wide.u_lane : lane #(W=32, LANES=4)
        ├── g_lp[*].u_g : leaf #(W=32)   (×4)
        └── u_l[3:0]    : leaf #(W=32)   (×4)
```

Generate blocks, instance arrays and resolved parameter values are all included,
and every type name is a cross-reference. Alongside it:

- **`sv:used-by`** — every site that instantiates a module, with its parameters
  and a link to the source line. No file-at-a-time tool can answer this.
- **`sv:parameter-matrix`** — the parameter values a module is *actually*
  elaborated at, as opposed to its declared defaults.

These are also `autosvmodule` options (`:show-instances:`, `:show-used-by:`,
`:show-parameters-used:`). They are off by default: each one walks the elaborated
hierarchy, so a project that does not ask pays nothing for it.

See [Design structure](https://dvkit.org/fvutils/sphinx-systemverilog/usage/structure.html).

## Development

```bash
source packages/python/bin/activate
pip install -e .
pytest -m "unit or sphinx"
sphinx-build -W docs docs/_build/html
```

### Building against a real design

`examples/cva6/` generates documentation from
[CVA6](https://github.com/openhwgroup/cva6), OpenHW Group's RISC-V
application-class core — a real design with generate loops, deep hierarchy and
struct-valued configuration parameters. It is not part of the published docs
(it needs a ~107 MB checkout) and is where the tool gets validated against
something fixtures cannot simulate.

```bash
cd examples/cva6
make fetch && make open
```

## License

Apache-2.0.
