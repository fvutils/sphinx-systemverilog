// D3c golden: named port connections, every shape LRM 23.3.2 allows.
module leaf (input logic a, output logic b, inout logic [1:0] c);
endmodule

/// A leaf instantiated with named connections: one bound, one explicitly
/// unconnected, one implicit (same name as the port).
module top;
  wire a, b;
  wire [1:0] c;
  leaf u1 (.a(a), .b(), .c(c));
  leaf u2 (.a, .b, .c);
endmodule
