# Register access path

What connects a register model to a real bus: the adapter that converts a
generic register item to and from a protocol sequence item, the predictor that
updates the model from observed bus traffic, the backdoor that bypasses the bus
entirely, and the callbacks that hook into each of those.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: reg/uvm_reg_adapter.svh, reg/uvm_reg_predictor.svh,
           reg/uvm_reg_backdoor.svh, reg/uvm_reg_cbs.svh,
           reg/uvm_reg_sequence.svh
```
