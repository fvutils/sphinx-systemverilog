// A testbench over `stitch_vip.sv` that overrides the VIP's driver from the
// test (docs/design/uvm-stitching-plan.md §5.4).

`include "mini_uvm.svh"

package vtb_pkg;
  import mini_uvm_pkg::*;
  import vip_pkg::*;

  class fast_vip_driver extends vip_driver;
    `mini_component_utils(fast_vip_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class vtb_scoreboard extends uvm_scoreboard;
    `mini_component_utils(vtb_scoreboard)
    uvm_analysis_imp #(vip_item, vtb_scoreboard) exp;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      exp = new("exp", this);
    endfunction
    function void write(vip_item t);
    endfunction
  endclass

  class vtb_env extends uvm_env;
    `mini_component_utils(vtb_env)
    vip_agent      mst;
    vip_agent      slv;
    vtb_scoreboard scb;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mst = vip_agent::type_id::create("mst", this);
      slv = vip_agent::type_id::create("slv", this);
      scb = vtb_scoreboard::type_id::create("scb", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      mst.mon.ap.connect(scb.exp);
      slv.mon.ap.connect(scb.exp);
    endfunction
  endclass

  class vtb_test extends uvm_test;
    `mini_component_utils(vtb_test)
    vtb_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      set_type_override_by_type(vip_driver::get_type(), fast_vip_driver::get_type());
      env = vtb_env::type_id::create("env", this);
    endfunction
  endclass
endpackage : vtb_pkg

module vtb_top;
  import mini_uvm_pkg::*;
  import vtb_pkg::*;
  initial run_test("vtb_test");
endmodule
