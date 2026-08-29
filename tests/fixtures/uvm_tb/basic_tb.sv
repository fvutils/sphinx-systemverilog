// The reference testbench shape for model extraction tests (U1-TEST-1).
//
// Every construct here exists to pin one extraction behaviour:
//
//   * `test -> env -> 2 agents -> driver/monitor` --- the ordinary containment
//     spine, built with `type_id::create`;
//   * a **conditional** create, which must be reported with `conditional=True`
//     rather than presented as unconditional fact;
//   * a **loop** create whose name comes from `$sformatf`, which must be
//     reported with an unknown instance name and multiplicity "N" --- never a
//     fabricated integer, since the trip count is not a constant;
//   * a **direct `new()`** create, which is a different expression kind
//     (`NewClass`, not `Call`) and therefore a separate code path.

`include "mini_uvm.svh"

package basic_tb_pkg;
  import mini_uvm_pkg::*;

  class my_item extends uvm_sequence_item;
    `mini_object_utils(my_item)
    function new(string name = "my_item");
      super.new(name);
    endfunction
  endclass

  class my_driver extends uvm_driver;
    `mini_component_utils(my_driver)
    uvm_seq_item_pull_port #(my_item) seq_item_port;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      seq_item_port = new("seq_item_port", this);
    endfunction
  endclass

  class my_monitor extends uvm_monitor;
    `mini_component_utils(my_monitor)
    uvm_analysis_port #(my_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // Direct construction: `ExpressionKind.NewClass`, not a factory call.
      ap = new("ap", this);
    endfunction
  endclass

  class my_sequencer extends uvm_sequencer #(my_item);
    `mini_component_utils(my_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class my_agent extends uvm_agent;
    `mini_component_utils(my_agent)
    my_driver    drv;
    my_monitor   mon;
    my_sequencer seqr;
    bit          is_active = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mon = my_monitor::type_id::create("mon", this);
      // Conditional: present in the tree, but flagged.
      if (is_active) begin
        drv  = my_driver::type_id::create("drv", this);
        seqr = my_sequencer::type_id::create("seqr", this);
      end
    endfunction
  endclass

  class my_scoreboard extends uvm_scoreboard;
    `mini_component_utils(my_scoreboard)
    uvm_analysis_export #(my_item)     analysis_export;
    uvm_tlm_analysis_fifo #(my_item)   fifo;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      analysis_export = new("analysis_export", this);
      // A library type that *is* a component: it belongs in the tree, and the
      // walk must stop at it rather than documenting UVM's own internals.
      fifo = new("fifo", this);
    endfunction
  endclass

  // Built with a direct `new()` rather than the factory --- legal, and common
  // enough for components nobody expects to override.
  class my_coverage extends uvm_subscriber #(my_item);
    `mini_component_utils(my_coverage)
    int n_seen;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void write(my_item t);
      n_seen++;
    endfunction
  endclass

  class my_env extends uvm_env;
    `mini_component_utils(my_env)
    my_agent     agt_a;
    my_agent     agt_b;
    my_agent     extra[4];
    my_scoreboard sb;
    my_coverage  cov;
    int          n_extra = 4;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt_a = my_agent::type_id::create("agt_a", this);
      agt_b = my_agent::type_id::create("agt_b", this);
      sb    = my_scoreboard::type_id::create("sb", this);
      // Direct construction: `ExpressionKind.NewClass`, not a factory call.
      cov   = new("cov", this);
      // Dynamic name + non-constant trip count: multiplicity is "N", and the
      // instance name is unknown rather than guessed.
      for (int i = 0; i < n_extra; i++) begin
        extra[i] = my_agent::type_id::create($sformatf("extra_%0d", i), this);
      end
    endfunction
  endclass

  class my_test extends uvm_test;
    `mini_component_utils(my_test)
    my_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = my_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : basic_tb_pkg

// The static root: auto-detection reads the `run_test` argument from here.
module tb_top;
  import mini_uvm_pkg::*;
  import basic_tb_pkg::*;

  initial begin
    run_test("my_test");
  end
endmodule
