// The smallest unit of the design; instantiated many times.
module leaf #(
    parameter int W = 8
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) dout <= '0;
    else        dout <= din;
  end
endmodule
