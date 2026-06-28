"""Autodoc layer: auto* directives and the SvObject -> RST documenter."""

from __future__ import annotations

from .directives import AUTODOC_DIRECTIVES
from .documenters import SvDocumenter

__all__ = ["AUTODOC_DIRECTIVES", "SvDocumenter"]
