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
    ):
        assert hasattr(app.config, name)


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
