# The `native` comment style

The `native` dialect is the recommended convention for new SystemVerilog code.
It is deliberately low-ceremony: the comment body *is* reStructuredText, so it
flows straight into Sphinx with no translation.

## Rules

- The doc comment is the contiguous `//` or `/* */` block immediately above a
  declaration.
- The **first paragraph** is the summary.
- Everything after the first blank line is the body (full reST/MyST allowed).
- reST **field lists** describe parameters and return values.
- A **trailing inline comment** documents the declaration on its own line.

## Example

```systemverilog
// Compute the parity of the data payload.
//
// A longer explanation can span multiple lines and use any
// reStructuredText: lists, ``literals``, references, etc.
//
// :param mask: bits to include in the parity calculation
// :returns: the computed parity bit
function bit parity(bit [31:0] mask);
  return ^(data & mask);
endfunction
```

A trailing comment attaches to the declaration it follows:

```systemverilog
rand bit [31:0] addr;   // The target address.
```

## Cross-references inside comments

Write a normal domain role and it resolves like anywhere else:

```systemverilog
// Drive this transaction; see :sv:class:`my_pkg::driver`.
```
