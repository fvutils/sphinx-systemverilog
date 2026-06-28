// Package: nd_pkg
//
// A small NaturalDocs-style package used to exercise the naturaldocs dialect,
// detached-block association, member groups, and inheritance diagrams.
package nd_pkg;

  // CLASS: nd_base
  //
  // The root of the nd_pkg hierarchy.
  virtual class nd_base;

    // Group: Identification

    // Function: get_name
    //
    // Returns the object name. See <set_name>.

    // @annotation auto 1.2.3
    extern virtual function string get_name();

    // Function: set_name
    //
    // Sets the object ~name~.
    extern virtual function void set_name(string name);

  endclass

  // CLASS: nd_mid
  //
  // An intermediate class.
  class nd_mid extends nd_base;
  endclass

  // CLASS: nd_leaf
  //
  // A concrete leaf class.
  class nd_leaf extends nd_mid;

    // Group: Operation

    // Function: run
    //
    // Runs the leaf for ~cycles~ cycles.
    extern function void run(int cycles);

  endclass

endpackage
