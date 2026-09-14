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

    When *token* is the **first token in its file** there is no previous line,
    so a comment before the first end-of-line cannot be a trailing comment - it
    is the opening line of this token's own leading block.  Skipping that case
    matters more than it sounds: almost every real HDL file opens with a license
    header on line 1, and attributing that line to a non-existent previous
    declaration leaked "Copyright 2018 ..." into the file's first declaration.
    """
    trivia = list(token.trivia)

    # Comments before the first EndOfLine sit on the previous source line -
    # unless there is no previous line at all.
    starts_file = _starts_buffer(token, trivia)
    trailing_prev: list[str] = []
    idx = 0
    while idx < len(trivia) and trivia[idx].kind != TriviaKind.EndOfLine:
        kind = trivia[idx].kind
        if kind in _COMMENT_KINDS:
            if not starts_file:
                trailing_prev.append(_raw(trivia[idx]))
        elif kind != TriviaKind.Whitespace:
            # A preprocessor directive intervenes, so this is not the previous
            # token's line: after include expansion the text here belongs to
            # the included file, not to any declaration in this one.
            trailing_prev = []
            break
        idx += 1

    leading_doc = _leading_block(trivia if starts_file else trivia[idx:])
    return trailing_prev, leading_doc


def _starts_buffer(token: Any, trivia: list) -> bool:
    """True when nothing but *trivia* precedes *token* in its source buffer.

    The token's offset is the count of characters before it, so if the trivia
    accounts for all of them, this is the first token in the file.
    """
    try:
        offset = token.location.offset
    except Exception:
        return False
    return offset == sum(len(_raw(t)) for t in trivia)


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
    """Return the comment block documenting the token *trivia* precedes.

    Normally this is the contiguous block closest to the token.  When the
    trivia contain preprocessor directives the picture is less simple: after
    include expansion the text sitting immediately above a declaration can be
    the *tail of an included file*, which is not documentation for anything
    here.  CVA6's top-level module is the case in point -- it is preceded by two
    ``\\`include`` lines, and the nearest comment is an include guard's closing
    ``// CVXIF_TYPES_SVH``.

    So when directives are present and the nearest block is not immediately
    adjacent, fall back to the trivia *before the first directive*: nothing has
    been included at that point, so those comments are certainly from this file.
    """
    block = _contiguous_block(trivia)
    first_directive = _first_directive_index(trivia)
    if first_directive is not None and block and not _is_adjacent(trivia):
        return _contiguous_block(trivia[:first_directive])
    return block


def _first_directive_index(trivia: list[Any]) -> int | None:
    for index, tr in enumerate(trivia):
        if tr.kind not in _COMMENT_KINDS and tr.kind not in (
            TriviaKind.EndOfLine, TriviaKind.Whitespace
        ):
            return index
    return None


def _is_adjacent(trivia: list[Any]) -> bool:
    """True when no blank line separates the nearest comment from the token."""
    end_of_lines = 0
    for tr in reversed(trivia):
        if tr.kind == TriviaKind.EndOfLine:
            end_of_lines += 1
        elif tr.kind == TriviaKind.Whitespace:
            continue
        else:
            break
    return end_of_lines <= 1


def _contiguous_block(trivia: list[Any]) -> list[str]:
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
            # Directive / skipped tokens / etc. terminate the doc block --
            # including when nothing has been collected yet.  After include
            # expansion the trivia adjacent to a declaration can be the *tail of
            # the included file*, so scanning past a directive attributed a
            # header guard's closing comment to the module below it (CVA6's
            # top-level module was documented as "CVXIF_TYPES_SVH").
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

    stripped = strip_license_preamble(stripped)

    # Trim leading/trailing blank lines.
    while stripped and not stripped[0].strip():
        stripped.pop(0)
    while stripped and not stripped[-1].strip():
        stripped.pop()

    if not stripped:
        return None
    return "\n".join(stripped)


#: Phrases that only appear in a license notice.  A run containing at least one
#: of these is a license; without one, nothing is stripped.
_LICENSE_STRONG = (
    "spdx-license-identifier",
    "licensed under",
    "license, version",
    "you may not use this file",
    "you may obtain a copy",
    "without warranties",
    "either express or implied",
    "specific language governing permissions",
    "limitations under the license",
    "compliance with the license",
    "or agreed to in writing",
    "this license is distributed",
    "conditions of any kind",
    "solderpad.org",
    "apache.org/licenses",
    "opensource.org/licenses",
    "gnu.org/licenses",
)

#: Phrases that belong to a license *when adjacent to* a strong marker, but that
#: also occur in ordinary prose ("checks the copyright field").  Treating these
#: as sufficient on their own silently deleted real documentation.
_LICENSE_WEAK = (
    "copyright",
    "all rights reserved",
    "distributed under",
    "the \"license\"",
)


def _license_line_kind(line: str) -> str:
    """``"strong"``, ``"weak"``, ``"blank"`` or ``""`` (not a license line)."""
    text = line.strip().lower()
    if not text:
        return "blank"
    if any(marker in text for marker in _LICENSE_STRONG):
        return "strong"
    if any(marker in text for marker in _LICENSE_WEAK):
        return "weak"
    return ""


def strip_license_preamble(lines: list[str]) -> list[str]:
    """Drop a leading run of license-notice lines from a comment block.

    Nearly every real HDL file opens with a license header, and it is routinely
    written as one contiguous comment block with the module's actual
    description - so without this, a module's documentation reads "Copyright
    2018 ETH Zurich ..." instead of "Ariane Instruction Fetch Frontend".

    Only a run at the **start** of the block is removed, and only when that run
    contains an unambiguous license phrase.  A one-line description such as
    "Checks the Copyright field of a header" is prose and is kept: a false
    positive here silently deletes real documentation, which is a worse failure
    than leaving a stray license line in place.

    If the whole block is a license the result is empty, which correctly means
    "this declaration is undocumented" rather than "documented by its license".
    """
    index = 0
    saw_strong = False
    while index < len(lines):
        kind = _license_line_kind(lines[index])
        if not kind:
            break
        if kind == "strong":
            saw_strong = True
        index += 1

    if index == 0 or not saw_strong:
        return lines
    return lines[index:]


def doc_above_line(text: str, line: int) -> list[str]:
    """The comment block ending on the line above 1-based *line* in *text*.

    A fallback for a declaration whose keyword arrived through a macro.  When
    source reads::

        `define ENTITY_TYPE interface
        /** What this interface is for. */
        `ENTITY_TYPE my_fifo #(...) (...);

    the preprocessor consumes the comment along with the macro usage, and the
    ``interface`` token the parser sees carries only ``Directive`` trivia -- so
    the trivia route finds nothing to attach.  The declaration's *name* is still
    at a real source line, which is enough to go back to the text and read what
    the author wrote above it.

    Scanning text is a last resort, not the normal path: it cannot tell a
    comment from an identical string literal, and it does not know about
    conditional compilation.  It runs only when the trivia route came back
    empty, so neither risk applies to a declaration the parser saw intact.
    """
    lines = text.split("\n")
    idx = line - 2                      # 0-based index of the preceding line
    if idx < 0 or idx >= len(lines):
        return []

    stripped = lines[idx].strip()
    if stripped.endswith("*/"):
        block: list[str] = []
        while idx >= 0:
            block.insert(0, lines[idx])
            if "/*" in lines[idx]:
                return block
            idx -= 1
        return []                       # unterminated: not a comment block

    block = []
    while idx >= 0 and lines[idx].strip().startswith("//"):
        block.insert(0, lines[idx])
        idx -= 1
    return block
