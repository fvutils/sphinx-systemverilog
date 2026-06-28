// A leaf register.
module rtl_leaf(input logic clk); endmodule

// An intermediate block.
module rtl_mid(input logic clk);
  rtl_leaf u_leaf(.clk(clk));
endmodule

// The design top.
module rtl_top;
  logic clk;
  rtl_mid u_mid0(.clk(clk));
  rtl_mid u_mid1(.clk(clk));
  rtl_leaf u_solo(.clk(clk));
endmodule
