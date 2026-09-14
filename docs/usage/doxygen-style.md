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

## Lists

Bullet (`*`, `-`, `+`) and enumerated (`1.`, `a)`) lists are preserved, including
the usual shape of a lead-in line ending in `:` followed by items indented under
it. Items are dedented to their lead-in, the blank lines docutils needs are
inserted automatically, and nesting is kept. A leading `*` is read as a bullet,
not as emphasis; `*ptr` in prose still escapes as before.

(doxygen-code-samples)=
## Code samples

A code sample is written as a reStructuredText literal block: end the
introducing line with `::`, leave a blank line, and indent the code.

```systemverilog
/**
 * Iterates a Python iterable from SystemVerilog.
 *
 * Wraps a Python iterator and presents it as a valid/next pair, which
 * maps onto a SystemVerilog while loop::
 *
 *     py_iter it = new(PyObject_GetIter(seq));
 *     while (it.valid()) begin
 *         py_object item = it.next();
 *     end
 */
```

Everything indented past the `::` line is passed through exactly as typed —
indentation, nesting and blank lines included — and none of the conversions on
this page apply inside it. That last part is the point: `#foo` is a macro rather
than a cross-reference, `*p` is a pointer rather than emphasis, and a trailing
`_` is an identifier rather than an RST reference. The block ends at the first
line indented back to the introducing line's column.

Markdown fences do **not** work:

````{warning}
```` ``` ````-fenced code renders as a block quote and produces
`ERROR: Unexpected indentation`. The comment text is passed through as
reStructuredText, so use `::` and indentation instead. The dialect is named for
where its *commands* come from, not for its markup.
````

## Example

```{eval-rst}
.. autosvclass:: dox_pkg::dox_txn
   :members:
```
