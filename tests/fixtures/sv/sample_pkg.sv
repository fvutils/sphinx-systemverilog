// sample_pkg: a small package exercising the Phase-1 feature set.
//
// It contains a base class, a derived class with documented and undocumented
// members, a function with parameters, a task, and a typedef.
package sample_pkg;

  // Base class for all sample objects.
  virtual class sample_base;

    // Human-readable name of this object.
    string name;

    // Return the object's name.
    //
    // :returns: the stored name
    virtual function string get_name();
      return name;
    endfunction

  endclass

  // A bus transaction.
  //
  // Models a single read or write transfer on the sample bus, carrying an
  // address and a data payload.
  class sample_txn extends sample_base;

    // The target address.
    rand bit [31:0] addr;

    // The data payload.
    rand bit [31:0] data;

    // Internal running count of transactions.
    local int m_count;   // not part of the public API

    // Compute the parity of the data payload.
    //
    // :param mask: bits to include in the parity calculation
    // :returns: the computed parity bit
    function bit parity(bit [31:0] mask);
      return ^(data & mask);
    endfunction

    // Drive the transaction onto the bus.
    //
    // :param cycles: number of clock cycles to hold the data
    virtual task drive(int cycles);
    endtask

  endclass

endpackage
