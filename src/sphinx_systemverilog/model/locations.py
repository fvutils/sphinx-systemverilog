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


#: Ceiling on the expansion climb.  A macro that expands to itself is a
#: preprocessor error slang reports on its own; a documentation build must not
#: hang deciding whether to print a member.
_MAX_EXPANSION_DEPTH = 32


def macro_chain(source_manager: Any, location: Any) -> tuple[str, ...]:
    """Names of the macro expansions *location* sits inside, innermost first.

    The last element is the macro as written in the source, which is the only
    name a user could reasonably put in a config list: the innermost name for a
    ``\\`uvm_component_utils`` member is ``m_uvm_component_registry_internal``.
    Returns ``()`` for a hand-written location.
    """
    if location is None:
        return ()
    names: list[str] = []
    try:
        for _ in range(_MAX_EXPANSION_DEPTH):
            if not source_manager.isMacroLoc(location):
                break
            name = source_manager.getMacroName(location)
            if name:
                names.append(str(name))
            location = source_manager.getExpansionLoc(location)
    except Exception:
        return tuple(names)
    return tuple(names)


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
