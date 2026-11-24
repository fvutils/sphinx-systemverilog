"""Block diagrams laid out by ELK.

Front ends build a :class:`Diagram`; :func:`to_elk` converts it to ELK JSON;
:func:`layout` positions it with elkjs.  See
``docs/design/block-diagram-layout.md`` for the design.
"""
from .elk import to_elk
from .engine import LayoutError, get_engine, layout, unavailable_reason
from .model import Box, Bundle, Diagram, Edge, Port

__all__ = [
    "Box", "Bundle", "Diagram", "Edge", "Port",
    "to_elk", "layout", "get_engine", "unavailable_reason", "LayoutError",
]
