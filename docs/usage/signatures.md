# How signatures are rendered

Every documented declaration is rendered from its SystemVerilog source text into
structured markup, so the theme can style each piece and Sphinx can lay it out.
A function signature is broken into a kind label, qualifiers, a return type, the
name, and a *parameter list* with one entry per argument:

```{eval-rst}
.. sv:function:: function py_object py_call_builtin(string name, py_tuple args)
   :module: doc_example
   :virtual:

   Call a Python builtin.
```

The parts, and where each comes from:

| Part | Source |
|---|---|
| `virtual`, `static`, … | the `:virtual:` / `:qualifiers:` options |
| kind label (`function`, `task`, `class`, …) | the directive itself |
| return type | the signature text |
| parameter list | the signature text, parsed per argument |
| `extends` | the `:extends:` option |
| `[source]` | the `:source:` option (see [source links](cross-referencing.md)) |

Autodoc fills those options in for you; a hand-written `sv:function::` directive
gets exactly the same treatment, because the parsing happens in the domain
rather than in the source model.

## Parameter lists

Arguments are parsed individually, into direction, type, name, unpacked
dimensions, and default value:

```systemverilog
function void seed(int vals[$] = '{1, 2}, int repeat_count = 3);
```

renders as two parameters, not three — the comma inside `'{1, 2}` is nested, and
the parser only splits at bracket depth zero. String literals are respected the
same way, so `string text = "a, b"` is a single argument.

Because the arguments are real
[`desc_parameterlist`](https://www.sphinx-doc.org/en/master/extdev/nodes.html)
nodes, long signatures wrap the way they do in the Python and C++ domains, and
each parameter carries the `sig-param` class for theming.

Unpacked dimensions bind to the *declarator*, not to the type or to the name
used for lookup: `ref int q[$]` renders as `q[$]`, but the object is indexed,
anchored, and cross-referenced as `q`.

## Types link automatically

Any type in a signature that names a documented object becomes a link — return
types, argument types, property types, and the base class in an `extends`
clause. Built-in types (`int`, `bit`, `logic`, `string`, `void`, …) are keywords
rather than objects, so they are styled but never linked.

A type that is *not* documented — declared in a header outside
`sv_source_dirs`, or excluded — renders as plain text without a warning. These
references are inferred from the signature rather than written by an author, so
warning about them would be noise; see
[cross-referencing](cross-referencing.md).

## When a signature cannot be parsed

Parsing never fails a build. If a signature does not match anything the parser
recognises — an unbalanced argument list, say — it falls back to rendering the
argument text as a single opaque string, exactly as earlier versions did. You
lose the per-parameter markup and the type links for that one declaration;
nothing else changes.
