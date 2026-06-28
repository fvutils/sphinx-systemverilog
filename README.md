# sphinx-systemverilog

A [Sphinx](https://www.sphinx-doc.org) autodoc extension for **SystemVerilog**, powered by
the [`pyslang`](https://github.com/MikePopoloski/slang) parser.

It documents SystemVerilog source the way `sphinx.ext.autodoc` documents Python: declarations
and their doc comments are pulled directly from source, supporting multiple comment dialects
(a Python-docstring-like *native* style, NaturalDocs, and Doxygen).

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
