// The reference testbench for per-class partial elaboration and stitching
// (docs/design/uvm-stitching-plan.md §5.1).
//
// Each class or statement pins down one behaviour of the stitcher, and the
// tests name the case they rely on.  Several tests are roots, so one database
// answers every case:
//
//   * `st_test`      --- factory ordering, chains, inst vs type, siblings,
//                        overrides in `new`, a helper before `create`, an
//                        override through another object, one in run_phase;
//   * `derived_test` --- virtual dispatch of `set_overrides()` and `super`;
//   * `late_test`    --- a helper called *after* `create(env)`;
//   * `helper_test`  --- creates and connections in helpers, conditional and
//                        looped helpers, helper recursion, a dangling handle;
//   * `inherit_test` --- an inherited build_phase/connect_phase, super calls,
//                        and a build_phase that drops its base's.
//
// The module `initial` registers a global override, which UVM applies before
// any test is built.

`include "mini_uvm.svh"

package stitch_tb_pkg;
  import mini_uvm_pkg::*;

  class st_item extends uvm_sequence_item;
    `mini_object_utils(st_item)
    function new(string name = "st_item");
      super.new(name);
    endfunction
  endclass

  // -- leaves ------------------------------------------------------------------

  class st_drv extends uvm_driver;
    `mini_component_utils(st_drv)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class fast_drv extends st_drv;
    `mini_component_utils(fast_drv)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class slow_drv extends st_drv;
    `mini_component_utils(slow_drv)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class st_mon extends uvm_monitor;
    `mini_component_utils(st_mon)
    uvm_analysis_port #(st_item) ap;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap", this);
    endfunction
  endclass

  // A chain: st_mon -> mon_b -> mon_c.
  class mon_b extends st_mon;
    `mini_component_utils(mon_b)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class mon_c extends mon_b;
    `mini_component_utils(mon_c)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class mon_x extends st_mon;
    `mini_component_utils(mon_x)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class st_seqr extends uvm_sequencer #(st_item);
    `mini_component_utils(st_seqr)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class top_seqr extends st_seqr;
    `mini_component_utils(top_seqr)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class big_seqr extends st_seqr;
    `mini_component_utils(big_seqr)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class st_scb extends uvm_scoreboard;
    `mini_component_utils(st_scb)
    uvm_analysis_imp #(st_item, st_scb) exp;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      exp = new("exp", this);
    endfunction
    function void write(st_item t);
    endfunction
  endclass

  class big_scb extends st_scb;
    `mini_component_utils(big_scb)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // An abstract base nothing instantiates: records, no node, no issue.
  virtual class abs_comp extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // -- the agent ---------------------------------------------------------------

  class st_agent extends uvm_agent;
    `mini_component_utils(st_agent)
    st_drv  drv;
    st_mon  mon;
    st_seqr seqr;
    bit     is_active = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mon = st_mon::type_id::create("mon", this);
      if (is_active) begin
        drv  = st_drv::type_id::create("drv", this);
        seqr = st_seqr::type_id::create("seqr", this);
      end
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      if (is_active)
        drv.seq_item_port.connect(seqr.seq_item_export);
    endfunction
  endclass

  // Inherits all of its structure through an override.
  class big_agent extends st_agent;
    `mini_component_utils(big_agent)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // -- envs and inheritance ----------------------------------------------------

  class base_env extends uvm_env;
    `mini_component_utils(base_env)
    st_agent agt_a;
    st_scb   scb;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt_a = st_agent::type_id::create("agt_a", this);
      scb   = st_scb::type_id::create("scb", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      agt_a.mon.ap.connect(scb.exp);
    endfunction
  endclass

  // No build_phase or connect_phase of its own: both are inherited.
  class inh_env extends base_env;
    `mini_component_utils(inh_env)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // super first, then its own; registers an override in `new`.
  class sup_env extends base_env;
    `mini_component_utils(sup_env)
    st_agent agt_b;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
      set_type_override_by_type(st_scb::get_type(), big_scb::get_type());
    endfunction
    virtual function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agt_b = st_agent::type_id::create("agt_b", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      super.connect_phase(phase);
      agt_b.mon.ap.connect(scb.exp);
      agt_b.drv.seq_item_port.connect(agt_b.seqr.seq_item_export);
    endfunction
  endclass

  class sup_env2 extends sup_env;
    `mini_component_utils(sup_env2)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // Its own build_phase without super: base_env's children are not built.
  class nosup_env extends base_env;
    `mini_component_utils(nosup_env)
    st_agent agt_b;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt_b = st_agent::type_id::create("agt_b", this);
    endfunction
  endclass

  // -- helpers -----------------------------------------------------------------

  class rec_comp extends uvm_component;
    `mini_component_utils(rec_comp)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      rec_a(3);
    endfunction
    function void rec_a(int n);
      if (n > 0) rec_b(n - 1);
    endfunction
    function void rec_b(int n);
      if (n > 0) rec_a(n - 1);
    endfunction
  endclass

  class helper_env extends uvm_env;
    `mini_component_utils(helper_env)
    st_agent agts[2];
    st_agent ghost;
    st_scb   scb;
    rec_comp rec;
    bit      has_scb = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      build_agents();
      if (has_scb) build_scb();
      rec = rec_comp::type_id::create("rec", this);
    endfunction
    function void build_agents();
      for (int i = 0; i < 2; i++)
        agts[i] = st_agent::type_id::create($sformatf("agts%0d", i), this);
    endfunction
    function void build_scb();
      scb = st_scb::type_id::create("scb", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      connect_agents();
      ghost.mon.ap.connect(scb.exp);
    endfunction
    function void connect_agents();
      foreach (agts[i])
        agts[i].mon.ap.connect(scb.exp);
    endfunction
  endclass

  // -- configuration ----------------------------------------------------------

  // Built before `b_agent` (children are built in name order), so what it
  // registers reaches b_agent's subtree:
  //   * replace=0 for a type the module already overrides: ignored;
  //   * a path relative to *itself*: `uvm_test_top.a_cfg.b_agent.mon`, which
  //     matches nothing;
  //   * an absolute path into its sibling: applies.
  class a_cfg_comp extends uvm_component;
    `mini_component_utils(a_cfg_comp)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      uvm_factory f = uvm_factory::get();
      set_type_override_by_type(st_seqr::get_type(), big_seqr::get_type(), 0);
      set_inst_override_by_type("b_agent.mon", st_mon::get_type(), mon_x::get_type());
      f.set_inst_override_by_type(st_drv::get_type(), slow_drv::get_type(), "uvm_test_top.b_agent.drv");
    endfunction
  endclass

  // Not a component: its overrides run through another object.
  class st_cfg extends uvm_object;
    `mini_object_utils(st_cfg)
    function new(string name = "st_cfg");
      super.new(name);
    endfunction
    function void apply_overrides();
      uvm_factory f = uvm_factory::get();
      f.set_type_override_by_type(st_item::get_type(), st_item::get_type());
    endfunction
  endclass

  // -- tests -------------------------------------------------------------------

  class st_test extends uvm_test;
    `mini_component_utils(st_test)
    sup_env    env;
    a_cfg_comp a_cfg;
    st_agent   b_agent;
    st_cfg     cfg;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void set_overrides();
      set_type_override_by_type(st_drv::get_type(), fast_drv::get_type());
    endfunction
    virtual function void build_phase(uvm_phase phase);
      uvm_factory f = uvm_factory::get();
      super.build_phase(phase);
      set_overrides();
      cfg = st_cfg::type_id::create("cfg");
      cfg.apply_overrides();
      env = sup_env::type_id::create("env", this);
      // after the create: the env keeps sup_env
      set_type_override_by_type(sup_env::get_type(), sup_env2::get_type());
      set_type_override_by_type(st_mon::get_type(), mon_b::get_type());
      set_type_override_by_type(mon_b::get_type(), mon_c::get_type());
      set_inst_override_by_type("env.agt_a.*", st_drv::get_type(), slow_drv::get_type());
      f.set_inst_override_by_type(st_mon::get_type(), mon_x::get_type(), "uvm_test_top.env.agt_b.mon");
      a_cfg   = a_cfg_comp::type_id::create("a_cfg", this);
      b_agent = st_agent::type_id::create("b_agent", this);
    endfunction
    virtual task run_phase(uvm_phase phase);
      set_type_override_by_type(st_scb::get_type(), st_scb::get_type());
    endtask
  endclass

  class derived_test extends st_test;
    `mini_component_utils(derived_test)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void set_overrides();
      super.set_overrides();
      set_type_override_by_type(st_agent::get_type(), big_agent::get_type());
    endfunction
  endclass

  class late_test extends uvm_test;
    `mini_component_utils(late_test)
    sup_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    function void set_overrides();
      set_type_override_by_type(sup_env::get_type(), sup_env2::get_type());
      set_type_override_by_type(st_drv::get_type(), fast_drv::get_type());
      st_mon::type_id::set_inst_override(mon_c::get_type(), "env.agt_b.mon", this);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = sup_env::type_id::create("env", this);
      set_overrides();
    endfunction
  endclass

  class helper_test extends uvm_test;
    `mini_component_utils(helper_test)
    helper_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = helper_env::type_id::create("env", this);
    endfunction
  endclass

  // Instantiates the inheritance cases, each by its own type.
  class inherit_test extends uvm_test;
    `mini_component_utils(inherit_test)
    inh_env   inh;
    nosup_env nosup;
    sup_env   sup;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      inh   = inh_env::type_id::create("inh", this);
      nosup = nosup_env::type_id::create("nosup", this);
      sup   = sup_env::type_id::create("sup", this);
    endfunction
  endclass

endpackage : stitch_tb_pkg

module st_tb_top;
  import mini_uvm_pkg::*;
  import stitch_tb_pkg::*;

  initial begin
    uvm_factory f;
    f = uvm_factory::get();
    f.set_type_override_by_type(st_seqr::get_type(), top_seqr::get_type());
    run_test("st_test");
  end
endmodule
