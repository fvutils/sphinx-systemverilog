// A minimal stand-in for UVM, used by the fast unit tests (U0-TEST-1).
//
// Nothing here is meant to *run*.  It reproduces only the **static** structure
// the elaborator reads:
//
//   * the `uvm_component_registry #(T, Tname)` factory typedef, which is how a
//     `type_id::create` call site names the type it creates;
//   * the component base-class chain, which is what tier classification walks;
//   * the `uvm_config_db` set/get signatures;
//   * TLM port/export/imp types, which `connect_phase` wires together.
//
// Method bodies are deliberately empty --- the analyser reads call sites, never
// behaviour.  Real UVM costs ~0.10s per compile and pulls in an ivpm-fetched
// dependency; this costs ~0.000s and is always present, so it carries the bulk
// of the coverage.  Real UVM remains the corpus gate (U1-TEST-7), which is
// where its cost is worth paying.

`include "mini_uvm.svh"

package mini_uvm_pkg;

  virtual class uvm_void;
  endclass

  // Real registries extend `uvm_object_wrapper`, and that matters here rather
  // than being decoration: `T::get_type()` returns a wrapper, and a factory
  // override is written by passing two of them.  A stub whose registries
  // extended nothing could not express an override call at all.
  virtual class uvm_object_wrapper extends uvm_void;
    virtual function string get_type_name();
      return "<unknown>";
    endfunction
  endclass

  class uvm_phase extends uvm_void;
    string m_name;
    function new(string name = "phase");
      m_name = name;
    endfunction
  endclass

  class uvm_object extends uvm_void;
    string m_name;
    function new(string name = "");
      m_name = name;
    endfunction
    virtual function string get_name();
      return m_name;
    endfunction
    virtual function string get_type_name();
      return "uvm_object";
    endfunction
  endclass

  class uvm_component extends uvm_object;
    uvm_component m_parent;
    function new(string name, uvm_component parent = null);
      super.new(name);
      m_parent = parent;
    endfunction
    virtual function void build_phase(uvm_phase phase);
    endfunction
    virtual function void connect_phase(uvm_phase phase);
    endfunction
    virtual task run_phase(uvm_phase phase);
    endtask
    virtual function string get_full_name();
      return m_name;
    endfunction
    // The four `uvm_component` convenience wrappers, with real UVM's argument
    // order --- which differs between the type and inst forms and is the whole
    // reason the extraction reads positions per method rather than uniformly.
    static function void set_type_override_by_type(uvm_object_wrapper original_type,
                                                   uvm_object_wrapper override_type,
                                                   bit replace = 1);
    endfunction
    static function void set_type_override(string original_type_name,
                                           string override_type_name,
                                           bit replace = 1);
    endfunction
    function void set_inst_override_by_type(string relative_inst_path,
                                            uvm_object_wrapper original_type,
                                            uvm_object_wrapper override_type);
    endfunction
    function void set_inst_override(string relative_inst_path,
                                    string original_type_name,
                                    string override_type_name);
    endfunction
    // Real `uvm_component::set_config_object` calls `config_db::set` from
    // inside the library.  Reproduced here so the rule that keeps library
    // bookkeeping out of a user's config table has a target to be tested
    // against --- against real UVM it is invisible for an unrelated reason
    // (slang does not elaborate those method bodies), so the stub is the only
    // place the rule itself can be exercised.
    virtual function void set_config_object(string inst_name,
                                            string field_name,
                                            uvm_object value);
      uvm_config_db #(uvm_object)::set(this, inst_name, field_name, value);
    endfunction
  endclass

  // -- the factory ----------------------------------------------------------
  //
  // `Tname` is the whole point.  The created type is recovered from this
  // parameter, *not* from the return type of `create`, which reports the
  // generic `uvm_component_registry::T` and so names nothing useful.

  class uvm_component_registry #(type T = uvm_object, string Tname = "<unknown>")
      extends uvm_object_wrapper;
    static function T create(string name = "", uvm_component parent = null);
      T obj = null;
      return obj;
    endfunction
    static function string get_type_name();
      return Tname;
    endfunction
    // The registry form of an override: `my_drv::type_id::set_type_override(...)`.
    // The *original* type is the specialization's own `Tname`, which is the
    // same trick `create` already relies on.
    static function void set_type_override(uvm_object_wrapper override_type,
                                           bit replace = 1);
    endfunction
    static function void set_inst_override(uvm_object_wrapper override_type,
                                           string inst_path);
    endfunction
  endclass

  class uvm_object_registry #(type T = uvm_object, string Tname = "<unknown>")
      extends uvm_object_wrapper;
    static function T create(string name = "");
      T obj = null;
      return obj;
    endfunction
    static function string get_type_name();
      return Tname;
    endfunction
    // The registry form of an override: `my_drv::type_id::set_type_override(...)`.
    // The *original* type is the specialization's own `Tname`, which is the
    // same trick `create` already relies on.
    static function void set_type_override(uvm_object_wrapper override_type,
                                           bit replace = 1);
    endfunction
    static function void set_inst_override(uvm_object_wrapper override_type,
                                           string inst_path);
    endfunction
  endclass

  // -- TLM ------------------------------------------------------------------
  //
  // A TLM port is **not** a `uvm_component`.  Real UVM declares
  // `uvm_port_base #(IF) extends IF`, where `IF` is a `uvm_tlm_if_base` that
  // extends `uvm_void`; the port holds an internal component proxy rather than
  // being one.  The stub follows that, because getting it wrong here would put
  // ports into the component tree of every testbench under test and hide the
  // fact that they never appear there against real UVM.
  //
  // `connect` is typed against the common base so any port may be written as
  // connected to any export; the analyser reads the call site, and a stub that
  // enforced real TLM typing would only make fixtures harder to write.

  class uvm_port_base extends uvm_void;
    string       m_name;
    uvm_component m_comp;    // the proxy real UVM keeps
    function new(string name, uvm_component parent = null);
      m_name = name;
      m_comp = parent;
    endfunction
    virtual function void connect(uvm_port_base provider);
    endfunction
  endclass

  class uvm_analysis_port #(type T = uvm_object) extends uvm_port_base;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    function void write(T t);
    endfunction
  endclass

  class uvm_analysis_export #(type T = uvm_object) extends uvm_port_base;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class uvm_analysis_imp #(type T = uvm_object, type IMP = uvm_component)
      extends uvm_port_base;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // A TLM FIFO, unlike a port, really *is* a component: real UVM declares
  // `uvm_tlm_fifo extends uvm_tlm_fifo_base extends uvm_component`.  Present so
  // the always-on library stop has a genuine target inside a component tree.
  class uvm_tlm_analysis_fifo #(type T = uvm_object) extends uvm_component;
    uvm_analysis_export #(T) analysis_export;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class uvm_seq_item_pull_port #(type REQ = uvm_object) extends uvm_port_base;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class uvm_seq_item_pull_export #(type REQ = uvm_object) extends uvm_port_base;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // -- the taxonomy tier classification walks -------------------------------

  // Real `uvm_driver` hands every driver three TLM ports it did not declare
  // --- `seq_item_port` is the one anybody connects, and the rest is plumbing.
  // The stub originally declared none, which made every driver box in every
  // stub-based test look right for a reason that did not hold against the real
  // library; the corpus gate is what noticed. Reproduced here so the rule that
  // hides *unconnected* inherited ports is exercised by the fast tests too.
  virtual class uvm_driver extends uvm_component;
    uvm_seq_item_pull_port #(uvm_object) seq_item_port;
    uvm_analysis_port      #(uvm_object) rsp_port;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  virtual class uvm_monitor extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class uvm_sequencer_base extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  class uvm_sequencer #(type REQ = uvm_object) extends uvm_sequencer_base;
    // The other end of the driver connection, inherited exactly as it is in
    // real UVM: connected, and so shown despite being a library port.
    uvm_seq_item_pull_export #(REQ) seq_item_export;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  virtual class uvm_agent extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  virtual class uvm_scoreboard extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  virtual class uvm_subscriber #(type T = uvm_object) extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
    pure virtual function void write(T t);
  endclass

  virtual class uvm_env extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  virtual class uvm_test extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // A register-model base.  Present so the default `sv_uvm_blackbox_bases`
  // has something real to match: a RAL package generated from RDL is the
  // archetypal thing to be absent when docs are built.
  class uvm_reg_block extends uvm_component;
    function new(string name, uvm_component parent = null);
      super.new(name, parent);
    endfunction
  endclass

  // -- sequences ------------------------------------------------------------

  class uvm_sequence_item extends uvm_object;
    // Real `uvm_sequence_item` carries this, and it is what `` `uvm_do ``
    // expands into as the default sequencer argument.  A sequence body that
    // never names a sequencer explicitly still mentions this one.
    uvm_sequencer_base m_sequencer;
    function new(string name = "");
      super.new(name);
    endfunction
  endclass

  class uvm_sequence_base extends uvm_sequence_item;
    function new(string name = "");
      super.new(name);
    endfunction
    virtual task body();
    endtask
    virtual task start(uvm_sequencer_base sequencer);
    endtask
    // On the base class rather than on `uvm_sequence #(REQ)`, which is where
    // real UVM declares them.
    virtual task start_item(uvm_sequence_item item, int set_priority = -1,
                            uvm_sequencer_base sequencer = null);
    endtask
    virtual task finish_item(uvm_sequence_item item, int set_priority = -1);
    endtask
  endclass

  class uvm_sequence #(type REQ = uvm_sequence_item) extends uvm_sequence_base;
    function new(string name = "");
      super.new(name);
    endfunction
  endclass

  // -- config_db ------------------------------------------------------------

  class uvm_config_db #(type T = int);
    static function void set(uvm_component cntxt, string inst_name,
                             string field_name, T value);
    endfunction
    // `inout`, not `ref`, because that is what real UVM declares --- and the
    // argument direction changes how slang shapes the call expression, which
    // is exactly the kind of divergence the corpus gate exists to catch.
    static function bit get(uvm_component cntxt, string inst_name,
                            string field_name, inout T value);
      return 0;
    endfunction
  endclass

  // -- the factory singleton ------------------------------------------------
  //
  // `factory.set_type_override_by_type(...)` is as common as the component
  // convenience wrapper, and it is a *different* declaring class, so the
  // discriminator has to know both.

  class uvm_factory extends uvm_void;
    static function uvm_factory get();
      return null;
    endfunction
    function void set_type_override_by_type(uvm_object_wrapper original_type,
                                            uvm_object_wrapper override_type,
                                            bit replace = 1);
    endfunction
    function void set_type_override_by_name(string original_type_name,
                                            string override_type_name,
                                            bit replace = 1);
    endfunction
    function void set_inst_override_by_type(uvm_object_wrapper original_type,
                                            uvm_object_wrapper override_type,
                                            string full_inst_path);
    endfunction
    function void set_inst_override_by_name(string original_type_name,
                                            string override_type_name,
                                            string full_inst_path);
    endfunction
  endclass

  // -- entry point ----------------------------------------------------------
  //
  // Root auto-detection (U1-IMPL-10) looks for exactly this call in a top
  // module's `initial` block.

  function automatic void run_test(string test_name = "");
  endfunction

endpackage : mini_uvm_pkg
