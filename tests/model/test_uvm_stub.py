"""U0-TEST-1: the mini-UVM stub is a valid basis for the rest of the tests.

The stub carries the bulk of UVM coverage, so its validity is a premise of
every later test rather than an incidental detail.  Two things are asserted:

* it **compiles clean** --- a stub with errors would make every downstream
  failure ambiguous between "the extractor is wrong" and "the fixture is";
* the **factory mechanism reproduces**, i.e. a ``type_id::create`` call site
  written against the stub yields its ``Tname`` exactly as one written against
  real UVM does.  That is the single fact the whole component model rests on,
  and it is the one thing a hand-written stub could plausibly get wrong.

The second point is what makes the stub legitimate rather than merely
convenient.  Behaviour that depends on real UVM internals is covered by the
corpus tests instead.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import registry_type_name
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


def test_stub_compiles_without_errors():
    index = uvm_stub_index()

    assert index.diagnostics == []
    assert len(index) > 0


def test_stub_plus_testbench_compiles_without_errors():
    index = uvm_stub_index("basic_tb.sv")

    assert index.diagnostics == []


def _create_calls(index, package: str, cls: str, method: str = "build_phase"):
    """Every ``create`` call expression inside one class method."""
    from pyslang.ast import ExpressionKind, SymbolKind

    comp = index.uvm_provider._compilation
    pkg = next(p for p in comp.getPackages() if p.name == package)
    sym = next(
        m for m in pkg
        if m.kind == SymbolKind.ClassType and m.name == cls
    )
    body = next(s for s in sym if getattr(s, "name", "") == method).body

    found = []

    def visit_expr(expr):
        if expr is None:
            return
        if getattr(expr, "kind", None) == ExpressionKind.Call:
            found.append(expr)
        for attr in ("left", "right", "operand"):
            visit_expr(getattr(expr, attr, None))

    def visit_stmt(stmt, depth=0):
        if stmt is None or depth > 20:
            return
        visit_expr(getattr(stmt, "expr", None))
        for attr in ("list", "body", "ifTrue", "ifFalse", "statements"):
            value = getattr(stmt, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit_stmt(item, depth + 1)
            elif value is not None and hasattr(value, "kind"):
                visit_stmt(value, depth + 1)

    visit_stmt(body)
    return found


def test_registry_tname_is_recoverable_from_a_create_call():
    """The fact the entire component model depends on (§0.2)."""
    index = uvm_stub_index("basic_tb.sv")

    calls = _create_calls(index, "basic_tb_pkg", "my_env")
    names = [registry_type_name(c) for c in calls]

    assert "my_agent" in names
    assert "my_scoreboard" in names


def test_registry_type_name_ignores_calls_that_are_not_creates():
    """Used as the test for "is this a factory create", so it must say no."""
    index = uvm_stub_index("basic_tb.sv")

    # `my_monitor.build_phase` constructs its analysis port with `new`, not the
    # factory, so it holds no create calls at all.
    calls = _create_calls(index, "basic_tb_pkg", "my_monitor")

    assert [c for c in calls if registry_type_name(c) is not None] == []


def test_stub_is_cheap_enough_to_be_the_default_fixture():
    """The stub's whole justification is that it is not real UVM.

    Asserted loosely: the point is the order of magnitude, not a benchmark.
    Real UVM costs ~0.10s per compile and needs an ivpm fetch; if the stub ever
    approaches that, it has grown past its purpose and the trade-off that put
    it here no longer holds.
    """
    import time

    start = time.perf_counter()
    uvm_stub_index("basic_tb.sv")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5
