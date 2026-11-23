// D3a golden: enumerations (LRM 6.19).
package enums;
  /// Traffic light colours.
  typedef enum logic [1:0] {
    RED,         // Stop.
    AMBER = 2,   // Get ready.
    /// Go.
    GREEN
  } color_t;

  /// Literals generated from a range.
  typedef enum {S[3], T[5:6]} state_t;

  /// An enumeration declared on the variable itself.
  enum bit {OFF, ON} power;

  class widget;
    typedef enum {IDLE, BUSY} mode_t;
    rand enum {SLOW, FAST} speed;
  endclass
endpackage

module enum_holder;
  enum {A, B = 5} st;
endmodule
