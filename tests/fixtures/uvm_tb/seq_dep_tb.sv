// Sequence dependencies that the task alone does not show (run-phase plan,
// phase 3).
//
//   * `warm` is a member, declared as `base_seq` and created as `warm_seq` in
//     `build_phase`: the catalog must name `warm_seq`, from another method.
//   * `dep_test` registers an unconditional type override of `base_seq` by
//     `fast_seq`: the `base_seq` the run_phase creates through the factory is
//     a `fast_seq` when it runs, and what `fast_seq` starts is a dependency.
//   * `byhand` is built with `new`, which no override can replace.
//   * the override of `cool_seq` is conditional, and `other_test` overrides
//     `warm_seq`: neither is certain for `dep_test`, so both are "possible".

`include "mini_uvm.svh"

package seq_dep_pkg;
  import mini_uvm_pkg::*;

  class dep_item extends uvm_sequence_item;
    `mini_object_utils(dep_item)
    function new(string name = "dep_item");
      super.new(name);
    endfunction
  endclass

  class base_seq extends uvm_sequence #(dep_item);
    `mini_object_utils(base_seq)
    function new(string name = "base_seq");
      super.new(name);
    endfunction
    virtual task body();
      dep_item it;
      `mini_do(it)
    endtask
  endclass

  class burst_seq extends uvm_sequence #(dep_item);
    `mini_object_utils(burst_seq)
    function new(string name = "burst_seq");
      super.new(name);
    endfunction
    virtual task body();
      dep_item it;
      repeat (4) `mini_do(it)
    endtask
  endclass

  class fast_seq extends base_seq;
    `mini_object_utils(fast_seq)
    function new(string name = "fast_seq");
      super.new(name);
    endfunction
    virtual task body();
      burst_seq b;
      b = burst_seq::type_id::create("b");
      b.start(m_sequencer);
    endtask
  endclass

  class warm_seq extends base_seq;
    `mini_object_utils(warm_seq)
    function new(string name = "warm_seq");
      super.new(name);
    endfunction
  endclass

  class cool_seq extends uvm_sequence #(dep_item);
    `mini_object_utils(cool_seq)
    function new(string name = "cool_seq");
      super.new(name);
    endfunction
    virtual task body();
      dep_item it;
      `mini_do(it)
    endtask
  endclass

  class cold_seq extends cool_seq;
    `mini_object_utils(cold_seq)
    function new(string name = "cold_seq");
      super.new(name);
    endfunction
  endclass

  class dep_sequencer extends uvm_sequencer #(dep_item);
    `mini_component_utils(dep_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class dep_test extends uvm_test;
    `mini_component_utils(dep_test)
    dep_sequencer seqr;
    base_seq      warm;
    bit           slow;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      seqr = dep_sequencer::type_id::create("seqr", this);
      warm = warm_seq::type_id::create("warm");
      set_type_override_by_type(base_seq::get_type(), fast_seq::get_type());
      if (slow)
        set_type_override_by_type(cool_seq::get_type(), cold_seq::get_type());
    endfunction
    virtual task run_phase(uvm_phase phase);
      base_seq s;
      base_seq byhand;
      cool_seq c;
      phase.raise_objection(this);
      warm.start(seqr);
      s = base_seq::type_id::create("s");
      s.start(seqr);
      byhand = new("byhand");
      byhand.start(seqr);
      c = cool_seq::type_id::create("c");
      c.start(seqr);
      phase.drop_objection(this);
    endtask
  endclass

  class other_test extends dep_test;
    `mini_component_utils(other_test)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      set_type_override_by_type(warm_seq::get_type(), cool_seq::get_type());
    endfunction
  endclass

endpackage : seq_dep_pkg
