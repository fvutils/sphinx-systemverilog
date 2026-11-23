"""``sv:uvm-tree :resolved:`` (stitching plan D1).

The tree a run would build: instances named from ``uvm_test_top``, the type
the factory builds after overrides, shown as ``declared → built``. The as-written
tree beside it keeps the declared types and annotates the overrides.
"""

from __future__ import annotations

import re

import pytest

from tests.conftest import UVM_STUB, UVM_TB

CONF = {
    "sv_source_dirs": [str(UVM_STUB)],
    "sv_build_units": [
        str(UVM_STUB / "mini_uvm.sv"),
        str(UVM_TB / "stitch_tb.sv"),
    ],
    "sv_include_dirs": [str(UVM_STUB)],
}

pytestmark = pytest.mark.sphinx


def _section(page: str, title: str) -> str:
    """The text of the section titled *title*, tags stripped."""
    start = page.index(title)
    end = page.find("<h2", start)
    return re.sub(r"<[^>]+>", "", page[start:end if end > 0 else None]).replace("&gt;", ">")


@pytest.fixture
def page(app):
    app.build()
    return (app.outdir / "index.html").read_text()


def _sphinx(fn):
    return pytest.mark.sphinx("html", testroot="uvm-tree-resolved", srcdir="uvm-tree-resolved",
                              confoverrides=CONF)(fn)


@_sphinx
def test_the_root_is_named_as_uvm_names_it(page):
    assert "uvm_test_top : st_test" in _section(page, "Resolved")


@_sphinx
def test_overrides_are_applied_per_instance(page):
    text = _section(page, "Resolved")
    agt_b = text[text.index("agt_b : st_agent"):text.index("scb")]
    # a type override everywhere; an inst override on agt_b only
    assert re.search(r"drv\s+: st_drv → fast_drv\s+\[conditional\]", agt_b)
    assert re.search(r"mon\s+: st_mon → mon_x", agt_b)
    agt_a = text[text.index("agt_a : st_agent"):text.index("agt_b : st_agent")]
    assert re.search(r"drv\s+: st_drv → slow_drv", agt_a)
    assert re.search(r"mon\s+: st_mon → mon_c", agt_a)
    assert re.search(r"scb\s+: st_scb → big_scb", text)


@_sphinx
def test_the_declared_and_built_types_are_both_cross_referenced(page):
    block = page[page.index("sv-uvm-resolved"):]
    block = block[:block.index("</pre>")]
    # Cross-references to undocumented classes render as their sv-type literal.
    sv_type = r'<code class="sv-type[^"]*"><span class="pre">{}</span></code>'
    assert re.search(sv_type.format("st_drv") + " → " + sv_type.format("fast_drv"), block)


@_sphinx
def test_issues_and_the_resolved_scope_note_are_shown(page):
    text = _section(page, "Resolved")
    assert "override_ignored" in text and "unplaced_override" in text
    assert "with factory overrides applied as the IEEE 1800.2 factory applies them" in text
    assert "built as a different type than their create call names" in text


@_sphinx
def test_the_written_tree_is_unchanged(page):
    text = _section(page, "As written")
    assert "[overridden → " in text and "st_drv → " not in text
    assert not re.search(r"^uvm_test_top :", text, re.M)


@_sphinx
def test_depth_elides_and_says_so(page):
    text = _section(page, "Shallow")
    assert re.search(r"└── env\s+: sup_env", text) and "agt_a" not in text
    assert re.search(r"deeper level\(s\) containing \d+ component\(s\) not shown", text)
