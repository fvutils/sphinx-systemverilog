"""Single source of truth for the package version.

BASE is the released version and is what a ``v<BASE>`` tag must match.
SUFFIX is empty in the tree and is stamped by CI on non-tag builds so an
ordinary push can never produce a wheel whose version collides with a
release on PyPI.
"""

BASE = "0.2.0"
SUFFIX = ""

# Read by pyproject.toml's dynamic version.
_pkg_version = BASE + SUFFIX

__version__ = _pkg_version
