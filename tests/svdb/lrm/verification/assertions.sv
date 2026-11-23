// D3d golden: concurrent assertions (LRM 16) written directly as module
// items -- labeled and anonymous, with and without a clock and
// ``disable iff``, and the ``cover``/``assume`` verbs. An *immediate*
// assertion (inside a procedural block) is not covered: it is a statement,
// and this pass does not walk statement bodies (same reason ``process`` and
// ``block`` are not extracted yet, D3e).
module top ();
  logic clk, rst, a, b;

  check_ab: assert property (@(posedge clk) disable iff (rst) a |-> b);
  assert property (@(posedge clk) a |-> b);
  cover property (@(posedge clk) a);
  assume property (a);
endmodule
