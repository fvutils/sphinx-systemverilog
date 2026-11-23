// D3d golden: LRM 17 ``checker`` declarations, at root and in a package, an
// instantiated checker (its body's declarations come from that instance) and
// one never instantiated (arguments only), and a checker instance.

/// Checks that v holds on every clock.
checker chk_hold(logic clk, logic v, int n = 1);
  property p_v;
    @(posedge clk) v;
  endproperty
  a_v: assert property (p_v);
endchecker

checker chk_unused(logic c);
  sequence s_c;
    c;
  endsequence
endchecker

package pkg;
  checker chk_pkg(logic c);
  endchecker
endpackage

module top (input logic clk, input logic v);
  chk_hold u_chk (clk, v);
endmodule
