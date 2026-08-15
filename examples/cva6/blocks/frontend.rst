Frontend — fetch and branch prediction
======================================

The frontend implements the first two pipeline stages: PC generation and
fetch.  Its description, ports and submodule list below are read from the
RTL; the hierarchy comes from elaborating the design.

.. sv:instance-tree:: frontend
   :depth: 2
   :optional:


Where it sits
-------------

.. sv:used-by:: frontend
   :optional:


frontend
--------

.. autosvmodule:: frontend
   :members:
   :show-parameters-used:
   :optional:


Submodules
----------

instr_realign
~~~~~~~~~~~~~

.. autosvmodule:: instr_realign
   :members:
   :show-used-by:
   :optional:

ras
~~~

.. autosvmodule:: ras
   :members:
   :show-used-by:
   :optional:

btb
~~~

.. autosvmodule:: btb
   :members:
   :show-used-by:
   :optional:

bht
~~~

.. autosvmodule:: bht
   :members:
   :show-used-by:
   :optional:

instr_scan
~~~~~~~~~~

.. autosvmodule:: instr_scan
   :members:
   :show-used-by:
   :optional:

instr_queue
~~~~~~~~~~~

.. autosvmodule:: instr_queue
   :members:
   :show-used-by:
   :optional:

