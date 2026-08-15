// A deliberately large elaboration: 4 levels of 8-way generate loops.
// Used to prove that the instance budget truncates rather than hanging.
module deep_leaf(input logic clk);
endmodule

module deep_l3(input logic clk);
  for (genvar i = 0; i < 8; i++) begin : g
    deep_leaf u(.clk(clk));
  end
endmodule

module deep_l2(input logic clk);
  for (genvar i = 0; i < 8; i++) begin : g
    deep_l3 u(.clk(clk));
  end
endmodule

module deep_l1(input logic clk);
  for (genvar i = 0; i < 8; i++) begin : g
    deep_l2 u(.clk(clk));
  end
endmodule

module deep_top;
  logic clk;
  for (genvar i = 0; i < 8; i++) begin : g
    deep_l1 u(.clk(clk));
  end
endmodule
