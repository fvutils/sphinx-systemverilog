// A package exercising coverage and constraint constructs.
package cov_pkg;

  class cov_item;

    rand bit [3:0] mode;
    rand int       value;

    // Coverage of the mode field.
    covergroup mode_cg;
      cp_mode: coverpoint mode;
    endgroup

    // value must be non-negative
    constraint c_value { value >= 0; }

  endclass

endpackage
