// A testbench linked against seq_vip.sv's database: its test starts a VIP
// sequence and one of its own, which starts another VIP sequence.

`include "mini_uvm.svh"

package seq_vip_tb_pkg;
  import mini_uvm_pkg::*;
  import seq_vip_pkg::*;

  class tb_smoke_seq extends uvm_sequence #(vip_item);
    `mini_object_utils(tb_smoke_seq)
    function new(string name = "tb_smoke_seq");
      super.new(name);
    endfunction
    virtual task body();
      vip_write_seq w;
      w = vip_write_seq::type_id::create("w");
      w.start(m_sequencer);
    endtask
  endclass

  class vip_test extends uvm_test;
    `mini_component_utils(vip_test)
    vip_sequencer seqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      seqr = vip_sequencer::type_id::create("seqr", this);
    endfunction
    virtual task run_phase(uvm_phase phase);
      tb_smoke_seq smoke;
      vip_burst_seq burst;
      phase.raise_objection(this);
      smoke = tb_smoke_seq::type_id::create("smoke");
      smoke.start(seqr);
      burst = vip_burst_seq::type_id::create("burst");
      burst.start(seqr);
      phase.drop_objection(this);
    endtask
  endclass
endpackage
