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

if os.path.isfile(_uvm_pkg) and not os.environ.get("SV_DOCS_NO_UVM"):
    # uvm_pkg.sv `include`s the whole library; the fixture files are parsed as
    # additional build units into the same index.
    sv_build_units = [_uvm_pkg, *_fixture_files]
    sv_include_dirs = [_uvm_src]
    tags.add("have_uvm")  # noqa: F821 (Sphinx injects `tags`)
else:
    sv_source_dirs = [_fixtures]

# -- General ------------------------------------------------------------------
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "design"]
master_doc = "index"

html_theme = "alabaster"
html_static_path = ["_static"]

# Branding (shared icon set lives in ../assets/icons; paths are relative to this
# conf dir and Sphinx copies them into the build).
html_logo = "../assets/icons/png/logo-horizontal.png"
html_favicon = "../assets/icons/favicon.ico"
html_theme_options = {
    "description": "Sphinx autodoc for SystemVerilog, powered by pyslang",
    "github_user": "fvutils",
    "github_repo": "sphinx-systemverilog",
    "github_button": True,
    "logo_name": False,
}

myst_enable_extensions = ["colon_fence", "deflist"]
