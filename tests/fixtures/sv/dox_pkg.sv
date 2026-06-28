// A package documented in the Doxygen style.
package dox_pkg;

  /**
   * @brief A Doxygen-documented transaction.
   *
   * @details Models a transfer with an address and data, documented using
   * Doxygen commands so the doxygen dialect can be exercised.
   */
  class dox_txn;

    /// The target address.
    bit [31:0] addr;

    /**
     * @brief Compute the parity of the payload.
     *
     * @param[in] mask  bits to include in the parity
     * @param width the bit width
     * @return the computed parity bit
     * @note Not synthesizable.
     * @see addr
     */
    function bit parity(bit [31:0] mask, int width);
      return ^addr;
    endfunction

  endclass

  /// A parameterized FIFO.
  class fifo #(type T = int, int DEPTH = 8);
    /// the storage
    T store[$];
    /// push an item
    extern function void push(T item);
  endclass

endpackage
