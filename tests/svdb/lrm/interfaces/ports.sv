// D3b golden: interface ports.
interface bus_if;
  logic req;
  modport mst (output req);
  modport slv (input req);
endinterface

/// A port of one modport of one interface.
module producer (bus_if.mst bus, input logic clk);
  assign bus.req = clk;
endmodule

/// Generic interface ports, with and without a modport; an array of them.
module consumer (interface bus, interface.slv b2, bus_if links [2]);
endmodule

module nonansi (bus, clk);
  /// A non-ANSI interface port.
  bus_if.slv bus;
  input logic clk;
endmodule

module top;
  logic clk;
  bus_if b ();
  bus_if l [2] ();
  producer p (.bus(b), .clk);
  consumer c (.bus(b), .b2(b), .links(l));
  nonansi n (.bus(b), .clk);
endmodule
