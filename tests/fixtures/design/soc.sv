// The design top: two differently-parameterized clusters.
module soc (
    input logic clk,
    input logic rst_n
);
  logic [7:0]  narrow_out;
  logic [31:0] wide_out;

  cluster #(.W(8), .WIDE(1'b0)) u_narrow (
      .clk(clk), .rst_n(rst_n), .din(8'h0), .dout(narrow_out)
  );

  cluster #(.W(32), .WIDE(1'b1)) u_wide (
      .clk(clk), .rst_n(rst_n), .din(32'h0), .dout(wide_out)
  );
endmodule
