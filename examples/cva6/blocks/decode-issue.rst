Decode and issue
================

Instruction decode turns fetched words into the core's internal
micro-operation format; issue tracks dependencies and dispatches to the
functional units.


id_stage
--------

.. sv:instance-tree:: id_stage
   :depth: 2
   :optional:

.. autosvmodule:: id_stage
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:


decoder
-------

.. sv:instance-tree:: decoder
   :depth: 2
   :optional:

.. autosvmodule:: decoder
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:


compressed_decoder
------------------

.. sv:instance-tree:: compressed_decoder
   :depth: 2
   :optional:

.. autosvmodule:: compressed_decoder
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:


issue_stage
-----------

.. sv:instance-tree:: issue_stage
   :depth: 2
   :optional:

.. autosvmodule:: issue_stage
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:


scoreboard
----------

.. sv:instance-tree:: scoreboard
   :depth: 2
   :optional:

.. autosvmodule:: scoreboard
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:


issue_read_operands
-------------------

.. sv:instance-tree:: issue_read_operands
   :depth: 2
   :optional:

.. autosvmodule:: issue_read_operands
   :members:
   :show-used-by:
   :show-parameters-used:
   :optional:

