Execute — the functional units
==============================

``ex_stage`` instantiates every functional unit.  Which units are present
depends on the configuration, and the tree below reflects the units that
this configuration actually elaborated — not every unit the source can
produce.

.. sv:instance-tree:: ex_stage
   :depth: 2
   :optional:


Where it sits
-------------

.. sv:used-by:: ex_stage
   :optional:


ex_stage
--------

.. autosvmodule:: ex_stage
   :members:
   :show-parameters-used:
   :optional:


Submodules
----------

alu_wrapper
~~~~~~~~~~~

.. autosvmodule:: alu_wrapper
   :members:
   :show-used-by:
   :optional:

branch_unit
~~~~~~~~~~~

.. autosvmodule:: branch_unit
   :members:
   :show-used-by:
   :optional:

csr_buffer
~~~~~~~~~~

.. autosvmodule:: csr_buffer
   :members:
   :show-used-by:
   :optional:

mult
~~~~

.. autosvmodule:: mult
   :members:
   :show-used-by:
   :optional:

fpu_wrap
~~~~~~~~

.. autosvmodule:: fpu_wrap
   :members:
   :show-used-by:
   :optional:

load_store_unit
~~~~~~~~~~~~~~~

.. autosvmodule:: load_store_unit
   :members:
   :show-used-by:
   :optional:

cvxif_fu
~~~~~~~~

.. autosvmodule:: cvxif_fu
   :members:
   :show-used-by:
   :optional:

aes
~~~

.. autosvmodule:: aes
   :members:
   :show-used-by:
   :optional:

