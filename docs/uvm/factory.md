# Factory, configuration and resources

Object construction and lookup: the factory and its type/instance overrides, the
registry proxies `` `uvm_object_utils `` generates, the core service that hands
out the singletons, and the resource database that `uvm_config_db` is a typed
view onto.

The data access policy (DAP) classes from `dap/` are here too — they are the
guard objects UVM uses to make a configuration field settable only until it is
read.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_factory.svh, base/uvm_registry.svh, base/uvm_coreservice.svh,
           base/uvm_resource*.svh, base/uvm_config_db*.svh,
           base/uvm_cmdline_processor.svh, dap/*.svh
```
