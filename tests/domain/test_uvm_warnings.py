"""U1-TEST-9: the directive degrades with an actionable warning, never a crash.

A documentation build fails for reasons that have nothing to do with the page
being built --- a missing generated package, a stale environment, a testbench
that has not been written yet. None of those should produce a traceback, and
none should produce silence either: a directive that renders nothing and says
nothing is indistinguishable from a directive that worked.

Every warning here has to name what to do about it, because the reader of a
build log is usually not the author of the page.
"""

from __future__ import annotations

import pytest

from tests.conftest import UVM_STUB, UVM_TB

pytestmark = pytest.mark.sphinx

WITH_TB = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "basic_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

#: No sources at all, so no compilation is retained and no provider is
#: attached. This is the same branch an *unpickled* index takes: Sphinx cannot
#: pickle a pyslang `Compilation`, so a re-read page sees exactly this state.
NO_SOURCES: dict = {"sv_source_dirs": []}


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-none", confoverrides=NO_SOURCES
)
def test_no_testbench_warns_and_says_what_to_do(app, warning):
    app.build()
    text = warning.getvalue()

    assert "not available in this process" in text
    assert "sphinx-build -E" in text, "the warning must name the remedy"


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-none", confoverrides=NO_SOURCES
)
def test_a_degraded_build_still_succeeds(app):
    """A missing testbench must not take the rest of the documentation down."""
    app.build()

    assert (app.outdir / "index.html").exists()


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-none", confoverrides=NO_SOURCES
)
def test_optional_suppresses_the_warning(app, warning):
    """`:optional:` is how a page says "render this if it exists"."""
    app.build()

    assert "also_absent" not in warning.getvalue()


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-unknown", confoverrides=WITH_TB
)
def test_an_unknown_root_names_the_component_it_could_not_find(app, warning):
    app.build()
    text = warning.getvalue()

    assert "definitely_not_a_test" in text
    assert "cannot find UVM component" in text


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-unknown", confoverrides=WITH_TB
)
def test_an_optional_unknown_root_is_silent(app, warning):
    app.build()

    assert "also_absent" not in warning.getvalue()


@pytest.mark.sphinx(
    "html", testroot="uvm-warn", srcdir="uvm-warn-typed", confoverrides=WITH_TB
)
def test_warnings_are_typed_so_they_can_be_suppressed(app, warning):
    """Consistent with the rest of the extension: `suppress_warnings`."""
    app.build()

    assert "systemverilog" in warning.getvalue()


# -- config_db orphans (U2-IMPL-5) --------------------------------------------
#
# Two paths, and the default one matters more than the opt-in one. Installing
# this extension must never turn a green build red over a testbench smell the
# reader did not ask about; the finding is always rendered in the page, and
# escalating it to a build warning is a decision a project takes for itself.

WITH_CONFIG = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "config_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}


@pytest.mark.sphinx(
    "html", testroot="uvm-orphan-warn", srcdir="uvm-orphan-quiet",
    confoverrides=WITH_CONFIG,
)
def test_orphans_do_not_warn_by_default(app, warning):
    app.build()
    text = warning.getvalue()

    assert "n_itmes" not in text
    # ...but the finding is still on the page. Silence in the log is not
    # silence in the document.
    assert "n_itmes" in (app.outdir / "index.html").read_text()


@pytest.mark.sphinx(
    "html", testroot="uvm-orphan-warn", srcdir="uvm-orphan-loud",
    confoverrides={**WITH_CONFIG, "sv_uvm_warn_orphans": True},
)
def test_orphans_warn_when_asked_to(app, warning):
    app.build()
    text = warning.getvalue()

    assert "n_itmes" in text
    assert "typo" in text, "the warning must say what the finding usually means"
    assert "systemverilog" in text


@pytest.mark.sphinx(
    "html", testroot="uvm-orphan-warn", srcdir="uvm-orphan-unset",
    confoverrides={**WITH_CONFIG, "sv_uvm_warn_orphans": True},
)
def test_an_unset_field_warns_too(app, warning):
    """The other direction: a component reading a knob nothing provides.

    Its own `srcdir`: a shared one means a cached doctree, the directive never
    re-runs, and no warning is ever emitted for the second test to see.
    """
    app.build()
    text = warning.getvalue()

    assert "unset_depth" in text
    assert "default will always be used" in text
