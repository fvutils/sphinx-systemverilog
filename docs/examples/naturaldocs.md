# Example: NaturalDocs, modules & diagrams

This page is generated from the NaturalDocs-style fixtures
(`tests/fixtures/sv/nd_pkg.sv` and `counter.sv`) with `sv_doc_style =
"naturaldocs"`. It exercises detached-block association, member groups, an
inheritance diagram, and module ports/parameters.

## A class hierarchy with groups and a diagram

```{eval-rst}
.. autosvclass:: nd_pkg::nd_leaf
   :members:
   :show-inheritance:

.. autosvclass:: nd_pkg::nd_base
   :members:
```

## A module with parameters and ports

```{eval-rst}
.. autosvmodule:: counter
   :members:
```
