Module reference
================

The blocks in :doc:`the design <index>` are documented on their own pages.
This page documents **everything else** in the elaborated design — chiefly the
vendor library blocks the core reuses heavily (``lzc``, ``popcount``,
``rr_arb_tree``, ``fifo_v3`` …) — so that every type name in every hierarchy
tree resolves to documentation.

The whole page is one directive:

.. code-block:: rst

   .. autosvsummary::
      :kinds: module interface
      :exclude: cva6 frontend instr_realign ras btb bht instr_scan ...

.. only:: have_cva6

   .. autosvsummary::
      :kinds: module interface
      :exclude: cva6 frontend instr_realign ras btb bht instr_scan instr_queue
             id_stage decoder compressed_decoder issue_stage scoreboard
             issue_read_operands ex_stage alu_wrapper branch_unit csr_buffer
             mult fpu_wrap load_store_unit cvxif_fu aes commit_stage controller
             csr_regfile perf_counters wt_cache_subsystem cva6_icache wt_dcache
             wt_axi_adapter instr_tracer cva6_rvfi_probes
      :optional:
