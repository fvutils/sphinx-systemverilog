// D3e golden: LRM 9.2/9.3 processes and named blocks. A process is recorded
// when its body is a named block (it takes the label); unlabelled processes
// are anonymous and not emitted. Named begin/fork blocks nest under their
// process, subroutine or block; a labelled assertion is not a block.

module m (input logic clk, input logic rst_n, input logic a);
  logic q, r;

  /// The state register.
  always_ff @(posedge clk or negedge rst_n) begin : seq_l
    q <= a;
    /// The second stage.
    begin : inner
      r <= q;
    end
  end

  always_comb begin : comb_l
    r = a;
  end

  always_latch begin : latch_l
    if (a) q = a;
  end

  always @(a) begin : sens_l
    begin
      begin : under_unnamed
      end
    end
  end

  initial begin : init_l
    fork : f_any
      #1 r = 0;
    join_any
    fork : f_none
    join_none
    fork : f_all
    join
  end

  final begin : fin_l
  end

  // Anonymous: not recorded.
  initial r = 0;
  always @(a) r = a;
  final begin end

  chk: assert property (@(posedge clk) a);

  task t;
    begin : tb
    end
  endtask

  if (1) begin : g
    always @(posedge clk) begin : g_l
    end
  end
endmodule

package p;
  function automatic int f();
    begin : fb
      return 0;
    end
  endfunction
endpackage
