// A design parameterized by a configuration struct, the shape modern RTL uses
// (CVA6 passes a config_pkg::cva6_cfg_t this way).  The struct elaborates to a
// single very wide integer, so its *value* is unreadable and its *type* is the
// only useful thing to show.
package cfg_pkg;

  typedef struct packed {
    logic [31:0] XLEN;
    logic [31:0] DEPTH;
    logic [31:0] LANES;
    logic [63:0] FEATURES;
    logic [63:0] RESERVED;
  } core_cfg_t;

  localparam core_cfg_t SmallCfg = '{
      XLEN: 32, DEPTH: 4, LANES: 1, FEATURES: 64'h0, RESERVED: 64'h0
  };

  localparam core_cfg_t BigCfg = '{
      XLEN: 64, DEPTH: 16, LANES: 4, FEATURES: 64'hffff, RESERVED: 64'h0
  };

endpackage

// A leaf configured by the whole struct.
module cfg_leaf
  import cfg_pkg::*;
#(
    parameter core_cfg_t Cfg = SmallCfg
) (
    input logic clk
);
endmodule

// A block that passes its configuration straight down.
module cfg_block
  import cfg_pkg::*;
#(
    parameter core_cfg_t Cfg  = SmallCfg,
    parameter int        TAG  = 0
) (
    input logic clk
);
  cfg_leaf #(.Cfg(Cfg)) u_leaf (.clk(clk));
endmodule

// Two blocks under genuinely different configurations.
module cfg_top;
  import cfg_pkg::*;
  logic clk;

  cfg_block #(.Cfg(SmallCfg), .TAG(1)) u_small (.clk(clk));
  cfg_block #(.Cfg(BigCfg),   .TAG(2)) u_big   (.clk(clk));
endmodule
