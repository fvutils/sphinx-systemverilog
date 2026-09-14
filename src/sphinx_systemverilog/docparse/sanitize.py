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


def strip_rules(text: str) -> str:
    """Drop banner-rule lines, leaving the surrounding blank-line structure."""
    return "\n".join(
        line for line in text.splitlines() if not _RULE_RE.match(line)
    )


def unwrap_continuations(text: str) -> str:
    """Fold over-indented lines into the line above, block by block.

    Blocks are separated by blank lines.  Within a block, indents are taken
    relative to the block's own minimum, and a line indented past the start of
    the current logical line continues it -- unless it opens a list item, which
    always starts a new logical line.  List runs are then dedented to their
    lead-in and blank-line separated so docutils sees a list.
    """
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        out.extend(_render_block(block))
        block.clear()

    for line in text.splitlines():
        if line.strip():
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
