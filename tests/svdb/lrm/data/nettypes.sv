// D3a golden: user-defined nettypes (LRM 6.6.7).
package nettypes;
  typedef struct { real v; real i; } vi_t;

  /// Resolves several drivers by summing their currents.
  function automatic vi_t sum(input vi_t d []);
    sum = '{0.0, 0.0};
    foreach (d[k]) sum.i += d[k].i;
  endfunction

  /// A nettype without a resolution function.
  nettype vi_t plain_net;
  /// A nettype resolved by sum.
  nettype vi_t vi_net with sum;
endpackage

module nettype_user;
  import nettypes::*;
  vi_net node;
  plain_net taps [2];
  nettype logic [3:0] local_net;
endmodule
