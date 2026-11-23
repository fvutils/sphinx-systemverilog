// D3c golden: LRM 23.11 bind. A bound instance is parented to the target
// *definition*, not the scope that writes the bind, and ``bind.from`` names
// that writing scope. The instance-list form restricts the bind to one named
// instance by its hierarchical path.
module mon (input logic a);
endmodule

module leaf (input logic a);
endmodule

module mid ();
  logic a;
  leaf u_leaf (a);
  bind leaf mon u_all (a);
endmodule

module top ();
  mid u_mid ();
  bind leaf : top.u_mid.u_leaf mon u_one (a);
endmodule
