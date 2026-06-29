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

## Cross-reference roles

Reference any documented object:

```rst
See :sv:class:`my_pkg::my_transaction` and :sv:func:`parity`.
```

Roles include `:sv:class:`, `:sv:mod:`, `:sv:func:`, `:sv:task:`,
`:sv:prop:`, `:sv:param:`, and the generic `:sv:obj:`. Both qualified
(`pkg::name`) and unambiguous bare names resolve; unresolved references emit a
build warning.
