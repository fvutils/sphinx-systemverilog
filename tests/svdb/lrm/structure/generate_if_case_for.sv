// D3c golden: the three generate constructs (LRM 27), each named, with
// their genvar and loop/condition/case-item expressions.
module leaf (input logic a, output logic b);
endmodule

/// A for-generate, an if-generate (with an else-if and an else), and a
/// case-generate, each instantiating ``leaf``.
module top #(parameter int SEL = 1);
  wire a, b;
  genvar i;

  generate
    for (i = 0; i < 2; i = i + 1) begin : g_lp
      leaf u_lp (.a(a), .b(b));
    end

    if (SEL == 0) begin : g_zero
      leaf u_zero (.a(a), .b(b));
    end else if (SEL == 1) begin : g_one
      leaf u_one (.a(a), .b(b));
    end else begin : g_other
      leaf u_other (.a(a), .b(b));
    end

    case (SEL)
      0: begin : g_case0
        leaf u_case0 (.a(a), .b(b));
      end
      1, 2: begin : g_case12
        leaf u_case12 (.a(a), .b(b));
      end
      default: begin : g_default
        leaf u_default (.a(a), .b(b));
      end
    endcase
  endgenerate
endmodule
