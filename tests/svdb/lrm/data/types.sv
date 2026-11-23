// D3a golden: the forms of a declared type.
interface bus_if;
  logic req;
endinterface

package types;
  typedef bit [31:0] word_t;
  typedef word_t addr_t;

  class item;
  endclass

  /// Parameterized: the parameters are documented, and so are members whose type is one.
  class holder #(type T = int, int N = 4);
    T        slots [N];
    T        q [$];
    int      by_name [string];
    T        dyn [];
  endclass

  class kinds;
    string          s;
    chandle         h;
    event           e;
    item            it;
    holder #(item)  hi;
    virtual bus_if  vif;
    addr_t          a;
    real            r;
    bit [7:0] [3:0] packed2;
    /// A method with every argument form.
    function automatic word_t pack(input addr_t a, output int n, ref item i, input int unsigned k = 3);
      return 0;
    endfunction
    task run(string name);
    endtask
  endclass
endpackage
