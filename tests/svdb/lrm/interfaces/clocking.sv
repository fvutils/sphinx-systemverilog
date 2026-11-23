// D3b golden: clocking blocks.
module dut (input logic clk, input logic rst_n);
  logic [7:0] a;
  logic [7:0] b;
  logic       v;
  logic       w;

  /// The default clocking block, declared in place.
  default clocking cb @(posedge clk);
    default input #1step output #2;
    /// Sampled.
    input a;
    output negedge v;            // Driven on the falling edge.
    input #1 output #3 w;
    inout b;
    input b0 = b[0];
  endclocking

  /// The global clock.
  global clocking gclk @(posedge clk); endclocking
endmodule

/// A default declared apart from its block.
module late (input logic clk);
  logic d;
  clocking c @(negedge clk);
    input d;
  endclocking
  default clocking c;
endmodule

interface ck_if (input logic clk);
  logic x;
  default clocking ck @(posedge clk);
    input x;
  endclocking
endinterface
