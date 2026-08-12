# Register model

The model itself: blocks, registers, fields, address maps and the register item
that carries an operation through the model.

Memories and virtual registers are on {doc}`memories`, the classes that connect
a model to a bus agent are on {doc}`register-access`, and the pre-built test
sequences are on {doc}`register-sequences`.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: reg/uvm_reg.svh, reg/uvm_reg_block.svh, reg/uvm_reg_field.svh,
           reg/uvm_reg_map.svh, reg/uvm_reg_file.svh, reg/uvm_reg_item.svh,
           reg/uvm_reg_model.svh, reg/uvm_reg_indirect.svh, reg/uvm_reg_fifo.svh
```
