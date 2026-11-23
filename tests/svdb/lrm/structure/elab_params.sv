// D3c golden: the same definition elaborated twice, at two parameter sets.
// ``leaf`` gets two distinct ``elab`` records (one per ``key``); ``top``
// elaborates once, with ``count`` 2 for the narrow site and 3 for the wide
// one (an instance array).
module leaf #(parameter int W = 8) (input logic [W-1:0] a);
endmodule

module top ();
  logic [7:0] a8;
  logic [15:0] a16;
  leaf #(.W(8)) u_n0 (a8);
  leaf #(.W(8)) u_n1 (a8);
  leaf #(.W(16)) u_w [2:0] (a16);
endmodule
