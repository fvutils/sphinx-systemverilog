// The reference testbench for the RTL <-> testbench bridge (U5).
//
// This is the fixture the phase exists for.  Everything else in the UVM
// feature reads *one* elaboration: the tree and the schematic read classes,
// the RTL views read modules.  A virtual-interface binding is the one fact
// that spans both, and it spans them through a *string*: the top module puts
// an interface instance into `uvm_config_db` under a field name, and a
// component pulls it back out by that same name.  Neither half references the
// other, and no compiler checks that they agree.
//
// Five shapes are laid out here, and the fourth and fifth are the point:
//
//   * `u_bus` --- the ordinary case.  Set from the top module with a null
//     cntxt, read by two components, and connected to two RTL instances, one
//     of them through a modport.  Two drivers rather than one because "the
//     DUT" is the obvious answer and not always the whole answer.
//   * `u_clk` --- set and driven, but read by nothing.  A binding whose field
//     name no `get` matches is the same silent bug the config table already
//     reports, and it is worth repeating here because a *virtual interface*
//     that never arrives fails at the first dereference rather than quietly
//     using a default.
//   * `u_spare` --- an interface instance nothing connects to.  Handed to the
//     testbench correctly; simply wired to no RTL.
//   * the `vif_alias` set --- the value is a virtual-interface *handle*, not an
//     instance, so there is no RTL instance to name.  Reported as unresolved
//     rather than guessed.
//   * `bridge_agent` reads `vif` and passes it down; that read is what makes
//     the documented path run `bridge_agent` -> `bridge_tb_top.u_bus` ->
//     `bridge_tb_top.u_dut`, which is the acceptance criterion.

`include "mini_uvm.svh"

interface bridge_if;
  logic clk;
  logic [7:0] data;
  modport mon_mp (input clk, input data);
endinterface

interface bridge_clk_if;
  logic clk;
endinterface

module bridge_dut(bridge_if bus, input logic rst);
endmodule

// Connected through a modport rather than the whole interface.  slang resolves
// the connection to the interface *instance* either way, which is the only
// reason one rule covers both.
module bridge_probe(bridge_if.mon_mp bus);
endmodule

module bridge_clkgen(bridge_clk_if ck);
endmodule

package bridge_tb_pkg;
  import mini_uvm_pkg::*;

  class bridge_driver extends uvm_driver;
    `mini_component_utils(bridge_driver)
    virtual bridge_if vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class bridge_agent extends uvm_agent;
    `mini_component_utils(bridge_agent)
    bridge_driver drv;
    virtual bridge_if vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      // The testbench end of the bridge.
      if (!uvm_config_db #(virtual bridge_if)::get(this, "", "vif", vif))
        $display("no virtual interface");
      // A set whose value is a handle rather than an instance: there is no RTL
      // instance to name, and saying so is the honest answer.
      uvm_config_db #(virtual bridge_if)::set(this, "drv", "vif_alias", vif);
      drv = bridge_driver::type_id::create("drv", this);
    endfunction
  endclass

  class bridge_env extends uvm_env;
    `mini_component_utils(bridge_env)
    bridge_agent agt;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agt = bridge_agent::type_id::create("agt", this);
    endfunction
  endclass

  class bridge_test extends uvm_test;
    `mini_component_utils(bridge_test)
    bridge_env env;
    virtual bridge_if vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      // The second reader of the same field.
      void'(uvm_config_db #(virtual bridge_if)::get(this, "", "vif", vif));
      env = bridge_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : bridge_tb_pkg

module bridge_tb_top;
  import mini_uvm_pkg::*;
  import bridge_tb_pkg::*;

  logic rst;

  bridge_if     u_bus();
  bridge_clk_if u_clk();
  bridge_if     u_spare();

  bridge_dut   u_dut  (.bus(u_bus), .rst(rst));
  bridge_probe u_probe(.bus(u_bus.mon_mp));
  bridge_clkgen u_ck  (.ck(u_clk));

  initial begin
    uvm_config_db #(virtual bridge_if)::set(null, "*", "vif", u_bus);
    // Driven RTL, handed over correctly, and read by nothing: the field name
    // does not match any get.
    uvm_config_db #(virtual bridge_clk_if)::set(null, "*", "clk_vif", u_clk);
    // Handed over correctly and wired to no RTL at all.
    uvm_config_db #(virtual bridge_if)::set(null, "*", "spare_vif", u_spare);
    run_test("bridge_test");
  end
endmodule
