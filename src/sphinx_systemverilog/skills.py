"""Agent-skill discovery hook.

Registered via the ``agent.skills`` entry-point group so that any environment
with sphinx-systemverilog installed exposes the bundled authoring skill to
IVPM's agents handler, which links it into ``.agents/skills/``,
``.claude/skills/`` and ``.cursor/skills/``.

This module is loaded by a bare ``importlib.metadata`` sweep running in the
managed venv, with no Sphinx application anywhere and possibly mid-install.  It
therefore imports nothing beyond the standard library: an exception raised here
surfaces to the user as an ``ivpm update`` warning about a broken entry-point,
not as a documentation problem.
"""

from __future__ import annotations

import os
from typing import List

#: Directory name under ``share/skills`` holding the bundled skill.  Must match
#: the ``name:`` in its SKILL.md frontmatter and the entry-point name declared
#: in pyproject.toml, because the agents handler names the installed skill from
#: the entry point and the host reads the name from the frontmatter.
SKILL_NAME = "sphinx-systemverilog"


def get_skill_dirs() -> List[str]:
    """Return directories containing bundled agent ``SKILL.md`` files.

    Referenced by the ``agent.skills`` entry-point in pyproject.toml.  Computed
    from ``__file__`` rather than hard-coded, so it is correct under an editable
    install as well as from a wheel.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(here, "share", "skills", SKILL_NAME)]
