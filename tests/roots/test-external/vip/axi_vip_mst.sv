// A stub of a VIP master: ports only, as a vendor header would give them.
module axi_vip_mst #(parameter int W = 32) (
  input  wire         aclk,
  input  wire         aresetn,
  output wire [W-1:0] awaddr
);
endmodule
