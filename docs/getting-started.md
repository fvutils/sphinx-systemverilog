# Getting started

## Install

```bash
pip install sphinx-systemverilog
```

The extension depends on `sphinx` and `pyslang`; both are installed
automatically.

## Enable the extension

Add it to your `conf.py` and point it at your SystemVerilog sources:

```python
extensions = [
    "sphinx_systemverilog",
]

# One or more directories scanned (recursively) for .sv / .svh files.
sv_source_dirs = ["../rtl", "../verif"]

# The default doc-comment dialect: "native", "naturaldocs", "doxygen", or "auto".
sv_doc_style = "native"
```

On each build the extension parses the configured sources **once** into a
project-wide index, then every directive resolves names against that index.

## Document something

Use an `auto*` directive in any `.rst` (or MyST `.md`) page:

```rst
.. autosvclass:: my_pkg::my_transaction
   :members:
```

This renders the class, its inheritance, and its documented members, pulling
the text from the doc comments in your source.

## Configuration reference

| Option | Default | Meaning |
|---|---|---|
| `sv_source_dirs` | `[]` | Directories scanned for `.sv`/`.svh` sources. |
| `sv_include_dirs` | `[]` | Additional `+incdir` paths for the parser. |
| `sv_defines` | `{}` | Preprocessor `` `define `` values for elaboration. |
| `sv_build_units` | `[]` | Explicit root files to parse (instead of scanning dirs). |
| `sv_doc_style` | `"native"` | Default doc-comment dialect. |
| `sv_default_options` | `{}` | Options applied to every `auto*` directive. |
