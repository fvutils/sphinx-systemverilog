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
sv_source_dirs = [os.path.join(_here, "..", "tests", "fixtures", "sv")]
# "auto" sniffs each comment: NaturalDocs blocks use the ND dialect, everything
# else falls back to native - so both example pages render from one config.
sv_doc_style = "auto"

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
