"""M1-IMPL-12: the structure config values warn on bad input, never raise.

A bad ``conf.py`` value should cost the user a warning and a sane default, not a
traceback in the middle of a documentation build.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.config import validate_config

pytestmark = pytest.mark.unit


#: (config name, default, a value meaning "no limit" or None if there is none)
SETTINGS = [
    ("sv_structure_max_instances", 20000, None),
    ("sv_instance_tree_depth", 3, None),
    ("sv_used_by_limit", 50, 0),        # 0 disables the cap
]


class _Config:
    """Minimal stand-in for Sphinx's config object."""

    def __init__(self, **overrides):
        self.sv_doc_style = "native"
        for name, default, _ in SETTINGS:
            setattr(self, name, default)
        for name, value in overrides.items():
            setattr(self, name, value)


@pytest.mark.parametrize("name,default,_zero", SETTINGS)
@pytest.mark.parametrize("bad", [-1, "many", None, True, 2.5])
def test_bad_values_fall_back(name, default, _zero, bad):
    config = _Config(**{name: bad})

    validate_config(None, config)

    assert getattr(config, name) == default


@pytest.mark.parametrize("name,default,_zero", SETTINGS)
def test_zero_is_rejected_unless_it_means_no_limit(name, default, _zero):
    config = _Config(**{name: 0})

    validate_config(None, config)

    expected = 0 if _zero == 0 else default
    assert getattr(config, name) == expected


@pytest.mark.parametrize("name,default,_zero", SETTINGS)
@pytest.mark.parametrize("good", [1, 7, 500])
def test_valid_values_are_left_alone(name, default, _zero, good):
    config = _Config(**{name: good})

    validate_config(None, config)

    assert getattr(config, name) == good
