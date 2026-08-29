"""U4-TEST-2: ``body()`` control flow, macro collapse, and what is counted.

Three facts carry this phase:

* **the control flow survives elaboration.** ``StatementBlockKind`` says which
  of the four join flavours a fork has, and a named block keeps its label, so
  the diagram reads both out of the source rather than guessing either;
* **a macro invocation is one step.** `` `uvm_do `` expands to a dozen
  statements, and grouping them by *invocation* --- not by macro name --- is
  what keeps two adjacent uses two steps;
* **what is not drawn is counted.** A ``body()`` is mostly not control flow,
  and a diagram of only the constructs it understands would claim the task is
  shorter than it is.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import (
    ACT_ACTION,
    ACT_DECISION,
    ACT_DELAY,
    ACT_FORK,
    ACT_ITEM,
    ACT_LOOP,
    ACT_SEQUENCE,
    JOIN_ALL,
    JOIN_ANY,
    JOIN_NONE,
    is_sequence,
    is_sequence_item,
)
from tests.conftest import uvm_stub_index

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def provider():
    return uvm_stub_index("seq_tb.sv").uvm_provider


def _kinds(activities):
    return [node.kind for node in activities]


def _first(sequence, kind):
    return next(node for node in sequence.walk() if node.kind == kind)


# -- the shape ---------------------------------------------------------------


def test_the_body_reproduces_the_probed_shape(provider):
    """The §8.6 probe is the evidence this feature rests on; this pins it."""
    main = provider.sequence("main_seq")
    assert _kinds(main.body) == [ACT_DECISION, ACT_FORK, ACT_ACTION]
    assert main.body[2].label == "disable fork"


def test_a_conditional_is_a_decision_with_its_condition_as_written(provider):
    decision = _first(provider.sequence("main_seq"), ACT_DECISION)
    assert decision.label == "do_cfg"
    assert [branch.label for branch in decision.children] == ["yes"]


def test_a_fork_carries_the_join_semantics_from_the_source(provider):
    """All four flavours are distinguished, so the join bar is never guessed."""
    assert _first(provider.sequence("main_seq"), ACT_FORK).join == JOIN_ANY
    forks = [n for n in provider.sequence("join_seq").walk() if n.kind == ACT_FORK]
    assert [fork.join for fork in forks] == [JOIN_ALL, JOIN_NONE]


def test_named_fork_branches_keep_their_labels(provider):
    """The branch names in the diagram are human-authored, not generated."""
    fork = _first(provider.sequence("main_seq"), ACT_FORK)
    assert [branch.label for branch in fork.children] == ["traffic", "timeout"]


def test_an_unnamed_fork_branch_is_numbered(provider):
    fork = next(n for n in provider.sequence("join_seq").walk() if n.kind == ACT_FORK)
    assert [branch.label for branch in fork.children] == ["branch 1", "branch 2"]


def test_a_loop_is_labelled_with_its_controlling_expression(provider):
    """``n_bursts`` is a variable, so it is shown, not folded to a number."""
    loop = _first(provider.sequence("main_seq"), ACT_LOOP)
    assert loop.label == "repeat (n_bursts)"


def test_a_forever_loop_has_no_controlling_expression(provider):
    loop = _first(provider.sequence("join_seq"), ACT_LOOP)
    assert loop.label == "forever"


def test_a_delay_is_written_as_the_source_writes_it(provider):
    assert _first(provider.sequence("main_seq"), ACT_DELAY).label == "#100ns"


def test_the_activity_tree_nests(provider):
    """The repeat is *inside* the traffic branch, not a sibling of the fork."""
    fork = _first(provider.sequence("main_seq"), ACT_FORK)
    traffic = fork.children[0]
    assert _kinds(traffic.children) == [ACT_LOOP]
    assert _kinds(traffic.children[0].children) == [ACT_SEQUENCE]


# -- what a node is about ----------------------------------------------------


def test_a_sub_sequence_start_names_the_created_type(provider):
    """The handle is declared ``cfg_seq cfg`` and created through the factory;
    either route gives the same answer here, and the create is preferred."""
    node = _first(provider.sequence("main_seq"), ACT_SEQUENCE)
    assert (node.label, node.type_name) == ("cfg", "cfg_seq")


def test_sub_sequences_are_listed_in_first_seen_order(provider):
    assert provider.sequence("main_seq").subsequences() == ["cfg_seq", "traf_seq"]


def test_a_transaction_is_an_item_and_not_a_sequence(provider):
    """Told apart by the operand's *type*, which is the only thing that can:
    ``start_item(it)`` and ``seq.start(seqr)`` are both calls on the same
    class."""
    node = _first(provider.sequence("cfg_seq"), ACT_ITEM)
    assert (node.label, node.type_name) == ("it", "seq_item")
    assert provider.sequence("cfg_seq").subsequences() == []


def test_every_sequence_is_also_a_sequence_item(provider):
    """Which is why the classifier asks the questions in this order."""
    chain = list(provider.sequence("main_seq").chain)
    assert "uvm_sequence_item" in chain
    assert is_sequence(chain)
    assert not is_sequence_item(chain)


def test_finish_item_is_absorbed_rather_than_drawn_or_counted(provider):
    """It is the back half of the transaction ``start_item`` already drew."""
    cfg = provider.sequence("cfg_seq")
    assert _kinds(cfg.body) == [ACT_ITEM]
    assert cfg.other == 0


# -- macro collapse ----------------------------------------------------------


def test_one_macro_invocation_is_one_step(provider):
    noisy = provider.sequence("noisy_seq")
    assert _kinds(noisy.body) == [ACT_ITEM, ACT_ITEM]
    assert noisy.macros == ("mini_do",)
    assert all(node.macro == "mini_do" for node in noisy.body)


def test_the_collapse_removes_real_noise(provider):
    """Not a tautology: the expansion really does contain the statements the
    filter is removing, so the reduction is measured rather than asserted.

    Counted against the raw AST, because a filter tested only against its own
    output can pass while removing nothing.
    """
    from pyslang.ast import StatementKind, SymbolKind

    compilation = uvm_stub_index("seq_tb.sv").uvm_provider._compilation
    body = None
    for package in compilation.getPackages():
        for member in package:
            if getattr(member, "name", "") != "noisy_seq":
                continue
            for sub in member:
                if getattr(sub, "kind", None) == SymbolKind.Subroutine and \
                        sub.name == "body":
                    body = sub.body

    raw = []

    def visit(stmt, depth=0):
        if stmt is None or depth > 32:
            return
        if getattr(stmt, "kind", None) == StatementKind.ExpressionStatement:
            raw.append(stmt)
        for attr in ("list", "body", "ifTrue", "ifFalse"):
            value = getattr(stmt, attr, None)
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item, depth + 1)
            elif value is not None and hasattr(value, "kind"):
                visit(value, depth + 1)

    visit(body)
    assert len(raw) == 10        # two invocations, five statements each
    assert len(provider.sequence("noisy_seq").body) == 2


def test_two_adjacent_invocations_stay_two_steps(provider):
    """The bug this guards is real and was written first: grouping on the
    macro's *definition* location merges every use of it into one node, and
    only the tokens that came from the invocation's arguments report the call
    site, so a one-invocation fixture never notices."""
    assert len(provider.sequence("noisy_seq").body) == 2


def test_a_macro_that_expands_to_nothing_drawable_is_counted_once(provider):
    """Not once per statement it happens to expand to."""
    traf = provider.sequence("traf_seq")
    assert _kinds(traf.body) == [ACT_ITEM]
    assert traf.other == 0


# -- honesty about what is not drawn -----------------------------------------


def test_statements_that_are_not_control_flow_are_counted(provider):
    """``n_bursts = 4`` and two ``$display`` calls."""
    assert provider.sequence("main_seq").other == 3


def test_declarations_are_neither_drawn_nor_counted(provider):
    """``cfg_seq cfg;`` is part of writing a task, not part of what it does;
    counting it as "not shown" would report noise as loss."""
    assert provider.sequence("join_seq").other == 0


def test_a_sequence_that_does_not_override_body_says_so(provider):
    """Distinct from a sequence with an empty body, and from a missing class."""
    silent = provider.sequence("silent_seq")
    assert silent is not None
    assert silent.overridden is False
    assert silent.declared_by == "uvm_sequence_base"
    assert silent.empty


# -- resolution --------------------------------------------------------------


def test_a_component_is_not_a_sequence(provider):
    assert provider.sequence("seq_env") is None


def test_an_unknown_name_is_not_a_sequence(provider):
    assert provider.sequence("no_such_seq") is None


def test_a_qualified_name_resolves(provider):
    assert provider.sequence("seq_tb_pkg::main_seq").name == "main_seq"


def test_each_sequence_is_walked_once(provider):
    before = provider.sequence_walk_count
    provider.sequence("main_seq")
    provider.sequence("main_seq")
    assert provider.sequence_walk_count == before


def test_a_sequence_walk_does_not_pay_for_a_tree():
    """A page with only an activity diagram must not trigger the hierarchy
    walk, which is the expensive one."""
    provider = uvm_stub_index("seq_tb.sv").uvm_provider
    provider.sequence("main_seq")
    assert provider.walk_count == 0
    assert provider.config_walk_count == 0
