// A design with structurally identical siblings, for exercising :collapse:.

// The repeated block.
module cl_leaf #(parameter int W = 8) (input logic clk);
endmodule

// Three identical children plus one that differs only by parameter.
module cl_mid #(parameter int W = 8) (input logic clk);
  cl_leaf #(.W(W)) u_a (.clk(clk));
  cl_leaf #(.W(W)) u_b (.clk(clk));
  cl_leaf #(.W(W)) u_c (.clk(clk));
  cl_leaf #(.W(64)) u_wide (.clk(clk));
endmodule

// Two identical mids.
module cl_top;
  logic clk;
  cl_mid #(.W(8)) u_m1 (.clk(clk));
  cl_mid #(.W(8)) u_m2 (.clk(clk));
endmodule
