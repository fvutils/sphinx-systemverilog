# Doc-comment dialects

Three dialects, plus `auto` detection. Set the project default with
`sv_doc_style`; override per directive with `:doc-style:`. Published version:
<https://dvkit.org/fvutils/sphinx-systemverilog/usage/native-style.html>

A doc comment is the contiguous `//` or `/* */` block **immediately above** a
declaration. A trailing comment on the declaration's own line documents that
declaration:

```systemverilog
rand bit [31:0] addr;   // The target address.
```

Ports and parameters accept either form — leading or trailing.

---

## `native` — recommended for new code

The comment body **is** reStructuredText. Nothing is translated; it flows
straight into Sphinx.

- First paragraph = summary; everything after the first blank line = body.
- reST field lists describe parameters and return values.
- Any reST is legal: lists, ``` ``literals`` ```, roles, directives.

```systemverilog
// Compute the parity of the data payload.
//
// A longer explanation can span multiple lines and use any
// reStructuredText: lists, ``literals``, references, etc.
//
// :param mask: bits to include in the parity calculation
// :returns: the computed parity bit
function bit parity(bit [31:0] mask);
  return ^(data & mask);
endfunction
```

Cross-references are ordinary roles:

```systemverilog
// Drive this transaction; see :sv:class:`my_pkg::driver`.
```

**The one hazard**: this is the only dialect that can emit RST, and therefore
the only one that can emit *broken* RST. An unterminated `` `` `` or a stray
`*` becomes a build warning. If a comment is banner art rather than prose,
either rewrite it or let `auto` classify it as plain text.

---

## `naturaldocs` — the UVM convention

```python
sv_doc_style = "naturaldocs"
```

A block starts with a **keyword header**, followed by prose:

```systemverilog
// Function: get_name
//
// Returns the name of the object, as provided by the ~name~ argument in the
// <new> constructor or <set_name> method.
```

Header keywords map to object kinds: `Class`, `Function`, `Task`, `Variable`
(property), `Group`, `Topic`, `Macro`, `Typedef`, `Module`, `Interface`,
`Package`, `Port`.

Separators may be a colon or a dash run, and banner rules are tolerated:

```systemverilog
// CLASS: uvm_object
// Function -- get_name
//----------------------------------------
//
// CLASS -- NODOCS -- uvm_object
//
//----------------------------------------
```

### Sections

A section header **on a line of its own** is lifted into a field list:

```systemverilog
// Function: m_do_open
//
// Initializes the state of the stream.
//
// Parameters:
// db - Database which the stream belongs to
// scope - Optional scope
//
// Returns:
// The opened stream.
```

Recognised: `Parameters`/`Arguments`/`Args`, `Returns`/`Return`, `Throws`,
`See Also`. Entries are `name - description`; a line that does not parse as an
entry stays in the prose rather than being guessed at. The section ends at the
next blank line.

Note the "own line" rule: an ordinary sentence beginning "Returns the name of
the object" is prose and is left alone. (UVM has 236 of those and two real
`Returns:` sections.)

### Inline markup

| Written | Renders as |
|---|---|
| `<symbol>` | a cross-reference (`:sv:obj:`) |
| `~code~` | inline ``literal`` |

Stray RST characters in prose are escaped automatically, so ND comments cannot
break a build the way native ones can.

### `NODOCS` and groups

UVM tags blocks `-- NODOCS --` to keep them out of its IEEE extraction. The
prose is still useful, so by default the marker is stripped and the block kept;
set `sv_naturaldocs_nodocs = "skip"` to drop those blocks instead.

`Group:` headers partition a class's members into labelled sections, rendered
as rubrics. `:member-order: groups` sorts members by group.

Blocks are frequently **detached** from what they document — UVM puts `extern`
prototypes and `@uvm-ieee` annotations in between. Every comment block is
scanned and matched to its symbol by name and proximity, so this works.

---

## `doxygen`

```python
sv_doc_style = "doxygen"
```

Commands take `@` or `\`. Delimiters `/** */`, `/*! */`, `///` and `//!` are
all recognised.

| Command | Effect |
|---|---|
| `@brief` / `@short` | summary |
| `@details` | detailed body |
| `@param[in] name desc` | a `:param name:` field (direction is dropped) |
| `@tparam name desc` | a parameter field |
| `@return` / `@returns` | a `:returns:` field |
| `@retval val desc` | a return-value field |
| `@note`, `@warning` | note / warning field |
| `@see` / `@sa` | see-also field, targets cross-referenced |
| `@pre`, `@post`, `@throws` | corresponding fields |

| Inline | Renders as |
|---|---|
| `@p name`, `@c name` | inline ``literal`` |
| `@a name` | *emphasis* |
| `#symbol`, `@ref symbol` | cross-reference |

```systemverilog
/**
 * @brief Compute the parity of the data payload.
 * @param mask bits to include in the calculation
 * @return the computed parity bit
 */
function bit parity(bit [31:0] mask);
```

---

## Code samples (every non-native dialect)

End the introducing line with `::`, leave a blank line, indent the code:

```systemverilog
/**
 * Presents a Python iterator as a valid/next pair, which maps onto a
 * SystemVerilog while loop::
 *
 *     py_iter it = new(PyObject_GetIter(seq));
 *     while (it.valid()) begin
 *         py_object item = it.next();
 *     end
 */
```

Everything indented past the `::` line is verbatim: no escaping, no inline
conversion, indentation and blank lines kept. So `#foo`, `<T>`, `~x~`, `*p` and
a trailing `_` mean what they mean in code, not what they mean in the dialect.
The block ends at the first line indented back to the introducing column.

Markdown ```` ``` ```` fences do **not** work in any dialect — they render as a
block quote and produce `ERROR: Unexpected indentation`.

---

## `auto`

Sniffs each comment individually — the right choice for a mixed tree (this
project's own doc set uses it).

Each dialect is asked, in registration order, whether it recognises the
comment; the first that says yes wins:

1. A NaturalDocs keyword header or ND markup → the ND parser.
2. Any `@`/`\` Doxygen command → the Doxygen parser.
3. A **sign of hand-written RST** — a field list, a ``` ``literal`` ```, a
   `:role:`, an explicit directive, or a `::` literal block → the native
   parser, which passes the body through unchanged.
4. Anything else → the internal **plain** parser: prose, escaped and
   structurally repaired. (`plain` is a fallback, not a value you can set —
   `sv_doc_style` accepts only the four names above.)

Step 4 is why banner comments are safe under `auto`:

```systemverilog
// ----------------------------------------
//  *** Do not call directly ***
// ----------------------------------------
```

renders as the words it contains, rather than as a transition followed by
unterminated emphasis.

The same structural repair preserves **lists**: in `plain`, `naturaldocs` and
`doxygen`, bullet (`*`, `-`, `+`) and enumerated (`1.`, `a)`) items are kept as
list items, dedented to their lead-in line and blank-line separated so docutils
recognises them. A lead-in ending in `:` followed by items indented under it —
the way banner comments are normally written — needs no source cleanup.

Setting `sv_doc_style = "native"` explicitly always uses
the native parser whatever the comment looks like — which is stricter, not
safer.

---

## Choosing

| Situation | Use |
|---|---|
| New code you control | `native` |
| UVM library or UVM-style code | `naturaldocs` |
| Code already commented for Doxygen | `doxygen` |
| Mixed tree, or vendor sources | `auto` |
| One page differs from the project default | `:doc-style:` on the directive |
