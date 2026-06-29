"""Tests for the :optional: flag and :doc-style: precedence (Phase-2 gap fix)."""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_systemverilog.autodoc.documenters import SvDocumenter
from sphinx_systemverilog.model.objects import SvObject, SourceRef
from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)], "sv_doc_style": "auto"}

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="optional", confoverrides=CONF)
def test_optional_missing_target_no_warning(app, warning):
    app.build()
    # The missing optional class must not warn, while the real one still renders.
    assert "not_a_real_class" not in warning.getvalue()
    names = {
        "".join(n.astext() for n in s.findall(addnodes.desc_name))
        for s in app.env.get_doctree("index").findall(addnodes.desc_signature)
    }
    assert "sample_txn" in names


@pytest.mark.unit
def test_directive_doc_style_overrides_object_style():
    # An object built under "auto" must still render via the directive's
    # explicit :doc-style: (regression: object style used to win).
    obj = SvObject(
        kind="function", name="f", signature="function void f()",
        raw_doc="Matches a *.txt pattern.", doc_style="auto",
        location=SourceRef("f.sv", 1),
    )

    class _App:
        def emit_firstresult(self, *a, **k):
            return None

        def emit(self, *a, **k):
            return []

    doc = SvDocumenter(_App(), {}, default_style="naturaldocs")
    rendered = "\n".join(doc.render(obj))
    # naturaldocs escapes the stray '*'; native would have left it raw.
    assert "\\*" in rendered
