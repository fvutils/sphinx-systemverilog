"""``autosvsummary`` applies the macro filter to what it selects, not only to members.

A project's own type-registration macro can emit an entire class. Filtering only
members left those classes on the page -- eleven identical wrappers in the case
this was found in -- while hiding the members that would have explained them.
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

ROOT = "macro-classes"
SOURCES = {"sv_source_dirs": ["."]}
FILTERED = {**SOURCES, "sv_ignore_macro_content": ["gen_wrapper_utils"]}


def _documented(app) -> set[str]:
    app.build()
    doctree = app.env.get_doctree("index")
    return {
        sig["sv_fullname"]
        for sig in doctree.findall(addnodes.desc_signature)
        if sig.get("sv_kind") == "class"
    }


@pytest.mark.sphinx("html", testroot=ROOT, confoverrides=SOURCES)
def test_macro_generated_classes_show_by_default(app):
    """No ignore list configured: nothing is filtered."""
    names = _documented(app)
    assert "gen_pkg::alpha_w" in names, names
    assert "gen_pkg::beta_w" in names, names


@pytest.mark.sphinx("html", testroot=ROOT, confoverrides=FILTERED)
def test_matching_macro_generated_classes_are_filtered(app):
    names = _documented(app)
    assert "gen_pkg::alpha_w" not in names, names
    assert "gen_pkg::beta_w" not in names, names


@pytest.mark.sphinx("html", testroot=ROOT, confoverrides=FILTERED)
def test_hand_written_classes_are_untouched(app):
    """The filter keys on provenance, so authored code is never at risk."""
    assert "gen_pkg::gen_real" in _documented(app)
