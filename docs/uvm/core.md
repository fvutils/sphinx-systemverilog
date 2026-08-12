# Core objects

The base of the class library: `uvm_object` and the transaction it underpins,
plus the container, synchronization and callback classes the rest of UVM is
built from.

Members are ordered by their NaturalDocs `Group:` headers, which is how the UVM
sources themselves organize them.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_object.svh, base/uvm_transaction.svh, base/uvm_misc.svh,
           base/uvm_field_op.svh, base/uvm_globals.svh,
           base/uvm_pool.svh, base/uvm_queue.svh,
           base/uvm_cache.svh, base/uvm_lru_cache.svh, base/uvm_regex_cache.svh,
           base/uvm_spell_chkr.svh,
           base/uvm_event.svh, base/uvm_event_callback.svh, base/uvm_barrier.svh,
           base/uvm_callback.svh, base/uvm_run_test_callback.svh,
           base/uvm_process_guard.svh, base/uvm_process_guard_base.svh,
           base/uvm_traversal.svh
```
