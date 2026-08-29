"""U1-TEST-7: the extraction works against **real** UVM, not just the stub.

The stub carries the bulk of the coverage because it is ~250x cheaper to
compile and needs no ivpm fetch. That trade-off is only legitimate if something
checks the assumption behind it, which is what this module is for: the stub
reproduces the factory *mechanism*, but it is not UVM, and any behaviour that
depends on the real library's internals has to be verified here.

Run with ``pytest -m corpus``. Skipped when the sources are absent.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.model.uvm import STATE_OK, UvmProvider
from tests.conftest import UVM_SRC, UVM_TB, requires_uvm

pytestmark = pytest.mark.corpus


@pytest.fixture(scope="module")
def real_uvm_index():
    """A testbench compiled against the real UVM library."""
    from sphinx_systemverilog.model.index import build_index

    return build_index(
        source_dirs=[str(UVM_SRC)],
        build_units=[
            str(UVM_SRC / "uvm_pkg.sv"),
            str(UVM_TB / "real_uvm_tb.sv"),
        ],
        include_dirs=[str(UVM_SRC), str(UVM_TB)],
        doc_style="naturaldocs",
        use_cache=False,
    )


@requires_uvm
def test_the_testbench_compiles_against_real_uvm(real_uvm_index):
    """A floor under everything else here: no errors means the rest is real."""
    assert real_uvm_index.diagnostics == []


@requires_uvm
def test_the_root_is_detected_from_run_test(real_uvm_index):
    structure = real_uvm_index.uvm_structure

    assert structure.root == "corpus_test"
    assert structure.root_origin == "run_test"


@requires_uvm
def test_the_factory_mechanism_works_against_the_real_registry(real_uvm_index):
    """The one fact the stub exists to reproduce, verified against the source.

    Real `uvm_component_registry` is considerably more elaborate than the stub's
    --- it inherits from `uvm_object_wrapper`, registers with a singleton
    factory, and `create` routes through `create_component_by_type`. None of
    that changes where `Tname` lives, and this is what proves it.
    """
    structure = real_uvm_index.uvm_structure

    assert [c.type_name for c in structure.children_of("corpus_test")] == [
        "corpus_env"
    ]
    env = {c.handle: c.type_name for c in structure.children_of("corpus_env")}
    assert env["agt"] == "corpus_agent"

    agent = {c.handle: c.type_name for c in structure.children_of("corpus_agent")}
    assert agent["drv"] == "corpus_driver"
    assert agent["mon"] == "corpus_monitor"


@requires_uvm
def test_tiers_are_assigned_from_real_uvm_base_classes(real_uvm_index):
    """The §7.4 taxonomy is written against real UVM's class names."""
    structure = real_uvm_index.uvm_structure

    assert structure.type_of("corpus_test").tier == "test"
    assert structure.type_of("corpus_env").tier == "env"
    assert structure.type_of("corpus_agent").tier == "agent"
    assert structure.type_of("corpus_driver").tier == "driver"
    assert structure.type_of("corpus_monitor").tier == "monitor"


@requires_uvm
def test_library_internals_are_black_boxed(real_uvm_index):
    """Without the always-on stop, the tree would be mostly UVM.

    Real `uvm_component` builds a substantial amount of its own machinery, and
    a walk that descended into it would bury the user's testbench in library
    detail --- which is the noise the rule exists to remove.
    """
    structure = real_uvm_index.uvm_structure

    walked = [name for name in structure.children if name.startswith("uvm_")]
    assert walked == [], f"walked into UVM library types: {walked}"


@requires_uvm
def test_user_components_are_not_black_boxed_by_the_library_rule(real_uvm_index):
    """Every one of them derives from `uvm_component`; none may be stopped at."""
    structure = real_uvm_index.uvm_structure

    for name in ("corpus_env", "corpus_agent"):
        child = next(
            c
            for children in structure.children.values()
            for c in children
            if c.type_name == name
        )
        assert child.state == STATE_OK


@requires_uvm
def test_a_real_uvm_tlm_port_is_not_a_component(real_uvm_index):
    """The divergence this module exists to catch.

    The stub originally declared `uvm_port_base extends uvm_component`, which
    put an analysis port under every monitor in every stub-based test. Real UVM
    declares `uvm_port_base #(IF) extends IF`, where `IF` is a `uvm_tlm_if_base`
    deriving from `uvm_void` --- a port owns an internal component proxy rather
    than being one. The stub-based tests all passed; this is what did not.

    Kept as a named test rather than folded into the tree assertions, because
    the property is about the library and not about any one testbench.
    """
    structure = real_uvm_index.uvm_structure

    ports = [
        c
        for children in structure.children.values()
        for c in children
        if c.type_name.startswith("uvm_analysis_port")
    ]
    assert ports == [], (
        "a TLM port is not a uvm_component and must not appear in a "
        "hierarchy read from build_phase"
    )
    assert structure.children_of("corpus_monitor") == []


@requires_uvm
def test_a_real_uvm_walk_stays_within_budget(real_uvm_index):
    """uvm_pkg alone holds hundreds of classes; the tree must stay the user's.

    This is the practical check on the library rule: without it the walk would
    not merely be noisy, it would be large.
    """
    structure = real_uvm_index.uvm_structure

    assert structure.truncated is False
    assert len(structure.children) < 20


@requires_uvm
def test_extraction_against_real_uvm_is_still_lazy(real_uvm_index):
    """Cost is only paid when a directive asks --- especially at this size."""
    provider = UvmProvider(real_uvm_index.uvm_provider._compilation)

    assert provider.computed is False


# -- config_db against the real library (U2) ----------------------------------
#
# The stub's `uvm_config_db` is a five-line class with two static methods. The
# real one extends `uvm_resource_db#(T)` and delegates both halves to a separate
# implementation class. The extractor keys on the *lexical* path of the called
# subroutine and on the specialization's `T` parameter; whether either survives
# that much machinery is a question about UVM, and only this file can answer it.


@pytest.fixture(scope="module")
def real_config(real_uvm_index):
    return real_uvm_index.uvm_provider.config()


@requires_uvm
def test_config_db_calls_are_recognized_against_real_uvm(real_config):
    assert len(real_config.sets) == 3
    assert len(real_config.gets) == 2


@requires_uvm
def test_a_get_in_an_if_condition_is_found_against_real_uvm(real_config):
    """The §8.2 caveat, closed against the library it was raised about.

    The assessment confirmed the `set` side end-to-end and explicitly left the
    `get` unconfirmed, because its probe's walker did not descend into
    if-conditions. This is that gap, tested where it was found.
    """
    get = next(a for a in real_config.gets if a.field == "n_items")

    assert get.owner == "corpus_driver"
    assert get.type_name == "int"


@requires_uvm
def test_the_specialization_type_survives_the_real_class_hierarchy(real_config):
    """`T` is read off the specialization, not off the call's return type.

    Real `uvm_config_db#(T)` extends `uvm_resource_db#(T)`, so there is a second
    `T` in the base class to be confused with. There is no ambiguity in
    practice, and this is what says so.
    """
    types = {a.field: a.type_name for a in real_config.accesses}

    assert types["n_items"] == "int"
    assert types["vif"] == "corpus_if"


@requires_uvm
def test_the_virtual_interface_binding_extracts_from_a_top_module(real_config):
    """The RTL bridge (§8.2): the set lives in a module, outside any component."""
    st = next(a for a in real_config.sets if a.field == "vif")

    assert st.owner == "corpus_tb_top"
    assert st.cntxt == "null"
    assert st.scope == "uvm_test_top"
    assert st.value == "u_if", "the RTL instance the agent is bound to"


@requires_uvm
def test_the_orphan_is_detected_against_real_uvm(real_config):
    assert [a.field for a in real_config.orphan_sets] == ["n_itmes"]


@requires_uvm
def test_uvms_own_internal_config_accesses_are_not_reported(real_config):
    """The table must be about the user's testbench, not about UVM.

    `uvm_pkg` really does call `config_db` from inside its own components ---
    `uvm_root`, `uvm_sequencer_base` and `uvm_component::set_config_object` all
    do. Reporting them would bury the handful a reader actually wrote.

    Worth recording how this test first passed: it passed before the filtering
    rule existed, because slang does not elaborate the bodies of methods
    nothing calls, so `uvm_sequencer_base` arrives with 10 subroutines instead
    of dozens and its accesses are simply not in the AST. A green assertion
    resting on that would be resting on an accident of elaboration. The rule is
    now explicit, and the stub --- where the method *is* elaborated --- is what
    tests it (`test_the_library_access_really_is_extractable`).
    """
    owners = {a.owner for a in real_config.accesses}

    assert not any(owner.startswith("uvm_") for owner in owners), sorted(owners)


# -- TLM connections and the schematic against the real library (U3) ----------
#
# The stub's `uvm_port_base` is a five-line class with one `connect`. Real UVM
# declares `uvm_port_base #(IF) extends IF`, where `IF` is a `uvm_tlm_if_base`
# deriving from `uvm_void`, and hands every driver and sequencer several ports
# nobody wrote. Both of those are things a stub-based test cannot see, and the
# second one changed the design: see `test_a_real_driver_arrives_with_ports_it_
# did_not_declare`.


@pytest.fixture(scope="module")
def real_schematic(real_uvm_index):
    from sphinx_systemverilog.autodoc.uvm_diagram import build_schematic

    return build_schematic(real_uvm_index.uvm_structure, "corpus_env")


@requires_uvm
def test_a_connect_call_resolves_against_the_real_port_hierarchy(real_uvm_index):
    """§3.4, tested where it was probed.

    The discriminator is the lexical path of the called subroutine, and real
    ``uvm_port_base`` is several classes further from the call site than the
    stub's. If that path came back specialized or qualified differently, every
    connection in every real testbench would be silently invisible.
    """
    connection = real_uvm_index.uvm_structure.connections_of("corpus_env")[0]

    assert connection.source.path == ("agt", "mon")
    assert connection.source.port == "ap"
    assert connection.target.path == ("sb",)
    assert connection.target.port == "aimp"


@requires_uvm
def test_a_real_analysis_imp_still_reads_as_a_port(real_uvm_index):
    """``uvm_analysis_imp`` is macro-generated in real UVM, and it is a port."""
    scoreboard = real_uvm_index.uvm_structure.type_of("corpus_scoreboard")

    assert [p.name for p in scoreboard.ports] == ["aimp"]
    assert scoreboard.ports[0].role == "imp"


@requires_uvm
def test_a_real_driver_arrives_with_ports_it_did_not_declare(real_uvm_index):
    """The divergence this phase's corpus gate caught.

    ``corpus_driver`` declares no ports at all. Real ``uvm_driver`` gives it
    three --- ``seq_item_port``, ``seq_item_prod_if`` and ``rsp_port`` --- of
    which one is the port anybody has ever drawn. The stub's driver declares
    none, so against the stub every driver box looked right for the wrong
    reason, and the rule that hides unconnected library ports exists because of
    this test rather than in spite of it.
    """
    driver = real_uvm_index.uvm_structure.type_of("corpus_driver")
    names = [p.name for p in driver.ports]

    assert "seq_item_port" in names
    assert len(names) > 1, "the library adds ports the user never wrote"
    assert all(p.library for p in driver.ports)


@requires_uvm
def test_an_unconnected_library_port_is_hidden_and_counted(real_schematic):
    drawn = {node.handle: [p.name for p in node.ports] for node in real_schematic.nodes}

    assert drawn["drv"] == ["seq_item_port"]
    assert real_schematic.hidden_ports == 3


@requires_uvm
def test_a_connected_library_port_is_still_drawn(real_schematic):
    """...and this is what stops the rule above from being a blanket exclusion.

    Both ends of a driver/sequencer connection are ports the *library*
    declares. Hiding them because of that would remove the single most
    recognizable connection in a UVM testbench.
    """
    drawn = {node.handle: [p.name for p in node.ports] for node in real_schematic.nodes}

    assert drawn["seqr"] == ["seq_item_export"]
    assert "n_agt__drv:seq_item_port -> n_agt__seqr:seq_item_export" in (
        _real_dot(real_schematic)
    )


@requires_uvm
def test_nothing_is_dropped_from_the_real_schematic(real_schematic):
    assert real_schematic.dropped == []


@requires_uvm
def test_slang_unifies_structurally_identical_specializations(real_uvm_index):
    """A pyslang fact worth pinning, because it looks like a bug and is not.

    ``corpus_monitor.ap`` is declared ``uvm_analysis_port #(corpus_item)``, and
    slang reports its type as ``uvm_analysis_port#(uvm_pkg::uvm_driver::RSP)``
    --- the spelling of whichever equivalent specialization it created first.
    The two really are the same type here (``RSP`` defaults to ``REQ``, which is
    ``corpus_item``), so nothing is wrong; but it is why a schematic labels a
    connection with the port *name* and never with the port's type.
    """
    connection = real_uvm_index.uvm_structure.connections_of("corpus_env")[0]

    assert connection.source.type_name.startswith("uvm_analysis_port")
    assert connection.kind == "analysis", "the link kind is unaffected"


def _real_dot(schematic) -> str:
    from sphinx_systemverilog.autodoc.uvm_diagram import build_schematic_dot

    return build_schematic_dot(schematic)


# -- sequence activity against the real library (U4) --------------------------
#
# The stub can reproduce a macro that expands to several statements, and it
# does.  What it cannot reproduce is what real `uvm_do` expands *to*: a
# `uvm_sequence_base` local, a `$cast` branch, and a `start` on that local
# sitting beside the `start_item` that names the user's type.  The rule that
# picks the user-typed candidate out of a macro expansion only has anything to
# choose between here.


@pytest.fixture(scope="module")
def real_seq(real_uvm_index):
    return real_uvm_index.uvm_provider.sequence("corpus_seq")


@requires_uvm
def test_a_real_sequence_body_is_read(real_seq):
    from sphinx_systemverilog.model.uvm import (
        ACT_ACTION, ACT_DECISION, ACT_FORK,
    )

    assert real_seq is not None
    assert real_seq.overridden
    assert [n.kind for n in real_seq.body] == [ACT_DECISION, ACT_FORK, ACT_ACTION]


@requires_uvm
def test_start_is_discriminated_by_its_declaring_class_in_real_uvm(real_seq):
    """``uvm_sequence_base::start`` is the lexical path the walk keys on, and
    real UVM's class hierarchy is far deeper than the stub's."""
    from sphinx_systemverilog.model.uvm import ACT_SEQUENCE

    started = [n for n in real_seq.walk() if n.kind == ACT_SEQUENCE]

    assert [n.type_name for n in started] == ["corpus_sub_seq"]


@requires_uvm
def test_real_uvm_do_collapses_to_one_step(real_uvm_index):
    """The claim in the plan --- roughly a dozen statements to one node ---
    measured against the real macro rather than against the stub's stand-in."""
    from pyslang.ast import StatementKind, SymbolKind

    from sphinx_systemverilog.model.uvm import ACT_ITEM

    compilation = real_uvm_index.uvm_provider._compilation
    body = None
    for package in compilation.getPackages():
        for member in package:
            if getattr(member, "name", "") != "corpus_sub_seq":
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
    sub = real_uvm_index.uvm_provider.sequence("corpus_sub_seq")

    assert len(raw) >= 8, "the real macro really is that noisy"
    assert [n.kind for n in sub.body] == [ACT_ITEM]
    assert sub.macros == ("uvm_do",)


@requires_uvm
def test_the_macro_step_names_the_users_type_and_not_the_librarys(real_uvm_index):
    """Real `uvm_do` declares a ``uvm_sequence_base`` local and starts it, so
    the expansion offers two candidates. The library-typed one loses.

    This is the finding the stub could not have produced: `` `mini_do `` has
    exactly one candidate, so a rule that simply took the first would pass
    every fast test and be wrong here.
    """
    sub = real_uvm_index.uvm_provider.sequence("corpus_sub_seq")

    assert sub.body[0].type_name == "corpus_item"
    assert not sub.body[0].type_name.startswith("uvm_")


@requires_uvm
def test_uvm_info_is_counted_rather_than_drawn(real_seq):
    """`` `uvm_info `` is a macro too, and a big one. It expands to nothing
    worth drawing, so it costs one line in the count and not one node.

    It is also why only macros that *produced* a node are named to the reader.
    slang reports the innermost macro, and for `` `uvm_info `` that is UVM's
    internal ``uvm_report_begin`` --- a name the user never wrote. Listing it
    under the diagram would send a reader looking for a step that is not there.
    The first version of this did exactly that, and only the corpus showed it:
    the stub has no nested macros.
    """
    assert real_seq.other >= 1
    assert real_seq.macros == ("uvm_do",)
    assert "uvm_report_begin" not in real_seq.macros


@requires_uvm
def test_named_fork_branches_survive_the_real_library(real_seq):
    from sphinx_systemverilog.model.uvm import ACT_FORK

    fork = next(n for n in real_seq.walk() if n.kind == ACT_FORK)

    assert [b.label for b in fork.children] == ["traffic", "timeout"]
    assert fork.join == "any"


@requires_uvm
def test_the_real_activity_diagram_renders(real_uvm_index):
    from sphinx_systemverilog.autodoc.uvm_activity import build_activity_dot

    provider = real_uvm_index.uvm_provider
    sequence = provider.sequence("corpus_seq")
    subs = {n: provider.sequence(n) for n in sequence.subsequences()}
    code, diagram = build_activity_dot(sequence, subs, depth=2)

    assert code.startswith("digraph uvm_activity {")
    assert diagram.expanded == ["corpus_sub_seq"]
    assert diagram.unresolved == []


# -- the RTL bridge against the real library (U5) ------------------------------
#
# The bridge is the one extraction that reads both elaborations, and the half
# the stub cannot vouch for is the *set* signature. Real `uvm_config_db#(T)`
# extends `uvm_resource_db#(T)` and its `set` takes the value through a formal
# of type `T`; whether an interface instance passed to that formal still
# arrives as a symbol the extraction can name --- rather than as a conversion
# node with nothing behind it --- is a fact about the real library.


@pytest.fixture(scope="module")
def real_bridge(real_uvm_index):
    return real_uvm_index.uvm_provider.bridge()


@requires_uvm
def test_a_virtual_interface_set_is_recognised_against_real_uvm(real_bridge):
    """Real ``uvm_config_db#(virtual corpus_if)`` is a specialization of a
    class that extends another parameterized class. The ``T`` lookup has to
    survive that, and ``isVirtualInterface`` has to be true on what it finds."""
    assert [b.field for b in real_bridge.bindings] == ["vif"]
    assert real_bridge.bindings[0].interface_type == "corpus_if"


@requires_uvm
def test_the_interface_instance_survives_the_real_signature(real_bridge):
    """The corpus question: an instance passed through a `T` formal, where the
    stub's `T` is declared identically but the surrounding class is not."""
    assert real_bridge.bindings[0].instance_path == "corpus_tb_top.u_if"


@requires_uvm
def test_the_rtl_join_holds_against_real_uvm(real_bridge):
    drivers = real_bridge.bindings[0].drivers

    assert [(d.path, d.type_name) for d in drivers] == [
        ("corpus_tb_top.u_dut", "corpus_dut"),
        ("corpus_tb_top.u_probe", "corpus_probe"),
    ]


@requires_uvm
def test_the_reader_is_found_against_real_uvm(real_bridge):
    """`U5-ACC`, against the library it is claimed for: a documented path from
    a component, through the config field, to an RTL instance."""
    binding = real_bridge.bindings[0]

    assert [a.where for a in binding.consumers] == ["corpus_test.build_phase"]
    assert binding.orphan is False
    assert binding.undriven is False


@requires_uvm
def test_the_bridge_costs_no_hierarchy_walk_against_real_uvm(real_uvm_index):
    """Real UVM elaborates a great deal more than the stub, so "the binding
    table does not walk the hierarchy" is worth measuring where it matters."""
    provider = UvmProvider(
        real_uvm_index.uvm_provider._compilation,
        real_uvm_index.uvm_provider._source_manager,
    )
    provider.bridge()

    assert provider.walk_count == 0
    assert real_uvm_index.structure_provider.walk_count == 0


# -- factory overrides against the real library (U6) ---------------------------
#
# The stub reproduces the override *signatures*, and the signatures are the
# whole thing being tested: `_OVERRIDE_SIGNATURES` is a table of argument
# positions, and UVM's own orders disagree between its two inst forms. A table
# written against a stub is a table of assumptions until it runs against the
# library it claims to describe.


@pytest.fixture(scope="module")
def real_overrides(real_uvm_index):
    return real_uvm_index.uvm_provider.overrides()


@requires_uvm
def test_the_component_wrapper_resolves_against_real_uvm(real_overrides):
    override = next(
        o for o in real_overrides.overrides
        if o.kind == "type" and o.original == "corpus_driver"
    )
    assert override.replacement == "fast_corpus_driver"


@requires_uvm
def test_the_inst_path_lands_in_the_path_field_against_real_uvm(real_overrides):
    """The assumption most likely to be wrong, checked where it matters.
    `uvm_component::set_inst_override_by_type(path, original, override)` puts
    the path first; the factory's form puts it last. Reading the wrong position
    swaps the path with the original type, and both spellings compile.
    """
    inst = next(o for o in real_overrides.overrides if o.kind == "inst")

    assert inst.inst_path == "env.agt.drv"
    assert inst.original == "corpus_driver"
    assert inst.replacement == "fast_corpus_driver"


@requires_uvm
def test_the_registry_form_finds_tname_through_real_uvm(real_overrides):
    """Real `uvm_component_registry::set_type_override` delegates through
    `uvm_registry_common`, a layer the stub does not have. Whether the
    specialization's `Tname` is still reachable from the called subroutine is a
    fact about the real class hierarchy, and the registry form names its
    original type nowhere else.
    """
    registry = [
        o for o in real_overrides.overrides if o.original == "corpus_monitor"
    ]
    assert registry, "the registry form produced no override"
    # Deliberately not a self-override: `original` and `replacement` come from
    # entirely different places here --- the specialization's `Tname` and an
    # argument --- so a fixture where they are the same string would pass with
    # either one wired to both.
    assert registry[0].replacement == "noisy_corpus_monitor"


@requires_uvm
def test_get_type_still_names_the_users_class_against_real_uvm(real_overrides):
    """`fast_corpus_driver::get_type()` comes from `uvm_component_utils`, so
    which class its lexical path reports is a property of the real macro."""
    assert any(
        o.replacement == "fast_corpus_driver" for o in real_overrides.overrides
    )


@requires_uvm
def test_a_typo_in_a_by_name_override_is_caught_against_real_uvm(real_overrides):
    broken = real_overrides.broken

    assert [o.replacement for o in broken] == ["corpus_scorebaord"]


@requires_uvm
def test_the_library_does_not_report_its_own_overrides(real_overrides):
    """UVM calls these methods on itself. The same library-boundary rule the
    config scan uses keeps that out of a user's document."""
    assert all(
        not o.where.startswith("uvm_") for o in real_overrides.overrides
    )
