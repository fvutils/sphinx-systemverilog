// D3e golden: LRM 26.3/26.6 package imports and exports -- wildcard and
// explicit, in a package and a module body and header.  The $unit import is
// not recorded: there is no compilation-unit object to scope it to yet.

package base_pkg;
  typedef int word_t;
  int counter;
endpackage

package mid_pkg;
  import base_pkg::*;
  import base_pkg::word_t;
  export base_pkg::word_t;
  export *::*;
  word_t w;
endpackage

import base_pkg::counter;

module imp_top import mid_pkg::*; (input logic clk);
  import base_pkg::word_t;
  word_t v;
endmodule
