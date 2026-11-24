// Pipeline stages for the RTL block-diagram tests.

module fetch (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] pc_in,
    input  logic        stall,
    output logic [31:0] instr,
    output logic        instr_valid,
    output logic [31:0] pc
);
endmodule

module decode (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] instr,
    input  logic        instr_valid,
    input  logic [31:0] pc,
    input  logic        flush,
    output logic [4:0]  rs1,
    output logic [4:0]  rs2,
    output logic [31:0] imm,
    output logic        op_valid
);
endmodule

module execute (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [4:0]  rs1,
    input  logic [4:0]  rs2,
    input  logic [31:0] imm,
    input  logic        op_valid,
    pipe_cfg_if.dev          cfg,
    output logic [31:0] result,
    output logic        branch_taken,
    output logic [31:0] branch_pc,
    output logic        dbg
);
endmodule

// Directions carried over (``input logic clk, rst_n, branch_taken``).
module ctrl (
    input  logic clk, rst_n, branch_taken,
    output logic stall,
    output logic flush
);
endmodule

// Drives nothing: an observer.
module trace (
    input logic        clk,
    input logic [31:0] result,
    input logic        op_valid
);
endmodule
