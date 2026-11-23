"""D2-TEST-1: compare two doctree dumps (see ``pytest_runtest_teardown`` in
``tests/conftest.py``), made by two versions of the code.

    git stash; SVDB_DOCTREE_DUMP=/tmp/a pytest -m sphinx; git stash pop
    SVDB_DOCTREE_DUMP=/tmp/b pytest -m sphinx
    python -m tests.frontend.doctree_equivalence /tmp/a /tmp/b

Doctrees are compared as ``pformat()`` text and warnings as text, both with
pytest's temporary directories normalized.  Exit status 1 lists every test
whose output differs.
"""

from __future__ import annotations

import difflib
import pickle
import re
import sys
from pathlib import Path

_TMP = re.compile(r"/tmp/pytest-of-[^/\s]+/pytest-\d+")
_ESC = re.compile(r"\x1b\[[0-9;]*m")


def _norm(text: str) -> str:
    return _TMP.sub("<TMP>", _ESC.sub("", text))


def _load(path: Path) -> str:
    with open(path, "rb") as f:
        return _norm(pickle.load(f).pformat())


def compare(a: Path, b: Path) -> list[str]:
    problems = []
    tests = sorted({p.name for p in a.iterdir()} | {p.name for p in b.iterdir()})
    for t in tests:
        ta, tb = a / t, b / t
        if not ta.is_dir() or not tb.is_dir():
            problems.append(f"{t}: only in {'A' if ta.is_dir() else 'B'}")
            continue
        names = sorted({p.name for p in ta.iterdir()} | {p.name for p in tb.iterdir()})
        for n in names:
            fa, fb = ta / n, tb / n
            if not fa.exists() or not fb.exists():
                problems.append(f"{t}/{n}: only in {'A' if fa.exists() else 'B'}")
                continue
            if n.endswith(".doctree"):
                xa, xb = _load(fa), _load(fb)
            else:
                xa, xb = _norm(fa.read_text()), _norm(fb.read_text())
            if xa != xb:
                diff = "".join(list(difflib.unified_diff(
                    xa.splitlines(True), xb.splitlines(True), "A", "B", n=1))[:40])
                problems.append(f"{t}/{n} differs:\n{diff}")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    a, b = Path(argv[0]), Path(argv[1])
    problems = compare(a, b)
    for p in problems:
        print(p)
    n = len({p.name for p in a.iterdir()})
    print(f"{n} test(s) compared, {len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
