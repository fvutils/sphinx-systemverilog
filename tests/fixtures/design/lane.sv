// One data lane: a generate loop plus an instance array.
module lane #(
    parameter int W     = 8,
    parameter int LANES = 2
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  logic [W-1:0] stage [LANES];

  generate
    for (genvar g = 0; g < LANES; g++) begin : g_lp
      leaf #(.W(W)) u_g (
          .clk  (clk),
          .rst_n(rst_n),
          .din  (din),
          .dout (stage[g])
      );
    end
  endgenerate

  // An instance array: four leaves in one declaration.
  leaf #(.W(W)) u_l [3:0] (
      .clk  (clk),
      .rst_n(rst_n),
      .din  (din),
      .dout (dout)
  );
endmodule
