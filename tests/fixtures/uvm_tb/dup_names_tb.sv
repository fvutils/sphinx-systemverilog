// Two packages that each define a component called `agent`, for the
// per-class extraction (docs/design/uvm-stitching-plan.md, A3): keyed by
// qualified name, the two stay apart.

`include "mini_uvm.svh"

package dup_a_pkg;
  import mini_uvm_pkg::*;
  class drv_t extends uvm_driver;
    `mini_component_utils(drv_t)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass
  class agent extends uvm_agent;
    `mini_component_utils(agent)
    drv_t drv;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      drv = drv_t::type_id::create("drv", this);
    endfunction
  endclass
endpackage

package dup_b_pkg;
  import mini_uvm_pkg::*;
  class mon_t extends uvm_monitor;
    `mini_component_utils(mon_t)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass
  class agent extends uvm_agent;
    `mini_component_utils(agent)
    mon_t mon;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      mon = mon_t::type_id::create("mon", this);
    endfunction
  endclass

  class env extends uvm_env;
    `mini_component_utils(env)
    dup_a_pkg::agent a;
    agent            b;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      a = dup_a_pkg::agent::type_id::create("a", this);
      b = agent::type_id::create("b", this);
    endfunction
  endclass
endpackage
