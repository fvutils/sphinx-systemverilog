// A configuration bus, connected through modports.
interface pipe_cfg_if;
  logic       wr;
  logic [7:0] addr;
  logic [31:0] wdata;
  modport host (output wr, addr, wdata);
  modport dev  (input  wr, addr, wdata);
endinterface
