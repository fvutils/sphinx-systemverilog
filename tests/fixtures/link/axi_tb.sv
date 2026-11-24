// A testbench over `axi_vip.sv`, built without its sources: linked against
// the VIP's database (docs/design/svdb-linking-plan.md).

`include "mini_uvm.svh"
`include "axi_macros.svh"

package axi_tb_pkg;
  import mini_uvm_pkg::*;
  import axi_vip_pkg::*;
  import axi_types_pkg::*;

  class fast_axi_driver extends axi_driver;
    `mini_component_utils(fast_axi_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual task drive(axi_item req, output bit ok);
      ok = req.burst == INCR;
    endtask
  endclass

  class axi_env extends uvm_env;
    `mini_component_utils(axi_env)
    axi_agent agent;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agent = axi_agent::type_id::create("agent", this);
    endfunction
  endclass

  class axi_test extends uvm_test;
    `mini_component_utils(axi_test)
    axi_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      axi_driver::type_id::set_type_override(fast_axi_driver::get_type());
      env = axi_env::type_id::create("env", this);
    endfunction
  endclass
endpackage

module axi_tb_top;
  import mini_uvm_pkg::*;
  logic clk, rst_n;
  logic [`AXI_ADDR_W-1:0] last;
  axi_if #(.DW(64)) bus (.clk(clk), .rst_n(rst_n));
  initial begin
    `AXI_CHECK(axi_vip_pkg::clog2_bursts() == axi_types_pkg::LEN_W, "len")
    run_test("axi_test");
  end
endmodule
