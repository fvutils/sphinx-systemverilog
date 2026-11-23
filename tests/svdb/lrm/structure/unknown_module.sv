// D3c golden: a module that instantiates something not in this compilation.
// It is kept as an object (``state: unresolved``, ``of_kind: unknown``), with
// its connections recorded exactly as written; nothing about its ports can
// be known.
module top;
  wire a, b;

  /// Not defined anywhere in these sources.
  acme_uvc u1 (.clk(a), .rst_n(b));
endmodule
