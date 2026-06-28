"""sphinx-systemverilog: a Sphinx autodoc extension for SystemVerilog.

Powered by the pyslang parser.  See ``docs/design/`` for architecture.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.0.1"


def _build_index(app: Any) -> None:
    """Build the project-wide source index once per Sphinx build.

    Connected to ``builder-inited`` so the index is available before any
    directive runs, and stored on the build environment.
    """
    from sphinx.util import logging
    from .model.index import build_index

    logger = logging.getLogger(__name__)
    config = app.config
    index = build_index(
        source_dirs=config.sv_source_dirs,
        build_units=config.sv_build_units,
        doc_style=config.sv_doc_style,
        include_dirs=config.sv_include_dirs,
        defines=config.sv_defines,
        base_path=app.confdir,
        nodocs_policy=config.sv_naturaldocs_nodocs,
    )
    app.env.sv_index = index
    logger.info(
        "sphinx-systemverilog: indexed %d SystemVerilog object(s)", len(index)
    )
    for diag in index.diagnostics:
        if diag and diag.strip():
            logger.warning(
                "sphinx-systemverilog (parser): %s",
                diag.strip(), type="systemverilog",
            )
    if index.suppressed_count:
        logger.info(
            "sphinx-systemverilog: suppressed %d non-error parser diagnostic(s)",
            index.suppressed_count,
        )


def setup(app: Any) -> dict[str, Any]:
    from .autodoc import AUTODOC_DIRECTIVES
    from .autodoc.diagrams import SvInheritanceDiagram
    from .config import register_config, validate_config
    from .domain import SystemVerilogDomain

    # Inheritance diagrams render through the graphviz extension.
    app.setup_extension("sphinx.ext.graphviz")

    register_config(app)
    app.add_domain(SystemVerilogDomain)
    app.add_directive_to_domain("sv", "inheritance-diagram", SvInheritanceDiagram)

    for name, directive in AUTODOC_DIRECTIVES.items():
        app.add_directive(name, directive)

    # Events mirroring sphinx.ext.autodoc's extension points.
    app.add_event("sv-autodoc-process-doc")
    app.add_event("sv-autodoc-skip-member")

    app.connect("config-inited", validate_config)
    app.connect("builder-inited", _build_index)

    # viewcode: resolve [source] links and generate highlighted listings.
    from . import viewcode

    app.connect("doctree-resolved", viewcode.resolve_links)
    app.connect("html-collect-pages", viewcode.collect_pages)
    app.connect("env-purge-doc", viewcode.purge)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
