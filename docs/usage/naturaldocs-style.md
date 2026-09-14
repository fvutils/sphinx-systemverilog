# The NaturalDocs comment style

NaturalDocs is the convention used by the UVM library. Set it as the default
dialect with:

```python
sv_doc_style = "naturaldocs"
```

## Documentation blocks

A NaturalDocs block starts with a **keyword header** and is followed by prose:

```systemverilog
// Function: get_name
//
// Returns the name of the object, as provided by the ~name~ argument in the
// <new> constructor or <set_name> method.
```

Recognized header keywords map to object kinds: `Class`, `Function`, `Task`,
`Variable` (property), `Group`, `Topic`, `Macro`, `Typedef`, `Module`,
`Interface`, `Package`, `Port`.

### Header separators and banners

The separator may be a colon or a dash run, and headers are often wrapped in
banner rules — all of these are recognized:

```systemverilog
// CLASS: uvm_object
// Function -- get_name
//----------------------------------------
//
// CLASS -- NODOCS -- uvm_object
//
//----------------------------------------
```

### The `NODOCS` marker

UVM tags blocks with `-- NODOCS --` to keep them out of its IEEE extraction.
The prose is still useful documentation, so by default it is **kept** (the
marker is simply stripped). To omit those blocks instead:

```python
# (model-level option; default is "include")
sv_naturaldocs_nodocs = "skip"
```

## Parameter and return sections

A section header on a line of its own is lifted out of the prose and rendered as
a field list, the same shape Doxygen's `@param`/`@return` and Python docstrings
produce:

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

Recognized headers are `Parameters`/`Arguments`/`Args`, `Returns`/`Return`,
`Throws` and `See Also`. The separator may be a colon or a dash, and the UVM
`-- NODOCS --` marker is allowed in the header (`Parameters -- NODOCS --`).
Each parameter entry is `name - description`; a line that does not parse as an
entry stays in the prose rather than being guessed at.

The section runs to the next blank line. Note that this is a *header on its own
line* — an ordinary sentence such as "Returns the name of the object" is prose
and is left alone, which matters because UVM has 236 of those and only two real
`Returns:` sections.

## Inline markup

| NaturalDocs | Rendered as |
|---|---|
| `<symbol>` | a cross-reference (`:sv:obj:`symbol``) |
| `~code~` | inline ``literal`` |

Stray RST characters in prose are escaped automatically, so comments written
for NaturalDocs render cleanly without RST surprises.

## Detached blocks and groups

NaturalDocs blocks are frequently **separated** from the declaration they
document (UVM puts `extern` prototypes and `@uvm-ieee` annotations in between).
The extension scans every comment block and associates each with its symbol by
name and source proximity, so detached blocks are found correctly.

Association is confined to the declaration's **own file**. Names like `new`,
`create` and `get_type_name` recur in dozens of UVM files, and line numbers are
only comparable within one file, so a block in `uvm_printer.svh` is never a
candidate for a member of your testbench. A member with no block in its own file
is reported as undocumented — which is what `:undoc-members:` and
[`sv_uvm_hide_trivial_new`](#uvm-constructors) act on.

Within one file, collisions between a `pure virtual` prototype and a
same-named override in a later class are still resolved by proximity alone, so a
prototype can pick up the override's prose. This affects libraries that declare
both in one file (UVM does); it cannot pull prose onto your code.

`Group:` headers partition a class's members into labeled sections, which render
as subsection rubrics in the output.
