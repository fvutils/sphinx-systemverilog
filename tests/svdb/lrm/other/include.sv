// D3e golden: LRM 22.4 `include -- one edge per directive (file and line),
// including one nested in an included file; a file included twice gives two
// edges.  Objects declared in an included file carry its file id.

`include "include_defs.svh"

module inc_top;
  `include "include_defs.svh"
  logic [W-1:0] data;
endmodule
