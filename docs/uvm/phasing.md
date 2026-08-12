# Phasing and objections

The phase schedule, the concrete phase singletons that populate it, the domains
that let subsystems run their own schedules, and the objection mechanism that
decides when a phase may end.

Each concrete phase (`uvm_build_phase`, `uvm_run_phase`, …) is a singleton class
rather than an enumeration, which is why there are so many of them.

```{eval-rst}
.. autosvsummary::
   :kinds: class
   :member-order: groups
   :optional:
   :files: base/uvm_phase.svh, base/uvm_phase_hopper.svh, base/uvm_domain.svh,
           base/uvm_common_phases.svh, base/uvm_runtime_phases.svh,
           base/uvm_bottomup_phase.svh, base/uvm_topdown_phase.svh,
           base/uvm_task_phase.svh, base/uvm_objection.svh
```
