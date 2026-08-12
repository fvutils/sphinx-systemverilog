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
    Because the rule is *relative*, list items -- which sit at the same indent
    as each other -- survive as separate items, with their own wrapped lines
    folded in.

Both are applied by the dialects whose sources are not RST (NaturalDocs,
Doxygen, plain).  The native dialect is left alone: there the comment body is
RST by definition, and its indentation is meaningful.
"""

from __future__ import annotations

import re

#: A line consisting only of rule characters, e.g. ``-----`` or ``* * * *``.
_RULE_RE = re.compile(r"""^\s*['"<>|^\-=*+~_#/](?:\s*['"<>|^\-=*+~_#/]){2,}\s*$""")


def strip_rules(text: str) -> str:
    """Drop banner-rule lines, leaving the surrounding blank-line structure."""
    return "\n".join(
        line for line in text.splitlines() if not _RULE_RE.match(line)
    )


def unwrap_continuations(text: str) -> str:
    """Fold over-indented lines into the line above, block by block.

    Blocks are separated by blank lines.  Within a block, the first line sets
    the reference indent; any later line indented past it is a continuation of
    what came before, not a new construct.
    """
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        indents = [len(ln) - len(ln.lstrip()) for ln in block]
        base = min(indents)
        first_indent = indents[0] - base
        rendered: list[str] = [block[0].strip()]
        for line, indent in zip(block[1:], indents[1:]):
            if indent - base > first_indent and rendered:
                rendered[-1] = rendered[-1].rstrip() + " " + line.strip()
            else:
                rendered.append(line.strip())
        out.extend(rendered)
        block.clear()

    for line in text.splitlines():
        if line.strip():
            block.append(line)
        else:
            flush()
            out.append("")
    flush()
    return "\n".join(out)


def sanitize_prose(text: str) -> str:
    """Both repairs, in the order the dialects want them."""
    return unwrap_continuations(strip_rules(text))
