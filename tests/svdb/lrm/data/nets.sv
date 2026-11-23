// D3a golden: nets (LRM 6.5-6.7).

/// Every built-in net type, and the declaration forms around them.
module nets (
  input  wire [7:0] din,   // An ANSI port: not a net object of its own.
  output logic      dout
);
  /// A plain wire with an initializer.
  wire [7:0] w = din;
  tri        t;
  wand       wa;
  wor        wo;
  triand     ta;
  trior      tro;
  tri0       t0;
  tri1       t1;
  uwire      uw;
  supply0    gnd;
  supply1    vdd;
  trireg (small) vectored [3:0] charge;  // Charge strength and expansion hint.
  wire (strong0, pull1) #3 driven;
  wire scalared [1:0] sc;
  wire signed [3:0] mem [4];
  interconnect ic;

  assign implicit_a = din[0];
  leaf u_leaf (.x(implicit_b));
endmodule

/// A non-ANSI port list: the port and its net are one object.
module leaf (x);
  input x;
  wire x;
endmodule
