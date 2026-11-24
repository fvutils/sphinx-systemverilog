// A VIP whose sequences a testbench starts, built into its own database
// (run-phase plan, phase 3): the testbench's catalog lists them with this
// database as their origin, and reads what they start from its records.

`include "mini_uvm.svh"

package seq_vip_pkg;
  import mini_uvm_pkg::*;

  class vip_item extends uvm_sequence_item;
    `mini_object_utils(vip_item)
    function new(string name = "vip_item");
      super.new(name);
    endfunction
  endclass

  class vip_write_seq extends uvm_sequence #(vip_item);
    `mini_object_utils(vip_write_seq)
    function new(string name = "vip_write_seq");
      super.new(name);
    endfunction
    virtual task body();
      vip_item it;
      `mini_do(it)
    endtask
  endclass

  class vip_burst_seq extends uvm_sequence #(vip_item);
    `mini_object_utils(vip_burst_seq)
    function new(string name = "vip_burst_seq");
      super.new(name);
    endfunction
    virtual task body();
      vip_write_seq w;
      repeat (8) begin
        w = vip_write_seq::type_id::create("w");
        w.start(m_sequencer);
      end
    endtask
  endclass

  class vip_sequencer extends uvm_sequencer #(vip_item);
    `mini_component_utils(vip_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass
endpackage
