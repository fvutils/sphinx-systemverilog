"""Structural repairs for doc text that was never authored as reStructuredText.

The dialect parsers handle *inline* markup; these functions handle the two
structural constructs that turn a perfectly ordinary source comment into invalid
RST once it is nested inside a directive body:

``strip_rules``
    Banner rules (``//----------``, ``// ****``) separate sections in a source
    file.  Nested in a directive they parse as a transition, which docutils
    rejects ("Document or section may not begin with a transition"), and they
    carry no information once the comment has become a documentation block.

``unwrap_continuations``
    Prose that aligns continuation lines under a term ::

        UVM_PRE_START  - The sequence is started and the
                         pre_start() task is being executed.

    reads as a definition list or a block quote to docutils, and then fails
    ("Definition list ends without a blank line", "Unexpected indentation").
    Joining each over-indented line onto the line above keeps the words, the
    order and any cross-reference roles, and loses only the column alignment.

    Folding is *marker-aware*: a line that opens with a bullet (``*``, ``-``,
    ``+``) or a simple enumerator (``1.``, ``a)``) starts a new logical line
    rather than continuing the one above, even when it is indented past it.
    That is the common banner-comment shape -- a lead-in ending in ``:``
    followed by bullets indented a couple of spaces -- and an indent-relative
    rule alone would fold the whole list into its lead-in.

    Recognised list runs are then dedented to their lead-in (so docutils sees
    a list, not a block quote wrapping one) and surrounded by the blank lines
    docutils requires to recognise a list at all, including between items that
    enter or leave a nesting level.

Both are applied by the dialects whose sources are not RST (NaturalDocs,
Doxygen, plain).  The native dialect is left alone: there the comment body is
RST by definition, and its indentation is meaningful.

``literal_line_mask``
    The exception to both.  A doc comment may still contain one construct whose
    indentation *is* meaningful -- an RST literal block, introduced by ``::`` --
    and the repairs above would destroy it: the folder reads the indented code
    as continuation lines and joins them, and the dedent leaves docutils with no
    indented block to find ("Literal block expected; none found").  The mask
    marks those lines so every pass leaves them exactly as typed.
"""

from __future__ import annotations

import re

#: A line consisting only of rule characters, e.g. ``-----`` or ``* * * *``.
_RULE_RE = re.compile(r"""^\s*['"<>|^\-=*+~_#/](?:\s*['"<>|^\-=*+~_#/]){2,}\s*$""")

#: A line opening a list item: leading space, a bullet or simple enumerator,
#: then whitespace and at least one non-space character.  Requiring the
#: ``\s+\S`` tail is what keeps ``*ptr = 5`` and a bare ``-`` out, and
#: anchoring the marker at the start of the line is what keeps a
#: ``TERM  - description`` line -- whose continuations must still fold -- out.
#: Shared with :mod:`.inline` so the escaper and the folder cannot drift.
_LIST_ITEM_RE = re.compile(
    r"^([ \t]*)((?:[*+\-]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]))([ \t]+)(?=\S)"
)


def match_list_item(line: str) -> "re.Match[str] | None":
    """Return the match for a leading list marker, or ``None``."""
    return _LIST_ITEM_RE.match(line)


def is_list_item(line: str) -> bool:
    """True if ``line`` opens a bullet or enumerated list item."""
    return _LIST_ITEM_RE.match(line) is not None


def opens_literal_block(line: str) -> bool:
    """True if ``line`` ends a paragraph with the RST literal-block marker."""
    return line.rstrip().endswith("::")


def literal_line_mask(text: str) -> list[bool]:
    """Mark the lines of *text* that belong to an RST literal block.

    A line ending in ``::`` opens one; every following line indented past it
    belongs to it, including the blank lines between its paragraphs.  The block
    ends at the first line indented back to the opener's column or further left,
    and that line is itself tested for opening the next one.

    The mask is what lets the repairs below -- and the inline escaper -- leave a
    code sample exactly as its author typed it.  Everything they do to prose is
    wrong for code: folding its continuation lines destroys the indentation that
    makes it a block, dedenting it stops docutils recognising it at all, and
    escaping ``*`` or a trailing ``_`` puts backslashes into the rendered
    listing.
    """
    lines = text.split("\n")
    mask = [False] * len(lines)
    opener: int | None = None
    blanks: list[int] = []
    for idx, line in enumerate(lines):
        if not line.strip():
            # Deferred: a blank belongs to the block only if the block resumes.
            if opener is not None:
                blanks.append(idx)
            continue
        indent = len(line) - len(line.lstrip())
        if opener is not None and indent > opener:
            for blank in blanks:
                mask[blank] = True
            mask[idx] = True
            blanks.clear()
            continue
        blanks.clear()
        opener = indent if opens_literal_block(line) else None
    return mask


def reintroduce_literal_block(summary: list[str], body: list[str]) -> list[str]:
    """Re-open a literal block that summary extraction left orphaned.

    The dialects take a comment's first paragraph as the summary and render it
    apart from the body.  When that paragraph is the one ending in ``::``, the
    indented block it introduced is now the first thing in the body with nothing
    above it -- docutils reads it as a block quote and warns about unexpected
    indentation.  Putting RST's bare ``::`` marker back at the head of the body
    restores the block; the marker itself renders as nothing.
    """
    if not body or not summary:
        return body
    if not opens_literal_block(summary[-1]):
        return body
    first = next((ln for ln in body if ln.strip()), "")
    if not first.startswith((" ", "\t")):
        return body
    return ["::", ""] + body


def strip_rules(text: str) -> str:
    """Drop banner-rule lines, leaving the surrounding blank-line structure.

    Lines inside a literal block are kept: ``// ------`` in a code sample is
    part of the sample.
    """
    literal = literal_line_mask(text)
    return "\n".join(
        line
        for line, is_literal in zip(text.split("\n"), literal)
        if is_literal or not _RULE_RE.match(line)
    )


def unwrap_continuations(text: str) -> str:
    """Fold over-indented lines into the line above, block by block.

    Blocks are separated by blank lines.  Within a block, indents are taken
    relative to the block's own minimum, and a line indented past the start of
    the current logical line continues it -- unless it opens a list item, which
    always starts a new logical line.  List runs are then dedented to their
    lead-in and blank-line separated so docutils sees a list.

    Literal blocks are exempt and pass through verbatim; see
    :func:`literal_line_mask`.
    """
    out: list[str] = []
    block: list[str] = []
    literal = literal_line_mask(text)

    def flush() -> None:
        if not block:
            return
        out.extend(_render_block(block))
        block.clear()

    for line, is_literal in zip(text.split("\n"), literal):
        if is_literal:
            # Verbatim, and at its original indentation: both are what make it
            # a literal block to docutils.
            flush()
            out.append(line)
        elif line.strip():
            block.append(line)
        else:
            flush()
            out.append("")
    flush()
    return "\n".join(out)


def _render_block(block: list[str]) -> list[str]:
    """Fold, dedent and blank-line-separate one blank-line-delimited block."""
    indents = [len(ln) - len(ln.lstrip()) for ln in block]
    base = min(indents)

    # 1. Fold continuations into logical lines of (relative indent, text, is-item).
    logical: list[list] = []
    cur_indent = 0
    for line, raw_indent in zip(block, indents):
        indent = raw_indent - base
        item = is_list_item(line)
        if not logical:
            logical.append([indent, line.strip(), item])
            cur_indent = indent
        elif item or indent <= cur_indent:
            logical.append([indent, line.strip(), item])
            cur_indent = indent
        else:
            logical[-1][1] = logical[-1][1].rstrip() + " " + line.strip()

    # 2. Shift each maximal run of list items left to sit under its lead-in.
    idx = 0
    while idx < len(logical):
        if not logical[idx][2]:
            idx += 1
            continue
        start = idx
        while idx < len(logical) and logical[idx][2]:
            idx += 1
        run = logical[start:idx]
        run_min = min(entry[0] for entry in run)
        prev_indent = logical[start - 1][0] if start else 0
        shift = run_min - prev_indent
        if shift:
            for entry in run:
                entry[0] -= shift

    # 3. Emit, inserting the blank lines docutils needs around and inside lists.
    rendered: list[str] = []
    for pos, (indent, body, item) in enumerate(logical):
        if rendered:
            prev_indent, _, prev_item = logical[pos - 1]
            if item != prev_item or (item and indent != prev_indent):
                rendered.append("")
        rendered.append(" " * max(indent, 0) + body)
    return rendered


def sanitize_prose(text: str) -> str:
    """Both repairs, in the order the dialects want them."""
    return unwrap_continuations(strip_rules(text))
