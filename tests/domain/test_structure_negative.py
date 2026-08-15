"""M2-TEST-6: what the structural directives do when there is nothing to say.

The distinction these tests pin down: a target the index has never heard of is
an authoring error and warns. A target that exists but has nothing structural to
report is *not* an error --- a module that instantiates nothing, or that nothing
instantiates, is a perfectly ordinary module, and saying so in prose is more
useful than either a warning or silence.
"""

from __future__ import annotations

import pytest

from tests.conftest import DESIGN

pytestmark = pytest.mark.sphinx

CONF = {"sv_source_dirs": [str(DESIGN)]}


@pytest.mark.sphinx("html", testroot="structure-bad", confoverrides=CONF)
def test_optional_is_silent_for_every_directive(app, warning):
    app.build()

    assert warning.getvalue().strip() == ""


@pytest.mark.sphinx("html", testroot="structure-bad", confoverrides=CONF)
def test_optional_renders_nothing_for_unknown_targets(app):
    app.build()
    text = app.env.get_doctree("index").astext()

    assert "no_such_module" not in text
    # ``:optional:`` also suppresses the informational notes.
    assert "documented sources" not in text


@pytest.mark.sphinx("html", testroot="structure-warn", confoverrides=CONF)
def test_unknown_target_warns_without_optional(app, warning):
    app.build()
    messages = warning.getvalue()

    assert "cannot find SystemVerilog object" in messages
    assert "no_such_module" in messages


@pytest.mark.sphinx("html", testroot="structure", confoverrides=CONF)
def test_existing_but_empty_targets_do_not_warn(app, warning):
    """``leaf`` instantiates nothing and ``soc`` is instantiated by nothing."""
    app.build()

    assert warning.getvalue().strip() == ""
    text = app.env.get_doctree("index").astext()
    assert "Instantiates nothing within the documented sources." in text
    assert "Not instantiated within the documented sources." in text
