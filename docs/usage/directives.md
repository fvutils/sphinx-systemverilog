# Directives & roles

## Autodoc directives

These parse your source and emit documentation automatically.

| Directive | Documents |
|---|---|
| `autosvpackage` | a package and (with `:members:`) its contents |
| `autosvclass` | a class and (with `:members:`) its properties/methods |
| `autosvmodule` | a module |
| `autosvfunction` | a single function |
| `autosvtask` | a single task |

Each takes a qualified name as its argument:

```rst
.. autosvclass:: my_pkg::my_transaction
   :members:
```

### Options

| Option | Meaning |
|---|---|
| `:members:` | Document members. With no value, all; or give a name list. |
| `:undoc-members:` | Also include members that have no doc comment. |
| `:exclude-members:` | Comma/space-separated names to skip. |
| `:member-order:` | `source` (default), `alpha`, or `groups`. |
| `:doc-style:` | Override the dialect for this directive. |
| `:optional:` | Skip silently (no warning) when the target is not in the index. Useful for pages that render the same whether optional sources are present. |
| `:show-inheritance:` | (classes) Add an inheritance diagram. |
| `:show-instances:` | (modules) Add the [instance tree](structure.md). |
| `:show-used-by:` | (modules) Add the list of [instantiation sites](instantiated-by). |
| `:show-parameters-used:` | (modules) Add the [parameter matrix](parameter-matrix). |

The three `:show-*:` structural options each trigger a walk of the elaborated
design and are off by default; see [Elaboration cost](advanced.md).

## Structural directives

These describe the *elaborated* design rather than any single file, and are
documented in full under [Design structure](structure.md):

| Directive | Renders |
|---|---|
| `sv:instance-tree` | A module's instantiation hierarchy, as a cross-linked text tree (or `:diagram:`). |
| `sv:used-by` | Every site that instantiates a module, with parameters and source links. |
| `sv:parameter-matrix` | The parameter values a module is actually elaborated at. |
| `sv:instance-diagram` | A module-to-module Graphviz graph. |
| `sv:inheritance-diagram` | A class hierarchy graph. |

```rst
.. sv:instance-tree:: soc
   :depth: 2
   :collapse:
```

## Manual domain directives

The autodoc directives emit these; you can also write them by hand when you
want full control:

```rst
.. sv:class:: my_transaction
   :module: my_pkg
   :extends: uvm_sequence_item
   :virtual:

   A bus transaction.

   .. sv:function:: function bit parity(bit[31:0] mask)

      Compute the parity of the payload.
```

Available object directives: `sv:package`, `sv:module`, `sv:interface`,
`sv:program`, `sv:class`, `sv:function`, `sv:task`, `sv:property`, `sv:port`,
`sv:parameter`, `sv:typedef`, `sv:macro`.

See [how signatures are rendered](signatures.md) for what the domain does with
the signature text and the options above.

## Objects in the table of contents

Documented objects become table-of-contents entries, so they appear in the
sidebar and in a page-local `contents` directive, nested under the declaration
that contains them. Sphinx's standard
[`toc_object_entries`](https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-toc_object_entries)
and `toc_object_entries_show_parents` settings control this:

| `toc_object_entries_show_parents` | Entry for `sig_pkg::sig_ops::seed` |
|---|---|
| `domain` (default) | `sig_ops::seed()` |
| `hide` | `seed()` |
| `all` | `sig_pkg::sig_ops::seed()` |

The package heads the qualified name, so `domain` mode shows the enclosing class
but not the package — the same shape the Python domain uses for modules. Set
`add_function_parentheses = False` to drop the `()` from function and task
entries, or `toc_object_entries = False` to suppress object entries entirely.

## Cross-reference roles

Reference any documented object:

```rst
See :sv:class:`my_pkg::my_transaction` and :sv:func:`parity`.
```

Roles include `:sv:class:`, `:sv:mod:`, `:sv:func:`, `:sv:task:`,
`:sv:prop:`, `:sv:param:`, and the generic `:sv:obj:`. Both qualified
(`pkg::name`) and unambiguous bare names resolve; unresolved references emit a
build warning.
