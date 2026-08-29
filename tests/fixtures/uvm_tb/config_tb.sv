// The reference testbench for `config_db` extraction and orphan detection
// (U2-TEST-1).  Every access here pins one extraction or pairing behaviour:
//
//   * a **matched** set/get pair --- the ordinary case;
//   * a get written inside an `if (!...)` **condition**, which is the dominant
//     UVM idiom and which a statement-level walker never reaches;
//   * a get written inside `void'(...)`, a `Conversion` wrapping the call;
//   * an **orphaned set** with a typo'd field name --- the silent bug this
//     whole view exists to catch;
//   * an **orphaned get** whose field nothing ever sets;
//   * a **glob field** set, which must pair with the literal get it could
//     match rather than being reported as an orphan;
//   * a **computed** field name, which cannot be paired at all and must be
//     counted and reported rather than quietly dropped;
//   * a set from a **top module** with `cntxt = null`, which is how a virtual
//     interface reaches the testbench and which lives outside any class.

`include "mini_uvm.svh"

interface cfg_if;
  logic clk;
endinterface

package config_tb_pkg;
  import mini_uvm_pkg::*;

  class cfg_driver extends uvm_driver;
    `mini_component_utils(cfg_driver)
    int    n_items;
    string mode;
    int    depth;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // The dominant idiom: the `get` is an *if-condition*, not a statement.
      // A statement-level walker sees a `Conditional` here and nothing else.
      if (!uvm_config_db #(int)::get(this, "", "n_items", n_items))
        n_items = 1;
      // A `get` inside `void'(...)`, i.e. wrapped in a `Conversion`.
      void'(uvm_config_db #(string)::get(this, "", "mode", mode));
      // Nothing anywhere sets this: an orphaned *get*.  The component reads a
      // knob no one provides, so it silently keeps its default forever.
      void'(uvm_config_db #(int)::get(this, "", "unset_depth", depth));
    endfunction
  endclass

  class cfg_agent extends uvm_agent;
    `mini_component_utils(cfg_agent)
    cfg_driver drv;
    int        n_dyn;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // Matched: `cfg_driver` reads "n_items".
      uvm_config_db #(int)::set(this, "drv", "n_items", 8);
      // Wildcard *scope*.  Scope plays no part in pairing (see the model
      // docstring); this exists to prove a glob scope is reported verbatim and
      // does not disturb the field match.
      uvm_config_db #(string)::set(this, "*", "mode", "fast");
      // Glob *field*: it could match "n_items", so it is not an orphan.
      uvm_config_db #(int)::set(this, "drv", "n_*", 2);
      // THE BUG.  "n_itmes" is a typo for "n_items".  It compiles, it
      // simulates, and it does nothing at all.
      uvm_config_db #(int)::set(this, "drv", "n_itmes", 4);
      drv = cfg_driver::type_id::create("drv", this);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
      // A computed field name: not knowable statically, so it is excluded from
      // pairing and counted rather than guessed at.
      uvm_config_db #(int)::set(this, "drv", $sformatf("k%0d", n_dyn), 1);
    endfunction
  endclass

  class cfg_env extends uvm_env;
    `mini_component_utils(cfg_env)
    cfg_agent agt;
    bit       enable_extra = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // Conditional: the set may not happen.
      if (enable_extra)
        uvm_config_db #(int)::set(this, "agt.drv", "n_items", 16);
      agt = cfg_agent::type_id::create("agt", this);
    endfunction
  endclass

  class cfg_test extends uvm_test;
    `mini_component_utils(cfg_test)
    cfg_env env;
    virtual cfg_if vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // The other half of the top-module set below.
      if (!uvm_config_db #(virtual cfg_if)::get(this, "", "vif", vif))
        $display("no vif");
      env = cfg_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : config_tb_pkg

module cfg_tb_top;
  import mini_uvm_pkg::*;
  import config_tb_pkg::*;

  cfg_if u_if();

  initial begin
    // `cntxt = null`, so the scope string is absolute.  This is the shape the
    // RTL bridge reads, and it lives in a module rather than a class --- the
    // walk has to scan both.
    uvm_config_db #(virtual cfg_if)::set(null, "uvm_test_top", "vif", u_if);
    run_test("cfg_test");
  end
endmodule
