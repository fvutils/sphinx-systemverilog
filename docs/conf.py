"""Sphinx configuration for the sphinx-systemverilog documentation.

This doc set *dogfoods* the extension: it documents the SystemVerilog fixtures
under ``tests/fixtures/sv`` using the very directives the project provides.
"""

from __future__ import annotations

import os

project = "sphinx-systemverilog"
author = "Matthew Ballance"
copyright = "2026, Matthew Ballance"

extensions = [
    "myst_parser",
    "sphinx_rtd_theme",
    "sphinx_systemverilog",
]

# -- sphinx-systemverilog -----------------------------------------------------
_here = os.path.dirname(__file__)
_fixtures = os.path.abspath(os.path.join(_here, "..", "tests", "fixtures", "sv"))
# "auto" sniffs each comment: NaturalDocs blocks use the ND dialect, everything
# else falls back to native - so all example pages render from one config.
sv_doc_style = "auto"

# When the UVM sources are present (fetched by ivpm into ../packages/uvm), build
# them into the index alongside the fixtures and publish a live UVM reference.
# When absent (e.g. a plain `pip install` CI run), fall back to fixtures only and
# the UVM page renders as a guide.  The ``have_uvm`` tag gates the live content.
_uvm_src = os.path.abspath(os.path.join(_here, "..", "packages", "uvm", "src"))
_uvm_pkg = os.path.join(_uvm_src, "uvm_pkg.sv")
_fixture_files = [
    os.path.join(_fixtures, f)
    for f in sorted(os.listdir(_fixtures))
    if f.endswith((".sv", ".svh"))
]

# The structural-documentation example page needs a design with a real
# hierarchy: generate loops, an instance array, and one module elaborated at two
# different widths.  That is exactly the M1 test fixture, so the example page
# renders from the same source the tests assert against.
_designs = [
    os.path.abspath(os.path.join(_here, "..", "tests", "fixtures", d))
    for d in ("design", "design_collapse")
]
_design_files = [
    os.path.join(d, f)
    for d in _designs
    for f in sorted(os.listdir(d))
    if f.endswith((".sv", ".svh"))
]

# The UVM testbench example renders from the mini-UVM stub rather than the real
# library, so the page is live in *both* builds -- a reader on the pip-installed
# docs sees a real extracted tree, not a description of one.
#
# Listed file-by-file rather than by directory on purpose: `tests/fixtures/uvm_tb`
# also holds `missing_dep_tb.sv`, which imports a package that deliberately does
# not exist, and `real_uvm_tb.sv`, which needs the real library. Both are correct
# as test fixtures and both would put errors in this build.
_uvm_stub = os.path.abspath(
    os.path.join(_here, "..", "tests", "fixtures", "uvm_stub")
)
_uvm_tb = os.path.abspath(os.path.join(_here, "..", "tests", "fixtures", "uvm_tb"))
_tb_files = [
    os.path.join(_uvm_stub, "mini_uvm.sv"),
    os.path.join(_uvm_tb, "basic_tb.sv"),
    os.path.join(_uvm_tb, "blackbox_tb.sv"),
    os.path.join(_uvm_tb, "config_tb.sv"),
    os.path.join(_uvm_tb, "tlm_tb.sv"),
    os.path.join(_uvm_tb, "seq_tb.sv"),
    os.path.join(_uvm_tb, "bridge_tb.sv"),
    os.path.join(_uvm_tb, "override_tb.sv"),
]

# Demonstrates glob black-boxing on the example page: `acme_vip_agent` stands
# for vendor VIP delivered as a precompiled library.  The base-class default
# (`uvm_reg_block`) needs no configuration and covers the register model.
#
# The example page names its root explicitly on every directive, because this
# fixture set holds two testbenches; without one the tree would pick a default
# and say so, which is correct behaviour but reads as indecision in an example.
sv_uvm_blackbox = ["acme_vip_*"]

if os.path.isfile(_uvm_pkg) and not os.environ.get("SV_DOCS_NO_UVM"):
    # uvm_pkg.sv `include`s the whole library; the fixture files are parsed as
    # additional build units into the same index.
    sv_build_units = [_uvm_pkg, *_fixture_files, *_design_files, *_tb_files]
    sv_include_dirs = [_uvm_src, _uvm_stub]
    tags.add("have_uvm")  # noqa: F821 (Sphinx injects `tags`)
else:
    sv_build_units = [*_fixture_files, *_design_files, *_tb_files]
    sv_include_dirs = [_uvm_stub]

# -- General ------------------------------------------------------------------
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "design"]
master_doc = "index"

# sphinx_rtd_theme rather than alabaster: the persistent left-hand navigation is
# what makes a 15-page generated reference usable, and it is what pyhdl-if -- the
# other project publishing SystemVerilog docs through this extension -- uses, so
# the two doc sets read as one family.
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Branding (shared icon set lives in ../assets/icons; paths are relative to this
# conf dir and Sphinx copies them into the build).  The rtd sidebar is narrow and
# dark, so it gets the dark-background horizontal logo rather than the light one.
html_logo = "../assets/icons/png/logo-horizontal-dark.png"
html_favicon = "../assets/icons/favicon.ico"
html_theme_options = {
    "logo_only": True,
    "collapse_navigation": False,   # keep the UVM sub-pages reachable in one click
    "navigation_depth": 2,
    "style_external_links": True,
}

myst_enable_extensions = ["colon_fence", "deflist"]

# Pygments' SystemVerilog lexer cannot tokenize a compiler-directive backtick in
# every position UVM uses one, so highlighting a whole UVM source file in the
# viewcode pages falls back to relaxed mode. That is a Pygments limitation, not
# a content problem, and it must not stand between this build and -W.
suppress_warnings = ["misc.highlighting_failure"]
