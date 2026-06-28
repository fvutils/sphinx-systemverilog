# The Doxygen comment style

Set Doxygen as the default dialect, or rely on `auto` detection (any `@`/`\`
command triggers it):

```python
sv_doc_style = "doxygen"   # or "auto"
```

## Supported commands

Commands may be written with `@` or `\`.

| Command | Effect |
|---|---|
| `@brief` / `@short` | the summary |
| `@details` | detailed body |
| `@param[in] name desc` | a `:param name:` field (direction `[in]`/`[out]` is dropped) |
| `@tparam name desc` | a parameter field |
| `@return` / `@returns` | a `:returns:` field |
| `@retval val desc` | a return-value field |
| `@note`, `@warning` | a note / warning field |
| `@see` / `@sa` | a "see also" field (targets become cross-references) |
| `@pre`, `@post`, `@throws` | corresponding fields |

Comment delimiters `/** */`, `/*! */`, `///`, and `//!` are all recognized.

## Inline markup

| Doxygen | Rendered as |
|---|---|
| `@p name` / `@c name` | inline ``literal`` |
| `@a name` | *emphasis* |
| `#symbol`, `@ref symbol` | a cross-reference |

## Example

```{eval-rst}
.. autosvclass:: dox_pkg::dox_txn
   :members:
```
