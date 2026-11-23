// D3d golden: covergroup extras this pass adds -- ``sample_args``, a
// coverpoint's ``expr``/``iff``/``type``, ``cross`` (new) and ``bins``
// (``bins``/``illegal_bins``/``ignore_bins``, an array bin, a default bin).
// ``extends`` (1800-2023 covergroup inheritance) is not exercised: this
// pyslang build's parser does not accept the construct.
package pkg;
  class txn;
    rand bit [2:0] a, b;
    covergroup cg with function sample(int extra);
      cp_a: coverpoint a iff (b > 0) {
        bins lo = {0, 1};
        bins hi[] = {[2:3]};
        illegal_bins bad = {4, 5};
        ignore_bins skip = {6};
        bins others = default;
      }
      cp_b: coverpoint b;
      cx_ab: cross cp_a, cp_b;
    endgroup
    function new();
      cg = new();
    endfunction
  endclass
endpackage
