# Cross-referencing, source links & intersphinx

## Roles

Reference any documented object with an `sv` role:

```rst
:sv:class:`my_pkg::my_transaction`
:sv:func:`parity`
:sv:mod:`counter`
```

| Role | Targets |
|---|---|
| `:sv:class:` / `:sv:type:` | classes, typedefs |
| `:sv:mod:` | modules |
| `:sv:func:` / `:sv:task:` | functions / tasks |
| `:sv:prop:` | class properties |
| `:sv:port:` / `:sv:param:` | ports / parameters |
| `:sv:obj:` | any object (also the target of NaturalDocs `<x>` / Doxygen `#x`) |

Both qualified (`pkg::name`) and unambiguous bare names resolve. An ambiguous
bare name (e.g. `new`, which many classes define) does **not** resolve — qualify
it. Unresolved *explicit* roles emit a build warning; references inferred from
comment markup (`<x>`, `#x`) degrade silently to text.

## Source links (viewcode)

When `sv_viewcode = True` (the default), every documented object gets a
`[source]` link to a generated, syntax-highlighted listing of its source file,
anchored at the declaration line. Disable with:

```python
sv_viewcode = False
```

## Intersphinx

The extension exports all documented objects to `objects.inv`, so other Sphinx
projects can reference your SystemVerilog API via
[`intersphinx`](https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html):

```python
intersphinx_mapping = {
    "mylib": ("https://example.com/mylib/docs/", None),
}
```

```rst
:sv:class:`mylib:my_pkg::my_transaction`
```
