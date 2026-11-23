// A self-contained agent package, built into its own database for the
// two-database stitching test (docs/design/uvm-stitching-plan.md §5.4).

`include "mini_uvm.svh"

package vip_pkg;
  import mini_uvm_pkg::*;

  class vip_item extends uvm_sequence_item;
    `mini_object_utils(vip_item)
    function new(string name = "vip_item");
      super.new(name);
    endfunction
  endclass

  class vip_driver extends uvm_driver;
    `mini_component_utils(vip_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class vip_monitor extends uvm_monitor;
    `mini_component_utils(vip_monitor)
    uvm_analysis_port #(vip_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap", this);
    endfunction
  endclass

  class vip_sequencer extends uvm_sequencer #(vip_item);
    `mini_component_utils(vip_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class vip_agent extends uvm_agent;
    `mini_component_utils(vip_agent)
    vip_driver    drv;
    vip_monitor   mon;
    vip_sequencer seqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      drv  = vip_driver::type_id::create("drv", this);
      mon  = vip_monitor::type_id::create("mon", this);
      seqr = vip_sequencer::type_id::create("seqr", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      drv.seq_item_port.connect(seqr.seq_item_export);
    endfunction
  endclass
endpackage : vip_pkg
