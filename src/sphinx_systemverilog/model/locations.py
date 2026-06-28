"""Source-location helpers.

pyslang reports symbol positions as ``SourceLocation`` values that must be
resolved through a ``SourceManager`` to obtain a file name / line / column.
Compiler-synthesized symbols (e.g. the ``randomize`` method injected into every
class) carry out-of-range locations; :func:`is_real_location` filters them.
"""

from __future__ import annotations

from typing import Any

from .objects import SourceRef


def is_real_location(source_manager: Any, location: Any) -> bool:
    """Return ``True`` if *location* maps into an actual source buffer.

    Synthesized symbols carry bogus, out-of-range buffer offsets (observed as
    huge integer values).  The reliable test is that the source manager can
    resolve a non-empty file name and a positive line number.
    """
    if location is None:
        return False
    try:
        file_name = source_manager.getFileName(location)
        line = source_manager.getLineNumber(location)
    except Exception:
        return False
    return bool(file_name) and line > 0


def resolve_location(source_manager: Any, location: Any) -> SourceRef | None:
    """Resolve a pyslang ``SourceLocation`` to a :class:`SourceRef`.

    Returns ``None`` for missing or synthesized locations.
    """
    if not is_real_location(source_manager, location):
        return None
    try:
        file_name = source_manager.getFileName(location)
        line = source_manager.getLineNumber(location)
        column = source_manager.getColumnNumber(location)
    except Exception:
        return None
    return SourceRef(file=str(file_name), line=int(line), column=int(column))
