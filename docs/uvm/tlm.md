# TLM

Transaction-level connections. `uvm_port_base` is the shared implementation
behind every port, export and imp; the TLM1 classes provide the
put/get/peek/transport interfaces and the analysis fan-out, and the TLM2 classes
add sockets, the generic payload and time annotation.

This is the largest family by class count — 94 classes derive from
`uvm_port_base` — because each interface exists in blocking, non-blocking and
combined variants, times port/export/imp.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_port_base.svh, tlm1/*.svh, tlm2/*.svh
```
