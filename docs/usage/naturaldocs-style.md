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

`Group:` headers partition a class's members into labeled sections, which render
as subsection rubrics in the output.
