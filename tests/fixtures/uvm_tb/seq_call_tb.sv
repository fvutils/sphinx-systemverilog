// Helper tasks and `super.` calls (run-phase plan, phase 4).
//
//   * `call_base_test::run_phase` raises an objection and calls the virtual
//     task `traffic()`; `call_test` overrides `traffic()`, so walking
//     `call_test` dispatches the call to its own version.
//   * `call_test::run_phase` calls `super.run_phase(phase)`, then `drain()`,
//     which calls itself again (cut), then `setup()`, a function (not followed).
//   * `call_seq::body` starts `step_seq` only through the helper `do_steps()`,
//     which creates the member `m_step` that `body` starts afterwards.
//   * `vseq_test` starts sequences on `env.agt.sqr` and on the virtual
//     sequencer `env.vseqr`, whose `agt_sqr` handle `call_env` assigns in
//     `connect_phase`; `call_vseq` starts on `p_sequencer.agt_sqr` and, through
//     `call_seq`, on `m_sequencer`: each resolves to `uvm_test_top.env.agt.sqr`.

`include "mini_uvm.svh"

package seq_call_pkg;
  import mini_uvm_pkg::*;

  class call_item extends uvm_sequence_item;
    `mini_object_utils(call_item)
    function new(string name = "call_item");
      super.new(name);
    endfunction
  endclass

  class step_seq extends uvm_sequence #(call_item);
    `mini_object_utils(step_seq)
    function new(string name = "step_seq");
      super.new(name);
    endfunction
    virtual task body();
      call_item it;
      `mini_do(it)
    endtask
  endclass

  class tail_seq extends uvm_sequence #(call_item);
    `mini_object_utils(tail_seq)
    function new(string name = "tail_seq");
      super.new(name);
    endfunction
    virtual task body();
      call_item it;
      `mini_do(it)
    endtask
  endclass

  class call_seq extends uvm_sequence #(call_item);
    `mini_object_utils(call_seq)
    step_seq m_step;
    function new(string name = "call_seq");
      super.new(name);
    endfunction
    task do_steps();
      step_seq s;
      m_step = step_seq::type_id::create("m_step");
      repeat (2) begin
        s = step_seq::type_id::create("s");
        s.start(m_sequencer);
      end
    endtask
    virtual task body();
      do_steps();
      m_step.start(m_sequencer);
    endtask
  endclass

  class call_sequencer extends uvm_sequencer #(call_item);
    `mini_component_utils(call_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class call_base_test extends uvm_test;
    `mini_component_utils(call_base_test)
    call_sequencer seqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      seqr = call_sequencer::type_id::create("seqr", this);
    endfunction
    virtual task traffic();
      step_seq s;
      s = step_seq::type_id::create("s");
      s.start(seqr);
    endtask
    virtual task run_phase(uvm_phase phase);
      phase.raise_objection(this);
      traffic();
      phase.drop_objection(this);
    endtask
  endclass

  class call_test extends call_base_test;
    `mini_component_utils(call_test)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    function void setup();
    endfunction
    virtual task traffic();
      call_seq c;
      c = call_seq::type_id::create("c");
      c.start(seqr);
    endtask
    task drain(int n);
      tail_seq t;
      t = tail_seq::type_id::create("t");
      t.start(seqr);
      if (n > 0)
        drain(n - 1);
    endtask
    virtual task run_phase(uvm_phase phase);
      super.run_phase(phase);
      this.drain(3);
      setup();
    endtask
  endclass

  class call_agent extends uvm_component;
    `mini_component_utils(call_agent)
    call_sequencer sqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      sqr = call_sequencer::type_id::create("sqr", this);
    endfunction
  endclass

  class call_vsequencer extends uvm_sequencer #(call_item);
    `mini_component_utils(call_vsequencer)
    call_sequencer agt_sqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class call_env extends uvm_component;
    `mini_component_utils(call_env)
    call_agent      agt;
    call_vsequencer vseqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt = call_agent::type_id::create("agt", this);
      vseqr = call_vsequencer::type_id::create("vseqr", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      vseqr.agt_sqr = agt.sqr;
    endfunction
  endclass

  class call_vseq extends uvm_sequence #(call_item);
    `mini_object_utils(call_vseq)
    call_vsequencer p_sequencer;
    function new(string name = "call_vseq");
      super.new(name);
    endfunction
    virtual task body();
      step_seq s;
      call_seq c;
      s = step_seq::type_id::create("s");
      s.start(p_sequencer.agt_sqr);
      c = call_seq::type_id::create("c");
      c.start(p_sequencer.agt_sqr);
    endtask
  endclass

  class vseq_test extends uvm_test;
    `mini_component_utils(vseq_test)
    call_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = call_env::type_id::create("env", this);
    endfunction
    virtual task run_phase(uvm_phase phase);
      call_vseq v;
      tail_seq t;
      call_sequencer elsewhere;
      phase.raise_objection(this);
      v = call_vseq::type_id::create("v");
      v.start(env.vseqr);
      t = tail_seq::type_id::create("t");
      t.start(this.env.agt.sqr);
      t.start(elsewhere);
      phase.drop_objection(this);
    endtask
  endclass

endpackage : seq_call_pkg
