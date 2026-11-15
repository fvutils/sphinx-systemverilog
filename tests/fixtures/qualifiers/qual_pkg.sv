// Classes and methods whose qualifiers the reference must show.
package qual_pkg;

  // An interface class.
  interface class q_if;
    // Implemented by every q_if.
    pure virtual function int f();
  endclass

  // A plain abstract class.
  virtual class q_base;
    // A static factory, defined out of block.
    extern static function q_base make();
    // A protected static helper.
    protected static function int helper(); return 0; endfunction
    // A local virtual hook.
    local virtual function void hook(); endfunction
    // Must be overridden.
    pure virtual function void must();
  endclass

  function q_base q_base::make(); return null; endfunction

  // A parameterized interface class.
  interface class q_gif #(type T = int);
    // Creates a T.
    pure virtual function T create();
  endclass

  // A parameterized abstract class.
  virtual class q_gen #(type T = int);
    // This class.
    typedef q_gen #(T) this_t;
    // A static factory.
    extern static function this_t get();
    // A protected virtual hook.
    protected virtual function void hook(); endfunction
  endclass

endpackage
