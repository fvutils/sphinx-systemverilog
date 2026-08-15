"""Sphinx configuration for the CVA6 example build.

This documents a real, large SystemVerilog design -- OpenHW Group's CVA6
RISC-V core -- rather than a fixture.  It is deliberately **not** part of the
published doc set: it needs a ~100 MB checkout, and its purpose is validation
and demonstration, not distribution.

    make fetch && make html

See ``README.md`` for what to look at and why.
"""

from __future__ import annotations

import os
import sys

_here = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, _here)

from flist import read_filelist                      # noqa: E402  (needs sys.path)

# -- Locate CVA6 --------------------------------------------------------------
# CVA6_ROOT lets a developer point at an existing checkout instead of the one
# `make fetch` creates.
CVA6 = os.environ.get("CVA6_ROOT") or os.path.join(_here, "_cva6")

# Which core configuration to elaborate.  CVA6 ships ten mutually exclusive
# `*_config_pkg.sv` files; the filelist selects one via ${TARGET_CFG}, which is
# exactly why a directory glob cannot work here.
TARGET_CFG = os.environ.get("TARGET_CFG", "cv64a6_imafdc_sv39")

_flist = os.path.join(CVA6, "core", "Flist.cva6")
have_cva6 = os.path.isfile(_flist)

project = "CVA6 — documented by sphinx-systemverilog"
author = "sphinx-systemverilog"
extensions = ["sphinx_systemverilog", "myst_parser"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
master_doc = "index"
exclude_patterns = ["_build", "_cva6", "README.md"]

html_theme = "sphinx_rtd_theme"
html_title = "CVA6 structural documentation"

if have_cva6:
    files, include_dirs, defines, skipped = read_filelist(
        _flist,
        variables={
            "CVA6_REPO_DIR": CVA6,
            "TARGET_CFG": TARGET_CFG,
            # Two vendored submodules are not present in a shallow clone.  The
            # filelist reader skips what it cannot find, and the count is
            # reported below so the gap is visible rather than mysterious.
            "HPDCACHE_DIR": os.path.join(CVA6, "core", "cache_subsystem", "hpdcache"),
        },
    )
    sv_build_units = files
    sv_include_dirs = include_dirs
    sv_defines = defines
    sv_doc_style = "native"

    # CVA6 elaborates a handful of unused vendor utilities as their own tops;
    # naming the real top keeps the structural views about the design.
    sv_structure_tops = ["cva6"]

    tags.add("have_cva6")                    # noqa: F821  (Sphinx injects `tags`)
    print(
        f"[cva6 example] {TARGET_CFG}: {len(files)} files, "
        f"{len(include_dirs)} include dirs, {len(skipped)} entries skipped"
    )
else:
    print(
        "[cva6 example] CVA6 sources not found at "
        f"{CVA6}\n"
        "[cva6 example] run `make fetch` (or set CVA6_ROOT); "
        "building the guide page only."
    )
