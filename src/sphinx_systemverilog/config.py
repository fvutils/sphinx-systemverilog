"""Configuration values for the sphinx-systemverilog extension.

All ``sv_*`` configuration values are registered here via :func:`register_config`,
which is called from :func:`sphinx_systemverilog.setup`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx


#: Valid values for ``sv_doc_style``.
DOC_STYLES = ("native", "naturaldocs", "doxygen", "auto")


def register_config(app: "Sphinx") -> None:
    """Register all ``sv_*`` configuration values on the Sphinx application."""
    # Directories scanned to build the project-wide source index.
    app.add_config_value("sv_source_dirs", [], "env", types=[list])
    # Additional include directories passed to the pyslang preprocessor.
    app.add_config_value("sv_include_dirs", [], "env", types=[list])
    # Preprocessor ``define`` values (name -> value) for elaboration.
    app.add_config_value("sv_defines", {}, "env", types=[dict])
    # Explicit "build unit" roots to elaborate (e.g. ["uvm_pkg.sv"]).
    app.add_config_value("sv_build_units", [], "env", types=[list])
    # Default doc-comment dialect: one of DOC_STYLES.
    app.add_config_value("sv_doc_style", "native", "env", types=[str])
    # How to treat UVM ``-- NODOCS --`` blocks: "include" the prose or "skip".
    app.add_config_value("sv_naturaldocs_nodocs", "include", "env", types=[str])
    # Default options applied to every auto* directive (e.g. {"members": True}).
    app.add_config_value("sv_default_options", {}, "env", types=[dict])
    # Generate '[source]' links to highlighted SystemVerilog source.
    app.add_config_value("sv_viewcode", True, "env", types=[bool])
    # Extract and document `\`define` macros.
    app.add_config_value("sv_document_macros", True, "env", types=[bool])


def validate_config(app: "Sphinx", config) -> None:
    """Validate ``sv_*`` config values; emit a warning for bad input.

    Connected to the ``config-inited`` event.
    """
    from sphinx.util import logging

    logger = logging.getLogger(__name__)
    if config.sv_doc_style not in DOC_STYLES:
        logger.warning(
            "sv_doc_style %r is not one of %s; falling back to 'native'",
            config.sv_doc_style,
            ", ".join(DOC_STYLES),
            type="systemverilog",
        )
        config.sv_doc_style = "native"
