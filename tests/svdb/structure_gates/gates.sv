// D3c-IMPL-3 golden: built-in gate instances (``of_kind: gate``), opt-in
// behind the ``structure.gates`` section (plan §5.2.1, §5.4 row 28). A
// scalar gate, a one-input gate, and a gate array, so the array-element
// shape (no ``.body``, unlike a module-instance array) is covered too.
module top (input a, b, output y, z, w);
  and g1 (y, a, b);
  not g2 (z, a);
  and g3 [3:0] (w, a, b);
endmodule
