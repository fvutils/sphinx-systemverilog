// Connections that end on a container's own port, for the ELK schematic.
//
// Graphviz draws an agent as a cluster, which can't carry ports, so the DOT
// schematic drops all three of these and says so under the diagram:
//
//   * `mon.ap.connect(ap)` inside the agent: the monitor's port forwarded to
//     the agent's own;
//   * `agt.ap.connect(sb.act_imp)` in the env: an edge leaving the agent's port;
//   * `exp_export.connect(sb.exp_imp)` in the env: the env's own export
//     forwarded inward, so the edge starts on the diagram root's border.

`include "mini_uvm.svh"

package fwd_tb_pkg;
  import mini_uvm_pkg::*;

  class fwd_item extends uvm_sequence_item;
    `mini_object_utils(fwd_item)
    function new(string name = "fwd_item");
      super.new(name);
    endfunction
  endclass

  class fwd_monitor extends uvm_monitor;
    `mini_component_utils(fwd_monitor)
    uvm_analysis_port #(fwd_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap", this);
    endfunction
  endclass

  class fwd_agent extends uvm_agent;
    `mini_component_utils(fwd_agent)
    fwd_monitor mon;
    uvm_analysis_port #(fwd_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap", this);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mon = fwd_monitor::type_id::create("mon", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      mon.ap.connect(ap);
    endfunction
  endclass

  class fwd_scoreboard extends uvm_scoreboard;
    `mini_component_utils(fwd_scoreboard)
    uvm_analysis_imp #(fwd_item, fwd_scoreboard) act_imp;
    uvm_analysis_imp #(fwd_item, fwd_scoreboard) exp_imp;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      act_imp = new("act_imp", this);
      exp_imp = new("exp_imp", this);
    endfunction
    function void write(fwd_item t);
    endfunction
  endclass

  class fwd_env extends uvm_env;
    `mini_component_utils(fwd_env)
    fwd_agent      agt;
    fwd_scoreboard sb;
    uvm_analysis_export #(fwd_item) exp_export;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      exp_export = new("exp_export", this);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt = fwd_agent::type_id::create("agt", this);
      sb  = fwd_scoreboard::type_id::create("sb", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      agt.ap.connect(sb.act_imp);
      exp_export.connect(sb.exp_imp);
    endfunction
  endclass

  class fwd_test extends uvm_test;
    `mini_component_utils(fwd_test)
    fwd_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = fwd_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : fwd_tb_pkg

module fwd_tb_top;
  import mini_uvm_pkg::*;
  import fwd_tb_pkg::*;

  initial begin
    run_test("fwd_test");
  end
endmodule
