"""``sv_compilation_flags``: slang CompilationFlags set on the Compilation.

The case that needs one: slang 9-12 report a false "cyclic dependency" when a
virtual interface is assigned from a hierarchical reference into the second
of two identically parameterized wrapper instances, whose interface has a
port sized by a derived parameter. The instances share one cached body;
``DisableInstanceCaching`` elaborates each on its own. The code is legal
(IEEE 1800-2017 6.20.2, 23.2.2, 25.9).
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model import ModelBuilder

pytestmark = pytest.mark.unit

CODE = """\
interface xif #(parameter int A = 8, parameter int W = A) (input [W-1:0] d);
endinterface
module xtor; xif u_if (.d()); endmodule
module top;
  xtor u_a();
  xtor u_b();
  virtual xif v;
  initial v = u_b.u_if;
endmodule
"""


def _cyclic(builder):
    builder.build_from_text(CODE, "cyclic.sv")
    return [d for d in builder.diagnostics if "cyclic dependency" in d]


def test_default_reports_slangs_false_cycle():
    # Documents the slang behaviour the option exists for. If slang fixes it,
    # this test fails and the explanation above can go.
    assert _cyclic(ModelBuilder())


def test_disable_instance_caching_removes_it():
    assert not _cyclic(ModelBuilder(compilation_flags=["DisableInstanceCaching"]))


def test_unknown_flag_is_an_error():
    with pytest.raises(ValueError, match="NoSuchFlag"):
        ModelBuilder(compilation_flags=["NoSuchFlag"]).build_from_text(CODE, "x.sv")
