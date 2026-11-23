"""The ``run`` rule over hand-built classes (stitching plan §3.3).

No pyslang: the model here is a dictionary of :class:`UvmType`\\ s and items,
which is all :func:`run` reads.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sphinx_systemverilog.model.uvm import UvmCall, UvmMethod, UvmType
from sphinx_systemverilog.svdb.uvm_inline import ISSUE_CYCLE, ISSUE_DEPTH, run

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Item:
    name: str
    method: str
    step: int | None
    conditional: bool = False
    multiplicity: str = "1"


class Model:
    """``classes`` is ``key -> (base, {method: (virtual, calls)}, [Item])``."""

    def __init__(self, classes):
        self.classes = classes

    def type(self, key):
        if key not in self.classes:
            return None
        _base, methods, _items = self.classes[key]
        return UvmType(name=key, key=key, methods=tuple(
            UvmMethod(name=n, virtual=v, calls=tuple(calls)) for n, (v, calls) in methods.items()))

    def base(self, key):
        return self.classes[key][0] if key in self.classes else None

    def items(self, key, method):
        return [i for i in self.classes[key][2] if i.method == method]


def call(step, method, **kw):
    return UvmCall(step=step, method=method, **kw)


def names(result):
    return [r.item.name for r in result.items]


def test_an_inherited_method_runs_the_base():
    m = Model({"B": ("lib", {"build_phase": (True, [])}, [Item("a", "build_phase", 0)]),
               "D": ("B", {}, [])})
    assert names(run(m, "D", "build_phase")) == ["a"]


def test_super_runs_in_step_order():
    m = Model({"B": (None, {"build_phase": (True, [])}, [Item("a", "build_phase", 0)]),
               "D": ("B", {"build_phase": (True, [call(1, "build_phase", super=True)])},
                     [Item("x", "build_phase", 0), Item("y", "build_phase", 2)])})
    r = run(m, "D", "build_phase")
    assert names(r) == ["x", "a", "y"]
    assert r.items[1].owner == "B" and r.items[1].via == (("D", "build_phase", 1),)


def test_without_super_the_base_does_not_run():
    m = Model({"B": (None, {"build_phase": (True, [])}, [Item("a", "build_phase", 0)]),
               "D": ("B", {"build_phase": (True, [])}, [Item("x", "build_phase", 0)])})
    assert names(run(m, "D", "build_phase")) == ["x"]


def test_a_virtual_helper_dispatches_from_the_actual_type():
    m = Model({"B": (None, {"build_phase": (True, [call(0, "hook")]), "hook": (True, [])},
                     [Item("b_hook", "hook", 0)]),
               "D": ("B", {"hook": (True, [])}, [Item("d_hook", "hook", 0)])})
    assert names(run(m, "D", "build_phase")) == ["d_hook"]
    assert names(run(m, "B", "build_phase")) == ["b_hook"]


def test_a_non_virtual_helper_binds_lexically():
    m = Model({"B": (None, {"build_phase": (True, [call(0, "hook")]), "hook": (False, [])},
                     [Item("b_hook", "hook", 0)]),
               "D": ("B", {"hook": (False, [])}, [Item("d_hook", "hook", 0)])})
    assert names(run(m, "D", "build_phase")) == ["b_hook"]


def test_super_from_a_redefined_helper():
    m = Model({"B": (None, {"build_phase": (True, [call(0, "hook")]), "hook": (True, [])},
                     [Item("b_hook", "hook", 0)]),
               "D": ("B", {"hook": (True, [call(0, "hook", super=True)])}, [Item("d_hook", "hook", 1)])})
    assert names(run(m, "D", "build_phase")) == ["b_hook", "d_hook"]


def test_conditional_and_loop_context_propagates():
    m = Model({"C": (None, {"build_phase": (True, [call(0, "h", conditional=True, multiplicity="N")]),
                            "h": (False, [])},
                     [Item("a", "h", 0)])})
    (a,) = run(m, "C", "build_phase").items
    assert (a.conditional, a.multiplicity) == (True, "N")


def test_items_without_a_step_run_last():
    m = Model({"C": (None, {"build_phase": (True, [])},
                     [Item("late", "build_phase", None), Item("a", "build_phase", 3)])})
    assert names(run(m, "C", "build_phase")) == ["a", "late"]


def test_a_cycle_is_an_issue_not_a_hang():
    m = Model({"C": (None, {"build_phase": (True, [call(0, "a")]), "a": (False, [call(0, "b")]),
                            "b": (False, [call(0, "a")])}, [Item("x", "b", 1)])})
    r = run(m, "C", "build_phase")
    assert names(r) == ["x"]
    assert [(i.kind, i.method) for i in r.issues] == [(ISSUE_CYCLE, "a")]


def test_depth_is_bounded():
    methods = {"build_phase": (True, [call(0, "h0")])}
    methods.update({f"h{i}": (False, [call(0, f"h{i + 1}")]) for i in range(20)})
    r = run(Model({"C": (None, methods, [])}), "C", "build_phase", max_inline=4)
    assert [i.kind for i in r.issues] == [ISSUE_DEPTH]


def test_a_constructor_without_super_new_still_runs_the_base():
    m = Model({"B": (None, {"new": (False, [])}, [Item("ovr", "new", 0)]),
               "D": ("B", {"new": (False, [])}, [Item("own", "new", 0)])})
    assert names(run(m, "D", "new")) == ["ovr", "own"]


def test_an_unknown_base_ends_the_search():
    m = Model({"D": ("uvm_env", {}, [])})
    assert run(m, "D", "build_phase").items == []
