Cache subsystem
===============

This configuration selects the write-through cache subsystem.  A different
``CVA6Cfg`` selects a different one — an if-generate decides, and the
hierarchy below shows the branch that was actually taken.

.. sv:instance-tree:: wt_cache_subsystem
   :depth: 2
   :optional:


Where it sits
-------------

.. sv:used-by:: wt_cache_subsystem
   :optional:


wt_cache_subsystem
------------------

.. autosvmodule:: wt_cache_subsystem
   :members:
   :show-parameters-used:
   :optional:


Submodules
----------

cva6_icache
~~~~~~~~~~~

.. autosvmodule:: cva6_icache
   :members:
   :show-used-by:
   :optional:

wt_dcache
~~~~~~~~~

.. autosvmodule:: wt_dcache
   :members:
   :show-used-by:
   :optional:

wt_axi_adapter
~~~~~~~~~~~~~~

.. autosvmodule:: wt_axi_adapter
   :members:
   :show-used-by:
   :optional:

