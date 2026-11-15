// Typedef names stay as written in signatures.
package types_pkg;

  // A pair.
  typedef int pair_t[2];

  // Settings.
  typedef struct { int depth; bit fast; } cfg_t;

  // Uses the typedefs.
  virtual class user;
    // Its params.
    typedef struct { bit unused; } params_t;
    // Returns params.
    extern static function params_t mk(pair_t pairs[], cfg_t c);
    // Some pairs.
    pair_t pp[3];
  endclass

endpackage
