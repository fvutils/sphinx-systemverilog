// The reference testbench for factory-override detection (U6-IMPL-1).
//
// A factory override is the one construct in UVM that makes a component tree
// *lie*. `build_phase` says `my_driver::type_id::create("drv", this)`, the
// extraction reads `my_driver`, and the simulation builds a `fast_driver`.
// Nothing in the source of the agent hints at it; the override is written
// somewhere else entirely, usually in a test.
//
// So the tree cannot be trusted without this, and it must not be silently
// "fixed" either --- Risk 2 in the plan says annotate, never resolve. An
// override is applied at run time, may be conditional, and an inst override is
// keyed on a hierarchical path that does not exist until the run.
//
// Every way of writing one is here, because they are genuinely different call
// shapes and a detector that handles the first two is a detector that misses
// half of real code:
//
//   * `set_type_override_by_type(a::get_type(), b::get_type())` --- the
//     `uvm_component` convenience wrapper, type-safe form;
//   * `factory.set_type_override_by_type(...)` --- the singleton, a different
//     declaring class with the same method name;
//   * `set_type_override("a", "b")` --- the by-name form, whose arguments are
//     string literals rather than types;
//   * `a::type_id::set_type_override(b::get_type())` --- the registry form,
//     where the *original* type is the specialization's own `Tname` and never
//     appears as an argument at all;
//   * `set_inst_override_by_type("env.agt.drv", a::get_type(), b::get_type())`
//     --- note the path comes *first* here and last on the factory form, which
//     is why argument positions are read per method;
//   * one written under an `if`, which may not run;
//   * one naming a type that does not exist, which is a typo the compiler
//     accepts in the by-name form and nothing reports.

`include "mini_uvm.svh"

package override_tb_pkg;
  import mini_uvm_pkg::*;

  class ovr_driver extends uvm_driver;
    `mini_component_utils(ovr_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class fast_driver extends ovr_driver;
    `mini_component_utils(fast_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class ovr_monitor extends uvm_monitor;
    `mini_component_utils(ovr_monitor)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class noisy_monitor extends ovr_monitor;
    `mini_component_utils(noisy_monitor)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class ovr_item extends uvm_sequence_item;
    `mini_object_utils(ovr_item)
    function new(string name = "ovr_item");
      super.new(name);
    endfunction
  endclass

  class big_item extends ovr_item;
    `mini_object_utils(big_item)
    function new(string name = "big_item");
      super.new(name);
    endfunction
  endclass

  class ovr_agent extends uvm_agent;
    `mini_component_utils(ovr_agent)
    ovr_driver  drv;
    ovr_monitor mon;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // Both of these read as their declared types in the tree, and neither is
      // what gets built.
      drv = ovr_driver::type_id::create("drv", this);
      mon = ovr_monitor::type_id::create("mon", this);
    endfunction
  endclass

  class ovr_env extends uvm_env;
    `mini_component_utils(ovr_env)
    ovr_agent agt;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt = ovr_agent::type_id::create("agt", this);
    endfunction
  endclass

  class ovr_test extends uvm_test;
    `mini_component_utils(ovr_test)
    ovr_env env;
    bit     want_noise = 1;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      uvm_factory f = uvm_factory::get();

      // 1. the component convenience wrapper, type-safe.
      set_type_override_by_type(ovr_driver::get_type(), fast_driver::get_type());

      // 2. the singleton. Same method name, different declaring class.
      f.set_type_override_by_type(ovr_item::get_type(), big_item::get_type());

      // 3. the by-name form, and a typo in it. `noisy_moniter` does not exist.
      //    This compiles, elaborates and simulates; the override silently never
      //    applies and the testbench quietly runs the type it was replacing.
      if (want_noise)
        set_type_override("ovr_monitor", "noisy_moniter");

      // 4. the registry form. The original type is never an argument.
      ovr_monitor::type_id::set_type_override(noisy_monitor::get_type());

      // 5. an inst override --- path first on this form.
      set_inst_override_by_type("env.agt.drv",
                                ovr_driver::get_type(), fast_driver::get_type());

      env = ovr_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : override_tb_pkg

module ovr_tb_top;
  import mini_uvm_pkg::*;
  import override_tb_pkg::*;

  initial begin
    run_test("ovr_test");
  end
endmodule
