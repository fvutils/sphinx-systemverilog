"""Extension load / registration smoke tests (P0-TEST-2)."""

from __future__ import annotations

import pytest

import sphinx_systemverilog

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="basic")
def test_extension_loads(app):
    assert "sphinx_systemverilog" in app.extensions


@pytest.mark.sphinx("html", testroot="basic")
def test_domain_registered(app):
    assert "sv" in app.env.domains


@pytest.mark.sphinx("html", testroot="basic")
def test_config_values_registered(app):
    for name in (
        "sv_source_dirs",
        "sv_include_dirs",
        "sv_defines",
        "sv_build_units",
        "sv_doc_style",
        "sv_default_options",
        "sv_structure_tops",
        "sv_structure_max_instances",
        "sv_instance_tree_depth",
        "sv_used_by_limit",
        "sv_uvm_blackbox",
        "sv_uvm_blackbox_bases",
        "sv_uvm_root",
        "sv_uvm_tree_depth",
        "sv_uvm_max_components",
    ):
        assert hasattr(app.config, name)


@pytest.mark.sphinx("html", testroot="basic")
def test_uvm_blackbox_bases_defaults_to_the_register_model(app):
    """A register model is the thing most likely to be absent at doc time.

    It is commonly generated from RDL or IP-XACT as a build step, so a doc build
    that runs before -- or without -- that step must still produce an honest
    tree rather than a silently shortened one.
    """
    assert app.config.sv_uvm_blackbox_bases == ["uvm_reg_block"]


@pytest.mark.sphinx("html", testroot="basic")
def test_structure_directives_registered(app):
    domain = app.env.domains["sv"]

    for name in ("instance-tree", "used-by", "parameter-matrix"):
        assert name in domain.directives


@pytest.mark.sphinx("html", testroot="basic")
def test_auto_directives_registered(app):
    from docutils.parsers.rst import directives as rst_directives

    for name in ("autosvclass", "autosvpackage", "autosvmodule"):
        assert rst_directives._directives.get(name) is not None


def test_setup_returns_metadata():
    meta_keys = {"version", "parallel_read_safe", "parallel_write_safe"}

    class _App:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def _rec(*a, **k):
                self.calls.append((name, a))
            return _rec

    app = _App()
    meta = sphinx_systemverilog.setup(app)
    assert meta_keys <= set(meta)
    assert meta["version"] == sphinx_systemverilog.__version__
