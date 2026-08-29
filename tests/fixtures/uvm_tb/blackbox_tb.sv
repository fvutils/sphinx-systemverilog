// Boundaries the walk is expected to stop at (U1-TEST-4).
//
// Unlike `missing_dep_tb.sv`, everything here **resolves**.  That is the point:
// black-boxing is a deliberate editorial choice about how far to look, not a
// failure to resolve, and the two must not be confused in the output.  A
// component that is present but not descended into is `opaque`; one that could
// not be resolved at all is `unresolved`.
//
// Three boundaries are exercised:
//
//   * `my_reg_block`, matched by the **default** `sv_uvm_blackbox_bases`
//     (`uvm_reg_block`) --- a register model is generated, so its internals are
//     an artifact of another toolchain rather than something to document here;
//   * `acme_vip_agent`, matched by a **glob** on the type name;
//   * TLM ports, stopped at by the **always-on library rule**.

`include "mini_uvm.svh"

package blackbox_tb_pkg;
  import mini_uvm_pkg::*;

  // The register model.  Its contents exist, and are still not walked into.
  class my_reg_field extends uvm_component;
    `mini_component_utils(my_reg_field)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class my_reg_block extends uvm_reg_block;
    `mini_component_utils(my_reg_block)
    my_reg_field f0;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      f0 = my_reg_field::type_id::create("f0", this);
    endfunction
  endclass

  // Vendor VIP, matched by glob rather than by base class.
  class acme_vip_driver extends uvm_driver;
    `mini_component_utils(acme_vip_driver)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class acme_vip_agent extends uvm_agent;
    `mini_component_utils(acme_vip_agent)
    acme_vip_driver drv;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      drv = acme_vip_driver::type_id::create("drv", this);
    endfunction
  endclass

  // An ordinary component, so the tests can show the boundaries are selective.
  class plain_agent extends uvm_agent;
    `mini_component_utils(plain_agent)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class bb_env extends uvm_env;
    `mini_component_utils(bb_env)
    my_reg_block   ral;
    acme_vip_agent vip;
    plain_agent    agt;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      ral = my_reg_block::type_id::create("ral", this);
      vip = acme_vip_agent::type_id::create("vip", this);
      agt = plain_agent::type_id::create("agt", this);
    endfunction
  endclass

  class bb_test extends uvm_test;
    `mini_component_utils(bb_test)
    bb_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = bb_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : blackbox_tb_pkg

module bb_tb_top;
  import mini_uvm_pkg::*;
  import blackbox_tb_pkg::*;

  initial begin
    run_test("bb_test");
  end
endmodule
