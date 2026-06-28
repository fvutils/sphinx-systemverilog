// A configurable up-counter.
//
// Counts clock edges into a WIDTH-bit register, with synchronous reset.
module counter #(
  parameter int WIDTH = 8,        // counter width in bits
  localparam int MAX = (1 << WIDTH) - 1
)(
  input  logic             clk,   // clock
  // active-high synchronous reset
  input  logic             rst,
  output logic [WIDTH-1:0] count
);
endmodule
