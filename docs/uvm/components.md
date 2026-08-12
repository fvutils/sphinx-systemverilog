# Components

`uvm_component` is the quasi-static testbench structure: instances have a place
in the hierarchy, a name path, a configuration scope and a phasing lifecycle.
`uvm_root` is the implicit top of that hierarchy.

Also here are the ready-made components from `comps/` — drivers, monitors,
scoreboards, comparators and the pair/policy helpers they use.

See {doc}`hierarchy` for the derivation graph.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_component.svh, base/uvm_root.svh, base/uvm_heartbeat.svh,
           comps/*.svh
```
