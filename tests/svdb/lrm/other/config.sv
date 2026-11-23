// D3e golden: LRM 33 ``config``, recorded but not applied: its ``design``
// cells and each rule as text.

module leaf (input a);
endmodule

module top;
  wire a;
  leaf u_leaf (a);
endmodule

/// The configuration for the top-level build.
config cfg;
  design work.top;
  default liblist work;
  instance top.u_leaf use work.leaf;
endconfig
