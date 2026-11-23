// D3e golden: LRM 23.10 ``defparam`` -- a single assignment, a list of two
// in one statement (two records), and one inside a generate block.

module leaf #(parameter int W = 1, parameter int D = 2) (input logic [W-1:0] a);
endmodule

module top;
  localparam int N = 8;
  logic [7:0] a;
  leaf u1 (a[0]);
  leaf u2 (a[1:0]);
  defparam u1.W = 1;
  defparam u2.W = 2, u2.D = N / 2;
  if (1) begin : g
    leaf u3 (a);
    defparam u3.W = N;
  end
endmodule
