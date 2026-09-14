"""``autosvmodule`` accepts the three instantiable entity kinds.

SystemVerilog spells a hardware entity `module`, `interface` or `program`
depending on what it needs; all three have ports and parameters and are
instantiated the same way, and the documentation points at this one directive
for all of them.  Warning that an interface "is not a module" told a user to
change their source to suit the doc tool.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.autodoc.directives import (
    AutoSvClassDirective,
    AutoSvModuleDirective,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", ["module", "interface", "program"])
def test_module_directive_accepts_instantiable_kinds(kind):
    accepted = (AutoSvModuleDirective.object_kind, *AutoSvModuleDirective.also_accepts)
    assert kind in accepted


def test_module_directive_still_rejects_a_class():
    accepted = (AutoSvModuleDirective.object_kind, *AutoSvModuleDirective.also_accepts)
    assert "class" not in accepted


def test_other_directives_are_unchanged():
    assert AutoSvClassDirective.also_accepts == ()
