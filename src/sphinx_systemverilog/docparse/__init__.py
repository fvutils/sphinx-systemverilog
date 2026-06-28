"""Doc-comment parsing: dialect registry and implementations."""

from __future__ import annotations

from .base import (
    DocField,
    DocstringParser,
    ParsedDoc,
    get_parser,
    get_parser_for,
    register_parser,
)

# Import implementations so they self-register.  Order matters for ``auto``
# sniffing: more specific dialects are tried before native (the fallback).
from . import naturaldocs  # noqa: F401
from . import doxygen  # noqa: F401
from . import native  # noqa: F401

__all__ = [
    "DocField",
    "DocstringParser",
    "ParsedDoc",
    "get_parser",
    "get_parser_for",
    "register_parser",
]
