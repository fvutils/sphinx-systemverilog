// LRM 3.12.1, 22.7, 22.8: a compilation unit's `timescale and `default_nettype.
`timescale 1ns / 1ps
`default_nettype none
module unit_a(input wire a, output wire y);
  assign y = a;
endmodule
`default_nettype wire
