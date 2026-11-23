// D3e golden: LRM 5.12 attributes -- (* name [= value] *) on a declaration
// becomes the object's attrs list, in source order: {name} for a bare flag,
// {name, value: {text}} when a value is given (text as written).  Covers
// module, ANSI port, variable, net, instance, subroutine,
// formal argument, package, typedef, class, class property, modport.

(* top_mod, ver = "1.0" *)
module attr_top #(parameter int P = 1)
    ((* io = 2 *) input logic a, output logic y);
  (* keep *) logic w;
  (* fsm_state = 1 + 2 *) wire [1:0] s;
  (* dont_touch = 1, mark *) attr_leaf u1 (.x(a));
  (* full_case *) function automatic int f((* arg *) int z); return z; endfunction
  (* opt *) task t; endtask
  assign y = a;
endmodule

(* leaf *) module attr_leaf(input x); endmodule

(* pk *) package attr_pkg;
  (* tdef *) typedef int myint;
  (* c *) class C;
    (* prop *) int a;
  endclass
endpackage

interface attr_ifc;
  logic x;
  (* mp *) modport m(input x);
endinterface
