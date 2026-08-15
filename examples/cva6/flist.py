"""Minimal reader for Verilog ``.f`` filelists, for the CVA6 example build.

**This file is a workaround, and its existence is the point.**  sphinx-systemverilog
cannot currently be pointed at a ``.f`` filelist -- it takes a directory to glob
(``sv_source_dirs``) or an explicit list of files (``sv_build_units``) -- and every
real SystemVerilog project is organized around filelists.  So documenting CVA6
requires re-implementing, badly, something the design already describes.

Globbing the directory instead is not an option: CVA6 ships ten mutually
exclusive ``*_config_pkg.sv`` files, one per target configuration, and parsing
all of them silently yields a *degraded* hierarchy (55 instances instead of 337)
with no warning that anything is wrong.

``docs/design/cva6-informed-enhancements.md`` §3 (`E1`) replaces this whole file
with a ``sv_filelists`` config value backed by ``pyslang.driver.Driver`` -- which
is slang's own filelist reader, and therefore handles the long tail of syntax
this does not.  When `E1` lands, delete this module.

Supported here, because CVA6 needs it: ``//`` comments, ``${VAR}`` expansion,
``-f``/``-F`` recursion, ``+incdir+``, ``+define+``.  Missing files are skipped
with a note rather than failing, since a filelist routinely names sources from
submodules a shallow clone did not fetch.
"""

from __future__ import annotations

import os
import re

_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _expand(text: str, variables: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return variables.get(name, os.environ.get(name, match.group(0)))

    return _VAR.sub(repl, text)


def read_filelist(
    path: str, variables: dict[str, str] | None = None
) -> tuple[list[str], list[str], dict[str, str], list[str]]:
    """Read *path*, returning ``(files, include_dirs, defines, skipped)``.

    Paths are absolute and de-duplicated, preserving filelist order (which
    matters for packages that must be compiled before their users).
    """
    variables = dict(variables or {})
    files: list[str] = []
    include_dirs: list[str] = []
    defines: dict[str, str] = {}
    skipped: list[str] = []
    seen: set[str] = set()

    def visit(flist: str) -> None:
        try:
            with open(flist, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            skipped.append(flist)
            return

        base = os.path.dirname(os.path.abspath(flist))
        for raw in lines:
            line = _expand(raw.split("//")[0].strip(), variables)
            if not line:
                continue
            if "${" in line or line.startswith("$"):
                # An unresolved variable would produce a nonsense path; skipping
                # is honest, and the caller reports what was skipped.
                skipped.append(line)
                continue

            if line.startswith("+incdir+"):
                for part in line[len("+incdir+"):].split("+"):
                    if part:
                        include_dirs.append(_abs(part, base).rstrip("/"))
            elif line.startswith("+define+"):
                for part in line[len("+define+"):].split("+"):
                    if not part:
                        continue
                    name, _, value = part.partition("=")
                    defines[name] = value or "1"
            elif line.startswith(("-f", "-F")):
                nested = line.split(None, 1)
                if len(nested) == 2:
                    visit(_abs(nested[1], base))
            elif line.startswith(("+", "-")):
                continue                      # a simulator option we do not need
            else:
                resolved = _abs(line, base)
                if resolved in seen:
                    continue
                seen.add(resolved)
                if os.path.isfile(resolved):
                    files.append(resolved)
                else:
                    skipped.append(resolved)

    visit(os.path.abspath(path))
    return files, _dedupe(include_dirs), defines, skipped


def _abs(path: str, base: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out
