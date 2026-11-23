// D3c golden: ".*" port connections (LRM 23.3.3.4). The definition is known,
// so the wildcard is expanded into one implicit entry per port, alongside
// the wildcard marker itself.
module leaf (input logic a, output logic b, inout logic [1:0] c);
endmodule

module top;
  wire a, b;
  wire [1:0] c;

  /// Every port picked up by name.
  leaf u1 (.*);

  /// The wildcard still covers ``b`` and ``c``; ``a`` is overridden.
  leaf u2 (.a(1'b0), .*);
endmodule
