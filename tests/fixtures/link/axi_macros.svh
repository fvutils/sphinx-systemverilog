// Macros the VIP's users include.
`ifndef AXI_MACROS_SVH
`define AXI_MACROS_SVH
`define AXI_ADDR_W 32
`define AXI_CHECK(cond, msg) if (!(cond)) $error(msg);
`endif
