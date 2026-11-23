// D3e golden: LRM 16.3/16.4 immediate and deferred assertions. They are
// recorded under the nearest labelled process, named block or subroutine;
// a labelled one takes its label, others are $assertion#N per parent.
// Assertions in an unlabelled process are not emitted (its parent is not).

module m (input logic clk, input logic a, input logic b);
  always_ff @(posedge clk) begin : seq_l
    /// a must hold on every edge.
    chk_a: assert (a) else $error("a low");
    assert #0 (a || b);
    if (a) begin
      assume final (b);
    end
    begin : inner
      cover (a && b) $display("both");
    end
  end

  always_comb begin
    assert (a);
  end

  task automatic t;
    t_chk: assert (b);
    fork : f
      assert final (a);
    join
  endtask

  function automatic bit f(bit x);
    assert #0 (x);
    return x;
  endfunction
endmodule

package p;
  function automatic void pf(int x);
    pf_chk: assert (x > 0);
  endfunction

  class c;
    task run;
      cover (1);
    endtask
  endclass
endpackage

module locals_m (input logic a);
  task automatic lt(input int n);
    int cnt;
    begin : body
      int seen;
      assert (n > cnt && seen >= 0 && a);
    end
  endtask
endmodule
