// The shape that exposed the silent-drop bug (U1-TEST-2).
//
// `generated_ral_pkg` does not exist and is not meant to: it stands for a
// register model generated from RDL or IP-XACT as a separate build step, which
// is routinely absent when documentation is built --- in CI especially.
//
// The point of this fixture is that degradation is **local**.  The package
// still compiles, `good_agent` still elaborates, and `reg_env` still has a
// resolvable child.  A naive walk reports `reg_env` as containing exactly one
// component and looks entirely healthy while doing so.
//
// It has to report two: the agent, and `ral` as *unresolved*.  Otherwise a
// reader cannot distinguish a testbench with no register model from one whose
// register model failed to parse --- and the second is a build problem being
// concealed by the tool that exists to explain it.

`include "mini_uvm.svh"

package missing_dep_pkg;
  import mini_uvm_pkg::*;
  import generated_ral_pkg::*;   // deliberately absent

  class good_agent extends uvm_agent;
    `mini_component_utils(good_agent)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class reg_env extends uvm_env;
    `mini_component_utils(reg_env)
    good_agent   agt;
    my_reg_block ral;            // type comes from the absent package
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt = good_agent::type_id::create("agt", this);
      ral = my_reg_block::type_id::create("ral", this);
    endfunction
  endclass

  class reg_test extends uvm_test;
    `mini_component_utils(reg_test)
    reg_env env;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      env = reg_env::type_id::create("env", this);
    endfunction
  endclass

endpackage : missing_dep_pkg

module reg_tb_top;
  import mini_uvm_pkg::*;
  import missing_dep_pkg::*;

  initial begin
    run_test("reg_test");
  end
endmodule
