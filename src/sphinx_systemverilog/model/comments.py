"""Doc-comment extraction from pyslang token trivia.

These are pure functions operating on a pyslang ``Token`` (and its ``trivia``
list).  They are kept separate from the builder so the fiddly trivia logic can
be unit-tested directly (see ``tests/model/test_comments.py``).

Two behaviours, both validated against pyslang during the design spike:

* **Leading doc** - the contiguous block of ``//`` / ``/* */`` comments
  immediately above a declaration is its documentation.  A blank line (two
  consecutive end-of-line trivia) terminates the block.
* **Trailing same-line comment** - an inline comment such as
  ``rand bit addr; // the address`` is attached by pyslang as the *leading*
  trivia of the *next* token (before that token's first end-of-line).  We split
  it out so the builder can re-assign it to the preceding declaration.
"""

from __future__ import annotations

from typing import Any

from pyslang.parsing import TriviaKind

_COMMENT_KINDS = (TriviaKind.LineComment, TriviaKind.BlockComment)


def _raw(trivia: Any) -> str:
    return trivia.getRawText()


def split_leading_trivia(token: Any) -> tuple[list[str], list[str]]:
    """Split a token's leading trivia into (trailing_prev, leading_doc).

    *trailing_prev* are comment(s) appearing before the first end-of-line, i.e.
    on the same physical line as the previous token - they document the
    *previous* declaration.  *leading_doc* is the contiguous comment block
    immediately preceding *this* token.
    """
    trivia = list(token.trivia)

    # Comments before the first EndOfLine sit on the previous source line.
    trailing_prev: list[str] = []
    idx = 0
    while idx < len(trivia) and trivia[idx].kind != TriviaKind.EndOfLine:
        if trivia[idx].kind in _COMMENT_KINDS:
            trailing_prev.append(_raw(trivia[idx]))
        idx += 1

    leading_doc = _leading_block(trivia[idx:])
    return trailing_prev, leading_doc


def iter_comment_blocks(token: Any) -> list[list[str]]:
    """Split a token's leading trivia into separate comment blocks.

    Unlike :func:`split_leading_trivia` (which returns only the block adjacent to
    the token), this returns *every* comment block in the leading trivia, in
    source order, where a block is a run of comments not broken by a blank line.
    Used to recover detached NaturalDocs documentation blocks.
    """
    blocks: list[list[str]] = []
    cur: list[str] = []
    eol_run = 0
    for tr in token.trivia:
        kind = tr.kind
        if kind in _COMMENT_KINDS:
            if eol_run >= 2 and cur:
                blocks.append(cur)
                cur = []
            cur.append(_raw(tr))
            eol_run = 0
        elif kind == TriviaKind.EndOfLine:
            eol_run += 1
    if cur:
        blocks.append(cur)
    return blocks


def _leading_block(trivia: list[Any]) -> list[str]:
    """Return the contiguous trailing comment block of *trivia*.

    Scans from the end (closest to the token) backwards, collecting comments
    until a blank line (>= 2 consecutive end-of-lines) or a non-comment,
    non-whitespace trivia is hit.
    """
    out: list[str] = []
    eol_run = 0
    started = False
    for tr in reversed(trivia):
        kind = tr.kind
        if kind in _COMMENT_KINDS:
            if started and eol_run >= 2:
                break
            out.append(_raw(tr))
            eol_run = 0
            started = True
        elif kind == TriviaKind.EndOfLine:
            if started:
                eol_run += 1
        elif kind == TriviaKind.Whitespace:
            continue
        else:
            # Directive / skipped tokens / etc. terminate the doc block.
            if started:
                break
    out.reverse()
    return out


def clean_comment_block(lines: list[str]) -> str | None:
    """Normalize raw comment text into plain documentation text.

    Strips comment delimiters (``//``, ``/*``, ``*/``, leading ``*``) and the
    minimum common indentation, preserving relative indentation of the body so
    that embedded reStructuredText survives.
    """
    if not lines:
        return None

    raw_lines: list[str] = []
    for block in lines:
        for line in block.splitlines() or [""]:
            raw_lines.append(line)

    stripped: list[str] = []
    for line in raw_lines:
        s = line.rstrip()
        ls = s.lstrip()
        if ls.startswith("///"):
            ls = ls[3:]
        elif ls.startswith("//!"):
            ls = ls[3:]
        elif ls.startswith("//"):
            ls = ls[2:]
        elif ls.startswith("/**"):
            ls = ls[3:]
        elif ls.startswith("/*"):
            ls = ls[2:]
        elif ls.startswith("*/"):
            ls = ls[2:]
        elif ls.startswith("*"):
            ls = ls[1:]
        if ls.endswith("*/"):
            ls = ls[:-2]
        # Drop a single leading space introduced by the delimiter (// foo).
        if ls.startswith(" "):
            ls = ls[1:]
        stripped.append(ls.rstrip())

    # Trim leading/trailing blank lines.
    while stripped and not stripped[0].strip():
        stripped.pop(0)
    while stripped and not stripped[-1].strip():
        stripped.pop()

    if not stripped:
        return None
    return "\n".join(stripped)
