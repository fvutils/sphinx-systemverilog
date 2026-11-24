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
    ACT_CALL,
    ACT_DECISION,
    ACT_DELAY,
    ACT_FORK,
    ACT_ITEM,
    ACT_LOOP,
    ACT_OBJECTION,
    ACT_SEQUENCE,
    ACT_WAIT,
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


# -- component task phases ------------------------------------------------------


def test_a_test_run_phase_is_an_activity(provider):
    """A test's ``run_phase`` runs behaviour as ``body()`` does, so it is
    walked by the same code and starts the same kind of sub-sequence node."""
    run = provider.activity("seq_test")
    assert run.method == "run_phase"
    assert run.declared_by == "seq_test" and run.overridden
    assert _kinds(run.body) == [
        ACT_OBJECTION, ACT_FORK, ACT_ACTION, ACT_WAIT, ACT_WAIT, ACT_OBJECTION,
    ]
    assert run.subsequences() == ["main_seq"]
    assert run.other == 0


def test_objections_are_steps_of_their_own(provider):
    run = provider.activity("seq_test")
    labels = [n.label for n in run.walk() if n.kind == ACT_OBJECTION]
    assert labels == ["raise objection", "drop objection"]


def test_an_event_wait_is_not_drawn_as_a_delay(provider):
    """``@(e)`` used to be labelled ``#e``: a delay always ends, an event wait
    only if something else happens, and the two must not read the same."""
    run = provider.activity("seq_test")
    assert [n.label for n in run.walk() if n.kind == ACT_WAIT] == [
        "@(settled)", "wait fork",
    ]
    assert [n.label for n in run.walk() if n.kind == ACT_DELAY] == ["#1us"]
    assert any(n.label == "-> settled" for n in run.walk())


def test_the_natural_task_depends_on_the_class(provider):
    assert provider.activity("main_seq").method == "body"
    assert provider.activity("main_seq") == provider.sequence("main_seq")
    assert provider.activity("seq_env").method == "run_phase"


def test_an_inherited_phase_is_not_overridden(provider):
    env = provider.activity("seq_env")
    assert not env.overridden and env.declared_by == "uvm_component"
    assert env.empty


def test_only_task_methods_of_the_right_kind_of_class(provider):
    """A sequence's task is ``body``; a component's are its task phases. A
    function phase has no behaviour to draw, and a component is not a sequence."""
    assert provider.activity("seq_test", "build_phase") is None
    assert provider.activity("seq_test", "body") is None
    assert provider.activity("main_seq", "run_phase") is None
    assert provider.sequence("seq_test") is None
    assert provider.activity("seq_item") is None


# -- the sub-sequence catalog -----------------------------------------------------


def test_a_start_records_its_sequencer_and_how_its_type_was_found(provider):
    start = next(n for n in provider.activity("seq_test").walk() if n.kind == ACT_SEQUENCE)
    assert start.sequencer == "env.seqr"
    assert start.resolved == "created"
    handed = [n for n in provider.sequence("rec_seq").walk() if n.label == "handed_in"]
    assert handed[0].resolved == "declared" and handed[0].type_name == "leaf_seq"


def test_the_catalog_is_the_transitive_closure(provider):
    catalog = provider.catalog("seq_test")
    assert catalog.method == "run_phase"
    assert [e.type_name for e in catalog.entries] == ["main_seq", "cfg_seq", "traf_seq"]
    assert [e.type_name for e in catalog.direct] == ["main_seq"]
    assert catalog.entry("cfg_seq").started_by == ["main_seq"]
    assert catalog.entry("cfg_seq").items == ("seq_item",)
    assert all(e.origin == "" and e.found for e in catalog.entries)


def test_the_catalog_of_a_sequence_is_its_body(provider):
    assert [e.type_name for e in provider.catalog("main_seq").entries] == ["cfg_seq", "traf_seq"]
    leaf = provider.catalog("leaf_seq")
    assert not leaf.entries and leaf.items == ("seq_item",)


def test_a_sequence_that_starts_itself_is_listed_once(provider):
    catalog = provider.catalog("rec_seq")
    rec = catalog.entry("rec_seq")
    assert rec.recursive and len(rec.sites) == 1
    leaf = catalog.entry("leaf_seq")
    assert not leaf.recursive and leaf.resolutions == ["declared"]


def test_a_sequence_the_lookup_cannot_find_is_kept_and_marked(provider):
    from sphinx_systemverilog.model.uvm_catalog import build_catalog

    catalog = build_catalog(provider.activity("seq_test"),
                            lambda name: None, origin=lambda name: "vip")
    [main] = catalog.entries
    assert not main.found and main.origin == "vip"


def test_the_catalog_stops_at_its_limit(provider):
    from sphinx_systemverilog.model.uvm_catalog import build_catalog

    catalog = build_catalog(provider.activity("seq_test"), provider.sequence, limit=1)
    assert catalog.truncated and len(catalog.entries) == 1


# -- phase 3: member handles, factory overrides, users ------------------------------


@pytest.fixture(scope="module")
def deps():
    return uvm_stub_index("seq_dep_tb.sv").uvm_provider


def _starts(task):
    return {n.label: n for n in task.walk() if n.kind == ACT_SEQUENCE}


def test_a_member_created_in_another_method_takes_that_type(deps):
    starts = _starts(deps.activity("dep_test"))
    warm = starts["warm"]
    assert (warm.type_name, warm.resolved, warm.created_in, warm.created_by) == \
        ("warm_seq", "member", "build_phase", "factory")
    assert (starts["s"].resolved, starts["s"].created_by) == ("created", "factory")
    assert starts["byhand"].created_by == "new"


def test_a_subclass_reads_its_base_class_creates(deps):
    """``other_test.build_phase`` calls ``super``: the member's create is in
    the base class's version, which is read too."""
    assert _starts(deps.activity("other_test"))["warm"].type_name == "warm_seq"


def test_an_unconditional_override_by_the_test_is_applied(deps):
    catalog = deps.catalog("dep_test")
    assert [(o.original, o.replacement) for o in catalog.applied] == [("base_seq", "fast_seq")]
    fast = catalog.entry("fast_seq")
    assert fast.direct and [s.original for s in fast.sites] == ["base_seq"]
    # The replacement is walked: what it starts is a dependency.
    assert catalog.entry("burst_seq").depth == 2
    # `new` bypasses the factory, so byhand stays a base_seq.
    assert [s.handle for s in catalog.entry("base_seq").sites] == ["byhand"]


def test_an_override_that_is_not_certain_is_listed_as_possible(deps):
    catalog = deps.catalog("dep_test")
    cool = catalog.entry("cool_seq")
    assert [(o.replacement, o.conditional) for o in cool.possible] == [("cold_seq", True)]
    assert catalog.entry("cold_seq") is None
    # Registered by a subclass: possible here, applied there.
    assert [o.owner for o in catalog.entry("warm_seq").possible] == ["other_test"]
    sub = deps.catalog("other_test")
    assert sub.entry("warm_seq") is None
    assert sub.entry("cool_seq").sites[0].original == "warm_seq"


def test_a_sequence_root_applies_no_override(deps):
    assert deps.catalog("fast_seq").applied == ()


def test_users_are_read_off_every_catalog(deps):
    users = deps.users("burst_seq")
    assert [(u.root, u.method, u.depth) for u in users.users] == [
        ("dep_test", "run_phase", 2), ("other_test", "run_phase", 2), ("fast_seq", "body", 1)]
    assert [(s.started_by, s.method) for s in users.sites] == [("fast_seq", "body")]
    # Reached only through the override the test registers.
    assert {u.root for u in deps.users("fast_seq").users} == {"dep_test", "other_test"}


def test_a_sequence_nothing_starts_has_no_users(deps):
    users = deps.users("cold_seq")
    assert users.users == () and users.sites == ()
    assert [o.original for o in users.replaces] == ["cool_seq"]


# -- helper tasks and super. (phase 4) -------------------------------------------


@pytest.fixture(scope="module")
def calls():
    return uvm_stub_index("seq_call_tb.sv").uvm_provider


def _calls(task):
    return [n for n in task.walk() if n.kind == ACT_CALL]


def test_super_and_helper_tasks_are_inlined(calls):
    task = calls.activity("call_test")
    top = [(n.kind, n.label) for n in task.body]
    assert top == [("call", "super.run_phase()"), ("call", "drain()")], \
        "setup() is a function: not followed, and not drawn"
    base = task.body[0]
    assert base.declared_by == "call_base_test"
    assert [n.kind for n in base.children] == ["objection", "call", "objection"]


def test_an_implicit_call_dispatches_from_the_walked_class(calls):
    # call_base_test::run_phase calls traffic(); for call_test that is its own.
    traffic = calls.activity("call_test").body[0].children[1]
    assert (traffic.label, traffic.declared_by) == ("traffic()", "call_test")
    assert _starts_in(traffic) == {"c": "call_seq"}
    base = next(n for n in _calls(calls.activity("call_base_test")) if n.label == "traffic()")
    assert base.declared_by == "call_base_test"
    assert _starts_in(base) == {"s": "step_seq"}


def _starts_in(node):
    return {n.label: n.type_name for n in node.walk() if n.kind == ACT_SEQUENCE}


def test_a_task_calling_itself_is_cut(calls):
    drains = [n for n in _calls(calls.activity("call_test")) if n.label == "drain()"]
    assert len(drains) == 2
    assert drains[0].children and not drains[1].children


def test_a_member_a_helper_creates_is_known_to_the_caller(calls):
    starts = _starts(calls.activity("call_seq"))
    assert (starts["m_step"].type_name, starts["m_step"].resolved) == ("step_seq", "created")


def test_the_catalog_follows_calls_and_names_them(calls):
    catalog = calls.catalog("call_test")
    assert [e.type_name for e in catalog.entries] == ["call_seq", "tail_seq", "step_seq"]
    call_seq = catalog.entry("call_seq")
    assert call_seq.sites[0].via == ("super.run_phase()", "traffic()")
    assert catalog.entry("tail_seq").sites[0].via == ("drain()",)
    assert catalog.entry("step_seq").depth == 2


# -- the nested sequence tree (phase 4) ------------------------------------------


def _shape(nodes):
    return [(n.handle, n.type_name, _shape(n.children)) for n in nodes]


def test_the_tree_nests_each_start_under_its_starter(calls):
    tree = calls.tree("call_test")
    assert _shape(tree.children) == [
        ("c", "call_seq", [("s", "step_seq", []), ("m_step", "step_seq", [])]),
        ("t", "tail_seq", []),
    ]
    step, again = tree.children[0].children
    assert (step.context, step.via, step.repeated) == (("repeat (2)",), ("do_steps()",), False)
    assert again.repeated, "step_seq is opened once"


def test_the_tree_applies_overrides_as_the_catalog_does(deps):
    tree = deps.tree("dep_test")
    s = next(n for n in tree.children if n.handle == "s")
    assert (s.type_name, s.original) == ("fast_seq", "base_seq")
    assert [c.type_name for c in s.children] == ["burst_seq"]
    assert {n.type_name for n in tree.walk()} == {e.type_name for e in deps.catalog("dep_test").entries}


def test_the_tree_marks_recursion_and_context(provider):
    tree = provider.tree("rec_seq")
    again = tree.children[0]
    assert again.recursive and not again.children
    assert again.context == ("level > 0: yes",)
    traf = provider.tree("main_seq").children[1]
    assert traf.context == ("fork (join_any): traffic", "repeat (n_bursts)")


def test_sequencers_resolve_against_the_component_tree(calls):
    tree = calls.tree("vseq_test")
    v, t, elsewhere = tree.children
    assert (v.sequencer_path, v.sequencer_type) == ("uvm_test_top.env.vseqr", "call_vsequencer")
    # p_sequencer.agt_sqr is a handle the virtual sequencer holds, assigned in
    # call_env.connect_phase.
    assert {c.sequencer_path for c in v.children} == {"uvm_test_top.env.agt.sqr"}
    nested = v.children[1].children[0]
    assert (nested.sequencer, nested.sequencer_path) == ("m_sequencer", "uvm_test_top.env.agt.sqr")
    assert t.sequencer_path == "uvm_test_top.env.agt.sqr", "this. is allowed"
    assert elsewhere.sequencer_path == "", "a local handle is not followed"


def test_a_sequence_tree_resolves_no_sequencer(calls):
    assert not any(n.sequencer_path for n in calls.tree("call_vseq").walk())
