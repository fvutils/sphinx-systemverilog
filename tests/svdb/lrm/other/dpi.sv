// D3e golden: LRM 35 DPI -- imports (pure, context, an explicit C name,
// a task) and exports (default and explicit C name) in a package and a module.

package dpi_pkg;
  import "DPI-C" pure function int c_add(input int a, input int b);
  import "DPI-C" context task c_wait(input int n);
  import "DPI-C" c_puts = function void sv_puts(input string s);
  export "DPI-C" function sv_cb;
  export "DPI-C" c_tick = task sv_tick;
  function void sv_cb(int x); endfunction
  task sv_tick(); endtask
  function int plain(); return 0; endfunction
endpackage

module dpi_top;
  import "DPI-C" function int c_status();
  export "DPI-C" function m_cb;
  function void m_cb(); endfunction
endmodule
