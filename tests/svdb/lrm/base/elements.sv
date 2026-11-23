// D3 golden: the kinds the front end emitted at D2 parity.

/// The bus width.
`define BUS_W 8
`define MAX(a, b) ((a) > (b) ? (a) : (b))

/// A package with one of each class member.
package base;
  /// A transaction.
  virtual class txn;
    /// Payload.
    rand bit [`BUS_W-1:0] data;
    /// Keep data small.
    constraint c_small { data < 16; }
    /// Sampled on demand.
    covergroup cg;
      cp_data: coverpoint data;
    endgroup
    function new();
      cg = new();
    endfunction
    /// Pure: every transaction prints itself.
    pure virtual function string show();
    /// Waits.
    task wait_cycles(int n);
    endtask
  endclass
endpackage

/// An interface.
interface bus #(parameter int W = 8) (input logic clk);
endinterface

/// A program.
program prog (input logic clk);
endprogram
