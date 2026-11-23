"""Import NDJSON into an ``.svdb`` file.

The NDJSON is read one line at a time and handed to a :class:`Writer`, so
memory does not grow with the input.  Blank lines are skipped; a line that is
not JSON is an error.
"""

from __future__ import annotations

import json
import os
from typing import IO, Iterable, Iterator

from .issues import Issue, SvdbError
from .writer import Writer


def read_ndjson(lines: Iterable[str], name: str = "<input>") -> Iterator[tuple[dict, str]]:
    """Parse NDJSON *lines*, yielding ``(record, "name:line")``."""
    for n, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise SvdbError(f"{name}:{n}: not JSON: {e.msg}") from None
        if not isinstance(rec, dict):
            raise SvdbError(f"{name}:{n}: a record must be a JSON object")
        yield rec, f"{name}:{n}"


def import_stream(src: IO[str] | Iterable[str], dst: str | os.PathLike, *, name: str = "<input>",
                  strict: bool = True) -> Writer:
    """Import NDJSON from *src* into *dst* (a path or ``":memory:"``).

    Returns the finished :class:`Writer`; its ``issues`` hold the warnings
    and, when not *strict*, the errors.  For ``":memory:"`` its ``conn`` is
    the database.
    """
    w = Writer(dst, strict=strict)
    try:
        for rec, where in read_ndjson(src, name):
            w.add(rec, where)
    except BaseException:
        w.abort()
        raise
    w.finish()
    return w


def import_file(src: str | os.PathLike, dst: str | os.PathLike, *, strict: bool = True) -> list[Issue]:
    """Import the NDJSON file *src* into the database file *dst*."""
    with open(src, encoding="utf-8") as f:
        return import_stream(f, dst, name=os.fspath(src), strict=strict).issues
