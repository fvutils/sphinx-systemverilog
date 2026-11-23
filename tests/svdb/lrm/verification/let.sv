// D3d golden: LRM 11.12 ``let``, at package scope and at module scope, with
// typed arguments, an untyped one, and a default value.
package pkg;
  /// The larger of two values.
  let max2(int a, b) = (a > b) ? a : b;
endpackage

module top ();
  let is_hi(x, int thresh = 5) = x > thresh;
endmodule
