// D3a golden: structures and unions (LRM 7.2, 7.3).
package structs;
  /// A packed header.
  typedef struct packed signed {
    logic [3:0] kind;   // Packet kind.
    /// Payload length.
    logic [11:0] len;
  } hdr_t;

  /// Unpacked, with defaults and a member that declares two fields.
  typedef struct {
    int x = 1, y = 2;
    struct { bit a; bit b; } flags;
  } point_t;

  typedef union tagged {
    void invalid;
    int  valid;
  } maybe_t;

  typedef union packed {
    logic [7:0] b;
    logic [3:0] [1:0] n;
  } byte_u;

  /// A structure declared on the variable.
  struct { int lo; int hi; } range;

  class box;
    typedef struct { int w; int h; } dim_t;
  endclass
endpackage
