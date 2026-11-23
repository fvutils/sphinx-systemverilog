// D3e golden: LRM 29 user-defined primitives -- combinational and sequential
// (with an ``initial`` value) -- and an instance of each (``of_kind:
// primitive``, recorded without Options.structure_gates).

/// A 2:1 multiplexer.
primitive mux2 (output o, input a, b, s);
  table
    0 ? 0 : 0;
    1 ? 0 : 1;
    ? 0 1 : 0;
    ? 1 1 : 1;
  endtable
endprimitive

/// A rising-edge flop that powers up low.
primitive dff_udp (output reg q, input d, clk);
  initial q = 1'b0;
  table
    0 (01) : ? : 0;
    1 (01) : ? : 1;
    ? (1?) : ? : -;
    (??) ? : ? : -;
  endtable
endprimitive

module top (input a, b, s, clk, output o, q);
  mux2 u_mux (o, a, b, s);
  dff_udp u_ff (q, o, clk);
endmodule
