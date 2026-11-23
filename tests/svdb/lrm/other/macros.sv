// D3e golden: LRM 22.5 `define -- function-like macros carry detail.params
// (name, and default when one is given, even an empty one); an object-like
// macro has no params; every non-empty body is a `body` record (text as
// written, line continuations kept).  A macro defined twice is one object,
// the last, with the first in detail.redefined_at.

`define DEPTH 16
`define MAX(a, b) ((a) > (b) ? (a) : (b))
`define CHECK(sig, clk = clk_i, msg = "bad", tag =) \
  assert property (@(posedge clk) !$isunknown(sig)) else $error(msg)
`define EMPTY
`define DEPTH 32

module macro_top;
  logic [`DEPTH-1:0] data;
endmodule
