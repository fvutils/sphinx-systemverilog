"""sphinx-systemverilog: a Sphinx autodoc extension for SystemVerilog.

Powered by the pyslang parser.  See ``docs/design/`` for architecture.
"""

from __future__ import annotations

from typing import Any

from .__version__ import __version__

__all__ = ["__version__", "UVM_BOILERPLATE_MACROS", "setup"]


def __getattr__(name: str) -> Any:
    """Lazily re-export :data:`~.model.uvm.UVM_BOILERPLATE_MACROS`.

    So a ``conf.py`` can extend the shipped default rather than restate it::

        sv_ignore_macro_content = [*UVM_BOILERPLATE_MACROS, "my_reg_field_decl"]

    Resolved on attribute access, not at import: every other import in this
    module is deferred into :func:`setup` so that importing the package does not
    drag in pyslang, and a convenience constant is not worth giving that up.
    """
    if name == "UVM_BOILERPLATE_MACROS":
        from .model.uvm import UVM_BOILERPLATE_MACROS

        return UVM_BOILERPLATE_MACROS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _build_index(app: Any) -> None:
    """Build the project-wide source index once per Sphinx build.

    Connected to ``builder-inited`` so the index is available before any
    directive runs, and stored on the build environment.  The index reads a
    database that the front end writes into ``<doctreedir>/svdb/`` and reuses
    while the sources are unchanged; ``sv_databases`` are read after it.
    """
    import os

    from sphinx.util import logging

    logger = logging.getLogger(__name__)
    config = app.config
    kwargs = dict(
        source_dirs=config.sv_source_dirs,
        build_units=config.sv_build_units,
        doc_style=config.sv_doc_style,
        include_dirs=config.sv_include_dirs,
        defines=config.sv_defines,
        base_path=app.confdir,
        nodocs_policy=config.sv_naturaldocs_nodocs,
        document_macros=config.sv_document_macros,
        structure_tops=config.sv_structure_tops,
        structure_max_instances=config.sv_structure_max_instances,
        uvm_root=config.sv_uvm_root,
        uvm_blackbox=config.sv_uvm_blackbox,
        uvm_blackbox_bases=config.sv_uvm_blackbox_bases,
        uvm_max_components=config.sv_uvm_max_components,
        external=config.sv_external,
        external_sources=config.sv_external_sources,
        # The sources link against every listed database that does not opt out.
        links=[d["path"] for d in config.sv_databases if d.get("link", True)],
    )
    from .frontend.build import Options, open_index
    from .svdb.issues import SvdbError

    def resolve(path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(app.confdir, path)

    databases = [resolve(d["path"]) for d in config.sv_databases if d["role"] == "local"]
    # A linked database feeds the UVM stitcher whatever its role: the
    # testbench's database no longer describes the classes it linked.
    stitch = [resolve(d["path"]) for d in config.sv_databases
              if d["role"] == "external" and d.get("link", True)]
    # ``role: external`` databases are not documented here: they only give
    # link targets (linkout.py).
    from .linkout import open_external

    open_external(app)
    cache_dir = os.path.join(app.doctreedir, "svdb") if config.sv_db_cache else None
    try:
        index = open_index(
            Options.make(**kwargs), cache_dir=cache_dir, databases=databases,
            stitch_databases=stitch, default_doc_style=config.sv_doc_style,
        )
    except SvdbError as e:
        from sphinx.errors import ConfigError

        raise ConfigError(f"sphinx-systemverilog: {e}") from None
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
    from .autodoc.diagrams import SvInheritanceDiagram, SvInstanceDiagram
    from .autodoc.structure import STRUCTURE_DIRECTIVES
    from .autodoc.uvm import UVM_DIRECTIVES
    from .config import register_config, validate_config
    from .domain import SystemVerilogDomain

    # Inheritance diagrams render through the graphviz extension.
    app.setup_extension("sphinx.ext.graphviz")

    register_config(app)
    app.add_domain(SystemVerilogDomain)
    app.add_directive_to_domain("sv", "inheritance-diagram", SvInheritanceDiagram)
    app.add_directive_to_domain("sv", "instance-diagram", SvInstanceDiagram)
    for name, directive in STRUCTURE_DIRECTIVES.items():
        app.add_directive_to_domain("sv", name, directive)
    for name, directive in UVM_DIRECTIVES.items():
        app.add_directive_to_domain("sv", name, directive)

    for name, directive in AUTODOC_DIRECTIVES.items():
        app.add_directive(name, directive)

    # Events mirroring sphinx.ext.autodoc's extension points.
    app.add_event("sv-autodoc-process-doc")
    app.add_event("sv-autodoc-skip-member")

    app.connect("config-inited", validate_config)
    app.connect("builder-inited", _build_index)

    # Link-out for names documented elsewhere, after intersphinx (plan §6.4).
    from . import linkout

    app.connect("missing-reference", linkout.missing_reference,
                priority=linkout.PRIORITY)

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
