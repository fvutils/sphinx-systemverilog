// A cluster whose composition depends on a parameter (if-generate).
module cluster #(
    parameter int  W        = 8,
    parameter bit  WIDE     = 1'b0
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  generate
    if (WIDE) begin : g_wide
      lane #(.W(W), .LANES(4)) u_lane (
          .clk(clk), .rst_n(rst_n), .din(din), .dout(dout)
      );
    end else begin : g_narrow
      leaf #(.W(W)) u_leaf (
          .clk(clk), .rst_n(rst_n), .din(din), .dout(dout)
      );
    end
  endgenerate
endmodule
