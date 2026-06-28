# Documenting modules & interfaces

`autosvmodule` (and the underlying `sv:module` / `sv:interface` directives)
document hardware modules and interfaces, including their **parameters** and
**ports** — concepts with no Python analog.

```rst
.. autosvmodule:: counter
   :members:
```

## Parameters and ports

With `:members:`, parameters and ports are listed in declaration order. Each
shows its full declaration; ports show their direction:

- **Parameters** — `parameter`/`localparam`, with type and default value.
- **Ports** — `input` / `output` / `inout`, with type and packed dimensions.

Documentation comes from comments on each parameter/port, either leading or as a
trailing inline comment:

```systemverilog
module counter #(
  parameter int WIDTH = 8        // counter width in bits
)(
  input  logic             clk,  // clock
  // active-high synchronous reset
  input  logic             rst,
  output logic [WIDTH-1:0] count
);
```

Ports and parameters are considered the module's public interface, so they are
shown even when undocumented (unlike undocumented class members, which are
hidden unless `:undoc-members:` is given).
