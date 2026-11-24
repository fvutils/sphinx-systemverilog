// A VIP built into its own database; testbenches link against it
// (docs/design/svdb-linking-plan.md).

`include "mini_uvm.svh"
`include "axi_macros.svh"

interface axi_if #(parameter int AW = `AXI_ADDR_W, parameter int DW = 32) (input logic clk, input logic rst_n);
  typedef logic [AW-1:0] addr_t;
  logic [AW-1:0] addr;
  logic [DW-1:0] data;
  logic          valid;
  logic          ready;
  clocking cb @(posedge clk);
    output addr, data, valid;
    input  ready;
  endclocking
  modport mst(output addr, data, valid, input ready, clk);
  modport slv(input addr, data, valid, clk, output ready);
  function automatic bit busy();
    return valid && !ready;
  endfunction
  task wait_ready(int cycles = 1);
  endtask
endinterface

package axi_types_pkg;
  parameter int MAX_BURST = 16;
  localparam int LEN_W = $clog2(MAX_BURST);
  typedef enum logic [1:0] { FIXED = 0, INCR = 1, WRAP = 2 } burst_e;
  typedef struct packed { logic [3:0] id; burst_e burst; } attr_t;
  typedef bit [7:0] byte_q_t[$];
endpackage

package axi_vip_pkg;
  import mini_uvm_pkg::*;
  import axi_types_pkg::*;

  typedef class axi_agent;

  class axi_item extends uvm_sequence_item;
    `mini_object_utils(axi_item)
    rand bit [31:0] addr;
    rand burst_e    burst;
    randc bit [3:0] id;
    byte_q_t        data;
    static int      count;
    const int       limit = 4;
    constraint c_len { data.size() <= MAX_BURST; }
    function new(string name = "axi_item");
      super.new(name);
    endfunction
    virtual function string convert2string();
      return $sformatf("%h", addr);
    endfunction
    extern function bit is_write();
  endclass

  function bit axi_item::is_write();
    return addr[0];
  endfunction

  virtual class axi_base_driver #(type REQ = axi_item, int DEPTH = 2) extends uvm_driver;
    protected REQ pending[$];
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    pure virtual task drive(REQ req, output bit ok);
    static function int depth();
      return DEPTH;
    endfunction
    local function void reset_q();
    endfunction
  endclass

  class axi_driver extends axi_base_driver #(axi_item, 4);
    `mini_component_utils(axi_driver)
    virtual axi_if.mst vif;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual task drive(axi_item req, output bit ok);
      ok = 1;
    endtask
  endclass

  class axi_sequencer extends uvm_sequencer #(axi_item);
    `mini_component_utils(axi_sequencer)
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class axi_agent extends uvm_agent;
    `mini_component_utils(axi_agent)
    axi_driver    drv;
    axi_sequencer seqr;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    virtual function void build_phase(uvm_phase phase);
      drv  = axi_driver::type_id::create("drv", this);
      seqr = axi_sequencer::type_id::create("seqr", this);
    endfunction
  endclass

  function automatic int clog2_bursts(int n = MAX_BURST);
    return $clog2(n);
  endfunction
endpackage
