// The one shape `bridge_tb.sv` cannot answer: a virtual interface reached
// through a `typedef`.
//
// Pairing a binding to its readers is narrowed by interface type, and that
// narrowing is only safe if two spellings of the same interface unify. Here
// they deliberately do not agree in source: the `set` writes `virtual td_if`
// in full and the `get` writes the typedef. If slang kept them apart, the
// binding would report an orphan that is not there --- which is precisely the
// failure the narrowing exists to avoid, arriving from the other direction.
//
// Kept out of `bridge_tb.sv` so the row counts there stay legible, and out of
// the documentation build because it demonstrates nothing a reader needs.

`include "mini_uvm.svh"

interface td_if;
  logic clk;
endinterface

module td_dut(td_if bus);
endmodule

package bridge_typedef_pkg;
  import mini_uvm_pkg::*;

  typedef virtual td_if td_vif_t;

  class td_agent extends uvm_agent;
    `mini_component_utils(td_agent)
    td_vif_t vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      // Spelled as the typedef; the `set` in the top module spells it out.
      void'(uvm_config_db #(td_vif_t)::get(this, "", "vif", vif));
    endfunction
  endclass

  class td_test extends uvm_test;
    `mini_component_utils(td_test)
    td_agent agt;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      agt = td_agent::type_id::create("agt", this);
    endfunction
  endclass

endpackage : bridge_typedef_pkg

module td_top;
  import mini_uvm_pkg::*;
  import bridge_typedef_pkg::*;

  td_if  u_if();
  td_dut u_dut(.bus(u_if));

  initial begin
    uvm_config_db #(virtual td_if)::set(null, "*", "vif", u_if);
    run_test("td_test");
  end
endmodule
