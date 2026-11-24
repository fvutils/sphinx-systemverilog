// A four-block pipeline with feedback through ctrl, an interface port, an
// assign-driven net and every connection style: named, implicit (.clk),
// wildcard (.*) and unconnected.
module pipe_top (
    input  logic        clk, rst_n,
    input  logic [31:0] boot_pc,
    pipe_cfg_if.dev          cfg,
    output logic [31:0] result
);
  logic [31:0] pc_in, instr, pc, imm, branch_pc;
  logic        instr_valid, op_valid, branch_taken, stall, flush;
  logic [4:0]  rs1, rs2;

  assign pc_in = branch_taken ? branch_pc : boot_pc;

  fetch u_fetch (
      .clk, .rst_n,
      .pc_in(pc_in), .stall(stall),
      .instr(instr), .instr_valid(instr_valid), .pc(pc)
  );

  decode u_decode (
      .clk(clk), .rst_n(rst_n),
      .instr(instr), .instr_valid(instr_valid), .pc(pc), .flush(flush),
      .rs1(rs1), .rs2(rs2), .imm(imm), .op_valid(op_valid)
  );

  execute u_exec (
      .clk(clk), .rst_n(rst_n),
      .rs1(rs1), .rs2(rs2), .imm(imm), .op_valid(op_valid),
      .cfg(cfg),
      .result(result), .branch_taken(branch_taken), .branch_pc(branch_pc),
      .dbg()
  );

  ctrl u_ctrl (.*);

  trace u_trace (.clk(clk), .result(result), .op_valid(op_valid));
endmodule
