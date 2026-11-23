// A design that instantiates VIP whose sources are not part of the build.
module tb;
  wire clk, rst_n;
  wire [31:0] awaddr;

  axi_vip_mst u_mst (.aclk(clk), .aresetn(rst_n), .awaddr(awaddr));
  axi_vip_slv u_slv (.aclk(clk), .aresetn(rst_n), .awaddr(awaddr));
endmodule
