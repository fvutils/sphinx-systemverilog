// Macro half of the mini-UVM test stand-in, mirroring `uvm_macros.svh`.
//
// This lives in its own file for the same reason UVM's does: slang compiles
// each file as its own compilation unit, so a macro defined inside
// `mini_uvm.sv` would not be visible to a testbench file.  A testbench includes
// this and imports the package, exactly as it would with real UVM.

`ifndef MINI_UVM_SVH
`define MINI_UVM_SVH

// The factory typedef is the only part that matters to static elaboration: the
// created type is recovered from the registry's `Tname` parameter.
`define mini_component_utils(T) \
  typedef mini_uvm_pkg::uvm_component_registry #(T, `"T`") type_id; \
  static function type_id get_type(); \
    return null; \
  endfunction \
  virtual function string get_type_name(); \
    return `"T`"; \
  endfunction

`define mini_object_utils(T) \
  typedef mini_uvm_pkg::uvm_object_registry #(T, `"T`") type_id; \
  static function type_id get_type(); \
    return null; \
  endfunction \
  virtual function string get_type_name(); \
    return `"T`"; \
  endfunction

// A stand-in for `` `uvm_do ``, and the only macro here whose *shape* matters
// rather than its meaning.  Real `uvm_do` expands to roughly a dozen
// statements --- create, sequencer selection, pre/post hooks, a randomize
// call wrapped in an error check, start_item, finish_item --- of which two
// carry any information a reader wants.  The point of reproducing that here is
// that a sequence diagram which draws the expansion draws a dozen boxes for
// one line of source, so the stub has to be able to produce the noise before
// the filter can be shown to remove it.
`define mini_do(SEQ_OR_ITEM) \
  begin \
    SEQ_OR_ITEM = new(); \
    SEQ_OR_ITEM.m_sequencer = m_sequencer; \
    start_item(SEQ_OR_ITEM, -1, m_sequencer); \
    if (!SEQ_OR_ITEM.randomize()) begin \
      $display("randomization failed"); \
    end \
    finish_item(SEQ_OR_ITEM, -1); \
  end

`endif // MINI_UVM_SVH
