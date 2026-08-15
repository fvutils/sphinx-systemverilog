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

## Structural context

A module's declaration describes its interface. The three `:show-*:` options add
what only the *elaborated* design knows — what the module is built from, what
builds it, and which parameter values it is really used at:

```rst
.. autosvmodule:: lane
   :members:
   :show-instances:
   :show-used-by:
   :show-parameters-used:
```

| Option | Adds |
|---|---|
| `:show-instances:` | **Instance tree** — the module's children, with generate paths, array widths and elaborated parameters. |
| `:show-used-by:` | **Instantiated by** — every site that instantiates this module, with source links. |
| `:show-parameters-used:` | **Parameter values used** — the distinct values each parameter is elaborated at. |

See [Design structure](structure.md) for what each view shows and how to read
it, and [a worked example](../examples/design.md) rendered from real source.

Each option is off by default because each one triggers a walk of the elaborated
hierarchy — the most expensive thing this extension does. A module page without
them costs exactly what it always did. See [Elaboration cost](advanced.md) if
you want them on project-wide.
