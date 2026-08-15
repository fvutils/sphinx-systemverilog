// A simple bus interface with modports.
interface bus_if #(parameter int W = 8) (input logic clk);
  logic [W-1:0] data;
  logic         valid;

  modport master(output data, output valid, input clk);
  modport slave(input data, input valid, input clk);
endinterface
