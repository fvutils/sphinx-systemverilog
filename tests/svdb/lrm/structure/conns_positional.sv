// D3c golden: positional port connections, with a trailing unconnected one,
// and an instance array.
module leaf (input logic a, output logic b, inout logic [1:0] c);
endmodule

module top;
  wire a, b;
  wire [1:0] c;

  /// Positional, with the last port left unconnected.
  leaf u1 (a, b, );

  /// An instance array: one site, several elaborated instances.
  leaf arr [3:0] (a, b, c);
endmodule
