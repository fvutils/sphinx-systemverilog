// D3d golden: LRM 16.8 ``sequence`` and 16.12 ``property`` declarations, at
// package scope and at module scope, with untyped, typed and defaulted
// arguments, and a concurrent assertion that uses them.
package pkg;
  /// a then b on the next cycle.
  sequence s_pair(a, b);
    a ##1 b;
  endsequence
endpackage

module top (input logic clk, input logic a, input logic b);
  /// No arguments.
  sequence s1;
    a ##1 b;
  endsequence

  sequence s_delay(x, int n = 2);
    @(posedge clk) x ##n b;
  endsequence

  /// Holds after reset.
  property p_follow(logic x);
    @(posedge clk) disable iff (!a) x |=> s1;
  endproperty

  assert property (p_follow(a));
endmodule
