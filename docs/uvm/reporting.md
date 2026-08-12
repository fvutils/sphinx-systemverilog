# Reporting

The message path, end to end: `uvm_report_object` (the reporting interface every
component inherits), the handler that applies verbosity and action settings, the
server that formats and emits, the message object itself, and the catcher
callbacks that can rewrite or suppress a message in flight.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_report_*.svh, base/uvm_cmdline_report.svh
```
