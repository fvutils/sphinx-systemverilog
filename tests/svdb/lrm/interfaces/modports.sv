// D3b golden: modports.
interface bus_if #(parameter int W = 8) (input logic clk);
  logic         req;
  logic         gnt;
  logic [W-1:0] data;

  clocking cb @(posedge clk);
    input gnt;
    output req;
  endclocking

  /// Drives a request.
  task automatic send(input logic [W-1:0] d);
    data = d;
  endtask

  function automatic logic busy();
    return req;
  endfunction

  /// The requester's view.
  modport master (output req, output data, input gnt, import send, clocking cb);

  /// The responder's view: a port renamed by an expression, a prototype.
  modport slave (input req, input .payload(data), output gnt,
                 import function logic busy());

  modport mon (input req, gnt, data);   // A monitor: one direction for three ports.

  modport tb (export task recv(input logic [W-1:0] d)), view (input req);
endinterface

/// Implements the task the ``tb`` modport exports.
module responder (bus_if.tb b);
  task b.recv(input logic [7:0] d);
  endtask
endmodule

module top;
  logic clk;
  bus_if i (.clk);
  responder r (.b(i));
endmodule
