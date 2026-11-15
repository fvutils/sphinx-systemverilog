// Parameterized classes: the parameter list belongs in the signature.
package gen_pkg;

  // A value holder.
  //
  // :param T: the value type
  class holder #(type T = bit, int unsigned W = $bits(T));
    T value;
  endclass

  // A shaped port, with its parameters documented one by one.
  class shaped #(
      // the data width
      int DW = 8,
      int AW = 4    // the address width
  );
  endclass

  // A mixin.
  class mix #(type B = holder #(bit)) extends B;
  endclass

endpackage
