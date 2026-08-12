# Register test sequences

UVM ships a library of ready-made sequences that exercise a register model:
reset-value checks, bit-bashing, address-map access and memory walks. Every one
of them derives from `uvm_reg_sequence` — see {doc}`hierarchy` for the
derivation graph.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: reg/sequences/*.svh
```
