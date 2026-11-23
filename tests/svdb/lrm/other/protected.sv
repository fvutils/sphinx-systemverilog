// Encrypted envelopes (LRM 34): recorded as line ranges on the file record
// (`file.protected`); the innermost declaration around one gets
// `flags.protected`. The data block is never decrypted.

// A whole module body encrypted: only the file range records it.
`pragma protect begin_protected
`pragma protect encrypt_agent = "golden"
`pragma protect data_method = "aes128-cbc"
`pragma protect data_block
QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=
`pragma protect end_protected

// Part of a module encrypted: the module is flagged; `a` and `b` are not.
module partly;
  logic a;
`pragma protect begin_protected
`pragma protect data_method = "aes128-cbc"
`pragma protect data_block
MDEyMzQ1Njc4OWFiY2RlZg==
`pragma protect end_protected
  logic b;
endmodule

// In a class method: the function is flagged, the class is not.
package pkg;
class keeper;
  function void hidden();
`pragma protect begin_protected
`pragma protect data_method = "aes128-cbc"
`pragma protect data_block
ZmVkY2JhOTg3NjU0MzIxMA==
`pragma protect end_protected
  endfunction
  function void plain();
  endfunction
endclass
endpackage

// An unencrypted `begin`/`end` input envelope is not an encrypted region.
module open_envelope;
`pragma protect begin
  logic c;
`pragma protect end
endmodule
