# Class hierarchy

Every diagram on this page is drawn from `extends` relationships the extension
resolved while parsing UVM — nothing here is hand-drawn. Arrows point from
derived class to base class, and the highlighted node is the root the diagram
was requested for.

`uvm_object` and `uvm_port_base` are deliberately absent: with 168 and 94
descendants respectively they produce a graph no one can read. The useful view
of a library this size is per-family, which is what follows.

## Components

`uvm_component` is the testbench structure: everything with a place in the
hierarchy and a phasing lifecycle.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_component
   :optional:
```

## Transactions and sequences

Data objects derive from `uvm_transaction`; sequences and the sequencers that
run them sit on top of `uvm_sequence_item`.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_transaction
   :optional:

.. sv:inheritance-diagram:: uvm_sequencer_base
   :optional:
```

## Phasing

The phase classes are themselves a hierarchy: the schedule is built from
`uvm_phase` objects, and each concrete phase is a singleton class.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_phase
   :optional:
```

## Policies

The policy classes — printing, comparing, packing, copying, recording — share a
`uvm_policy` base, which is what lets a single `uvm_field_op` carry any of them.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_policy
   :optional:
```

## Callbacks

```{eval-rst}
.. sv:inheritance-diagram:: uvm_callback
   :optional:
```

## Resources

The configuration and resource database rests on `uvm_resource_base`, with the
typed `uvm_resource#(T)` specializations above it.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_resource_base
   :optional:
```

## Register sequences

The register layer ships a library of pre-built test sequences, all deriving
from `uvm_reg_sequence`.

```{eval-rst}
.. sv:inheritance-diagram:: uvm_reg_sequence
   :optional:
```
