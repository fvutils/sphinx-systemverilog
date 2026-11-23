// D3c golden: LRM 27.6 generate-block naming. Every construct in a scope is
// numbered from 1, named or not; an unnamed one is called genblk<n>. Here
// the first construct is named, so the second (unnamed) if-generate is
// genblk2, and its two unlabeled, never-taken branches still need distinct
// names as siblings even though only one is ever elaborated.
module leaf ();
endmodule

module top #(parameter int SEL = 0);
  generate
    for (genvar i = 0; i < 2; i = i + 1) begin : g_lp
      leaf u_lp ();
    end

    if (SEL == 0) begin
      leaf u_a ();
    end else if (SEL == 1) begin
      leaf u_b ();
    end else begin
      leaf u_c ();
    end
  endgenerate
endmodule
