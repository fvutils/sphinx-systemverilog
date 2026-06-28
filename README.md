<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icons/png/logo-horizontal-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/icons/png/logo-horizontal.png">
  <img src="assets/icons/png/logo-horizontal.png" alt="sphinx-systemverilog" width="440">
</picture>

**A Sphinx autodoc extension for SystemVerilog, powered by [`pyslang`](https://github.com/MikePopoloski/slang).**

[![CI](https://github.com/fvutils/sphinx-systemverilog/actions/workflows/ci.yml/badge.svg)](https://github.com/fvutils/sphinx-systemverilog/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-fvutils.github.io-38BDF8)](https://fvutils.github.io/sphinx-systemverilog/)
[![PyPI](https://img.shields.io/pypi/v/sphinx-systemverilog?color=0EA5A4)](https://pypi.org/project/sphinx-systemverilog/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pyslang.readthedocs.io/)
[![License](https://img.shields.io/badge/license-Apache--2.0-FBBF24)](LICENSE)

</div>

A [Sphinx](https://www.sphinx-doc.org) autodoc extension for **SystemVerilog**, powered by
the [`pyslang`](https://github.com/MikePopoloski/slang) parser.

It documents SystemVerilog source the way `sphinx.ext.autodoc` documents Python: declarations
and their doc comments are pulled directly from source, supporting multiple comment dialects
(a Python-docstring-like *native* style, NaturalDocs, and Doxygen).

📖 **Documentation:** <https://fvutils.github.io/sphinx-systemverilog/>

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

## Development

```bash
source packages/python/bin/activate
pip install -e .
pytest -m "unit or sphinx"
sphinx-build -W docs docs/_build/html
```

## License

Apache-2.0.
