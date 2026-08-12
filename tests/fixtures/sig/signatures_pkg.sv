// signatures_pkg: declarations chosen to exercise signature rendering.
//
// Kept apart from sample_pkg because several tests assert that package's exact
// contents.  Everything here is about *how a signature is displayed*: argument
// directions, defaults (including one containing a comma), unpacked
// dimensions, packed types, and user-defined types that should cross-link.
package signatures_pkg;

  // A user-defined type, so signatures mentioning it have something to link to.
  class sig_payload;

    // The payload bytes.
    byte data[];

  endclass

  // Operations whose signatures cover the interesting rendering cases.
  class sig_ops;

    // Takes no arguments at all.
    function void reset();
    endfunction

    // A default value containing a comma at brace depth 1.
    //
    // The renderer must not split this into two arguments.
    function void seed(int vals[$] = '{1, 2}, int repeat_count = 3);
    endfunction

    // Directions and a packed type.
    function void transfer(input bit [7:0] addr, output bit [7:0] data);
    endfunction

    // A user type as both argument and return type; both should link.
    function sig_payload wrap(sig_payload src);
      return src;
    endfunction

    // A string default, which also contains a comma.
    function void label(string text = "a, b");
    endfunction

    // A queue argument: the dimensions bind to the name, not the type.
    task push(ref int q[$], int value);
    endtask

  endclass

endpackage
