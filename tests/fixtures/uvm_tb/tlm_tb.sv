// The reference testbench for TLM connection extraction and the schematic
// (U3-TEST-1).  Its shape is deliberately the one the layout prototype was
// drawn against (`docs/design/assets/uvm-schematic-controlled.dot`): an env
// holding two agents, a scoreboard, a coverage collector and a virtual
// sequencer, so the four §7.3 layout knobs have something real to control.
//
// Every wiring style a single-level schematic has to read appears once:
//
//   * `agt.mon.ap.connect(sb.aimp)` --- an analysis connection written from the
//     *parent*, whose two ends are three- and two-deep member chains;
//   * `drv.seq_item_port.connect(seqr.seq_item_export)` --- a sequencer/driver
//     connection written *inside* the agent, so a resolved endpoint may be a
//     sibling rather than a child;
//   * `vseqr.seqr_a = agt_a.seqr` --- a virtual-sequencer handle *assignment*,
//     which is not a call at all and which a connect-only walker never sees;
//   * a connection made under an `if`, which may not happen;
//   * a connection to a component that is built conditionally.

`include "mini_uvm.svh"

package tlm_tb_pkg;
  import mini_uvm_pkg::*;

  class tlm_item extends uvm_sequence_item;
    `mini_object_utils(tlm_item)
    int addr;
    function new(string name = "tlm_item");
      super.new(name);
    endfunction
  endclass

  // Neither of these declares a port.  `seq_item_port` and `seq_item_export`
  // are **inherited** from the library, which is how real UVM works and which
  // is what makes them the interesting case: a port a reader never wrote, and
  // which the schematic must still draw because it is connected.
  class tlm_sequencer extends uvm_sequencer #(tlm_item);
    `mini_component_utils(tlm_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class tlm_driver extends uvm_driver;
    `mini_component_utils(tlm_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class tlm_monitor extends uvm_monitor;
    `mini_component_utils(tlm_monitor)
    uvm_analysis_port #(tlm_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap", this);
    endfunction
  endclass

  class tlm_agent extends uvm_agent;
    `mini_component_utils(tlm_agent)
    tlm_driver    drv;
    tlm_monitor   mon;
    tlm_sequencer seqr;
    bit           is_active = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mon = tlm_monitor::type_id::create("mon", this);
      if (is_active) begin
        drv  = tlm_driver::type_id::create("drv", this);
        seqr = tlm_sequencer::type_id::create("seqr", this);
      end
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      // Written inside the agent, so both endpoints are the agent's own
      // children --- and it is under an `if`, so it may not happen.
      if (is_active)
        drv.seq_item_port.connect(seqr.seq_item_export);
    endfunction
  endclass

  class tlm_scoreboard extends uvm_scoreboard;
    `mini_component_utils(tlm_scoreboard)
    uvm_analysis_imp #(tlm_item, tlm_scoreboard) aimp;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      aimp = new("aimp", this);
    endfunction
    function void write(tlm_item t);
    endfunction
  endclass

  class tlm_coverage extends uvm_subscriber #(tlm_item);
    `mini_component_utils(tlm_coverage)
    uvm_analysis_imp #(tlm_item, tlm_coverage) aimp;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      aimp = new("aimp", this);
    endfunction
    virtual function void write(tlm_item t);
    endfunction
    // A decoy.  A testbench is full of user methods called `connect`, and a
    // walker keying on the *name* would draw an edge for this one.  The
    // discriminator is the lexical path of the subroutine being called ---
    // `uvm_port_base::connect` and nothing else --- so this is called from
    // `connect_phase`, where a name-based walker would be most confident.
    function void connect(tlm_scoreboard peer);
    endfunction
  endclass

  // A virtual sequencer holds *handles* to the real ones.  Nothing is created
  // here and nothing is connected: the wiring is plain assignment, which is why
  // a walker that only looked at `connect` calls would draw this component with
  // no edges at all.
  class tlm_vseqr extends uvm_sequencer_base;
    `mini_component_utils(tlm_vseqr)
    tlm_sequencer seqr_a;
    tlm_sequencer seqr_b;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class tlm_env extends uvm_env;
    `mini_component_utils(tlm_env)
    tlm_agent      agt_a;
    tlm_agent      agt_b;
    tlm_scoreboard sb;
    tlm_coverage   cov;
    tlm_vseqr      vseqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt_a = tlm_agent::type_id::create("agt_a", this);
      agt_b = tlm_agent::type_id::create("agt_b", this);
      sb    = tlm_scoreboard::type_id::create("sb", this);
      cov   = tlm_coverage::type_id::create("cov", this);
      vseqr = tlm_vseqr::type_id::create("vseqr", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      // Analysis fan-out: both monitors reach the scoreboard, one also reaches
      // the coverage collector.  These are the edges that must never be allowed
      // to constrain the layout.
      agt_a.mon.ap.connect(sb.aimp);
      agt_b.mon.ap.connect(sb.aimp);
      agt_a.mon.ap.connect(cov.aimp);
      // Virtual-sequencer wiring is an assignment, not a call.
      vseqr.seqr_a = agt_a.seqr;
      vseqr.seqr_b = agt_b.seqr;
      // Not a TLM connection: `tlm_coverage::connect` is the user's own method.
      cov.connect(sb);
    endfunction
  endclass

  class tlm_test extends uvm_test;
    `mini_component_utils(tlm_test)
    tlm_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = tlm_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : tlm_tb_pkg

module tlm_tb_top;
  import mini_uvm_pkg::*;
  import tlm_tb_pkg::*;

  initial begin
    run_test("tlm_test");
  end
endmodule
