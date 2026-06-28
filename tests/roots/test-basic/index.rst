SystemVerilog Test Document
===========================

Manual directive
----------------

.. sv:class:: manual_class
   :module: manual_pkg

   A manually written class.

   .. sv:function:: function bit do_thing(int n)

      Do a thing.

Autodoc
-------

.. autosvclass:: sample_pkg::sample_base
   :members:

.. autosvclass:: sample_pkg::sample_txn
   :members:

Cross references
----------------

Qualified ref to :sv:class:`sample_pkg::sample_base`, bare ref to
:sv:class:`sample_txn`, and a method ref :sv:func:`parity`.
