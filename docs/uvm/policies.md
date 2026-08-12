# Policies

Printing, comparing, packing and copying are all *policy* objects:
`uvm_field_op` carries one of them through a field automation pass, so the same
`do_print`/`do_compare` implementation serves every output format.

Recording is a policy too, but large enough to get its own page:
{doc}`recording`.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_policy.svh, base/uvm_printer.svh, base/uvm_comparer.svh,
           base/uvm_packer.svh, base/uvm_packer_array_extension.svh,
           base/uvm_copier.svh
```
