"""Tests for the autosvsummary whole-tree directive (P3-TEST-3)."""

from __future__ import annotations

import pytest
from sphinx import addnodes

from tests.conftest import FIXTURES

CONF = {"sv_source_dirs": [str(FIXTURES)], "sv_doc_style": "auto"}

pytestmark = pytest.mark.sphinx


def _names(doctree):
    return [
        "".join(n.astext() for n in s.findall(addnodes.desc_name))
        for s in doctree.findall(addnodes.desc_signature)
    ]


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_documents_classes_in_scope(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    # :kinds: class :packages: nd_pkg -> the three nd_pkg classes, with members.
    assert {"nd_base", "nd_mid", "nd_leaf"} <= set(names)
    assert "get_name" in names  # members included by default


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_scope_excludes_other_packages(app):
    app.build()
    names = _names(app.env.get_doctree("index"))
    # sample_pkg / dox_pkg classes are out of the nd_pkg scope.
    assert "sample_txn" not in names
    assert "dox_txn" not in names


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_files_selects_by_source_path(app):
    # A bare pattern matches a path suffix, so the same directive works against
    # whatever absolute path the sources happen to sit at.
    app.build()
    names = _names(app.env.get_doctree("files"))
    assert "sample_txn" in names
    assert "nd_base" not in names


@pytest.mark.sphinx("html", testroot="summary", confoverrides=CONF)
def test_summary_files_pattern_spans_directories(app):
    from sphinx_systemverilog.autodoc.directives import _matches_files
    from sphinx_systemverilog.model.objects import SourceRef, SvObject

    obj = SvObject(
        kind="class", name="uvm_reg",
        location=SourceRef(file="/opt/uvm/src/reg/uvm_reg.svh", line=1),
    )
    assert _matches_files(obj, ["reg/uvm_reg.svh"])          # suffix
    assert _matches_files(obj, ["reg/*.svh"])                # glob in a dir
    assert _matches_files(obj, ["uvm_*.svh"])                # basename only
    assert _matches_files(obj, ["**/reg/*.svh"])             # '**' crosses dirs
    assert _matches_files(obj, ["/opt/uvm/src/reg/*"])       # anchored
    assert not _matches_files(obj, ["/other/*"])             # anchored, no match
    assert not _matches_files(obj, ["base/*.svh"])           # wrong directory
    assert not _matches_files(obj, ["/opt/*.svh"])           # '*' stops at '/'
    # The bug this replaced: a directory glob must not reach into a subdirectory,
    # or a class lands on two pages at once.
    nested = SvObject(
        kind="class", name="uvm_reg_access_seq",
        location=SourceRef(file="/opt/uvm/src/reg/sequences/uvm_reg_access_seq.svh", line=1),
    )
    assert not _matches_files(nested, ["reg/*.svh"])
    assert _matches_files(nested, ["reg/sequences/*.svh"])
    # No location at all must not match, rather than raising.
    assert not _matches_files(SvObject(kind="class", name="x"), ["*"])
