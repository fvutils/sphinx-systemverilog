// The reference testbench for sequence activity extraction (U4-TEST-1).
//
// Its shape is the one probed in section 8.6 of the elaboration study, because
// that probe is the evidence the feature rests on: a `body()` elaborates with
// its control flow intact, and each construct maps onto exactly one UML
// activity element.
//
//   * a conditional, which is a decision diamond;
//   * a `fork ... join_any` whose branches are *named blocks*, so the diagram
//     gets human-authored branch labels out of the source rather than
//     "branch 1" / "branch 2";
//   * a `repeat`, which is a loop node;
//   * a `#` delay, which is a time trigger;
//   * `disable fork`;
//   * sub-sequence `create` + `start`, which are the nodes that can become
//     cross-references to another sequence's own page.
//
// It also carries the two things a naive walker gets wrong.  `noisy_seq` uses
// the `` `mini_do `` macro, which is a stand-in for `` `uvm_do `` and expands
// to seven statements for one line of source.  And `body()` holds ordinary
// statements --- reporting, assignment --- which are not activity nodes and
// which must be *counted* rather than dropped, because a diagram that shows
// three boxes for a forty-line task is claiming something about the task.

`include "mini_uvm.svh"

package seq_tb_pkg;
  import mini_uvm_pkg::*;

  class seq_item extends uvm_sequence_item;
    `mini_object_utils(seq_item)
    rand int addr;
    function new(string name = "seq_item");
      super.new(name);
    endfunction
  endclass

  // -- sub-sequences ---------------------------------------------------------

  class cfg_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(cfg_seq)
    function new(string name = "cfg_seq");
      super.new(name);
    endfunction
    virtual task body();
      seq_item it;
      it = new();
      start_item(it, -1, m_sequencer);
      finish_item(it, -1);
    endtask
  endclass

  class traf_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(traf_seq)
    function new(string name = "traf_seq");
      super.new(name);
    endfunction
    virtual task body();
      seq_item it;
      `mini_do(it)
    endtask
  endclass

  // -- the reference sequence ------------------------------------------------
  //
  // Every node kind the emitter draws appears exactly once, in the order the
  // section 8.6 probe printed them.

  class main_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(main_seq)

    bit do_cfg = 1;
    int unsigned n_bursts = 4;

    function new(string name = "main_seq");
      super.new(name);
    endfunction

    virtual task body();
      cfg_seq  cfg;
      traf_seq traf;

      // Not an activity node: an assignment and a report.  Counted, not drawn.
      n_bursts = 4;
      $display("main_seq starting");

      if (do_cfg) begin
        cfg = cfg_seq::type_id::create("cfg");
        cfg.start(m_sequencer);
      end

      fork
        begin : traffic
          repeat (n_bursts) begin
            traf = traf_seq::type_id::create("traf");
            traf.start(m_sequencer);
          end
        end
        begin : timeout
          #100ns;
        end
      join_any
      disable fork;

      $display("main_seq done");
    endtask
  endclass

  // -- macro noise -----------------------------------------------------------
  //
  // One line of source, seven statements after expansion.  The whole of it is
  // one action.

  class noisy_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(noisy_seq)
    function new(string name = "noisy_seq");
      super.new(name);
    endfunction
    virtual task body();
      seq_item it;
      `mini_do(it)
      `mini_do(it)
    endtask
  endclass

  // -- the other join flavours ----------------------------------------------
  //
  // `StatementBlockKind` distinguishes all four, so the join bar is drawn from
  // the source rather than guessed.  A separate sequence rather than more
  // branches in `main_seq`, because the reference diagram should stay the shape
  // the study drew.

  class join_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(join_seq)
    function new(string name = "join_seq");
      super.new(name);
    endfunction
    virtual task body();
      fork
        #10ns;
        #20ns;
      join
      fork
        begin : detached
          #30ns;
        end
      join_none
      forever begin
        #40ns;
      end
    endtask
  endclass

  // -- a sequence that does not override body() ------------------------------
  //
  // Inherits an empty `body()` from `uvm_sequence_base`.  There is nothing to
  // draw, and "nothing to draw" has to be said rather than rendered as an
  // empty diagram.

  class silent_seq extends uvm_sequence #(seq_item);
    `mini_object_utils(silent_seq)
    function new(string name = "silent_seq");
      super.new(name);
    endfunction
  endclass

  // -- a driver and a sequencer, so the sequences have somewhere to run ------

  class seq_driver extends uvm_driver;
    `mini_component_utils(seq_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class seq_sequencer extends uvm_sequencer #(seq_item);
    `mini_component_utils(seq_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class seq_env extends uvm_env;
    `mini_component_utils(seq_env)
    seq_driver    drv;
    seq_sequencer seqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      drv  = seq_driver::type_id::create("drv", this);
      seqr = seq_sequencer::type_id::create("seqr", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      drv.seq_item_port.connect(seqr.seq_item_export);
    endfunction
  endclass

  class seq_test extends uvm_test;
    `mini_component_utils(seq_test)
    seq_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = seq_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : seq_tb_pkg
