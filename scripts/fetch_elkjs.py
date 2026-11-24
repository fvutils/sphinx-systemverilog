#!/usr/bin/env python3
"""Put elkjs's ``elk.bundled.js`` and its licence into the package source tree.

The block-diagram layout runs elkjs (Eclipse Layout Kernel, compiled to
JavaScript) inside mini-racer.  elkjs is not on PyPI and is never committed
here; it ships inside the wheel and sdist instead.  This script places the two
files at ``src/sphinx_systemverilog/diagram/js/`` (git-ignored), where
``[tool.setuptools.package-data]`` picks them up.

Two ways in:

``--from DIR``
    Copy from an unpacked npm tarball.  The ``ivpm.yaml`` post-update hook
    uses this with ``packages/elkjs``.
(no arguments)
    Download the pinned tarball from the npm registry, check its integrity
    hash, and unpack the two files.  The CI jobs that build without ivpm use
    this.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import shutil
import sys
import tarfile
import urllib.request

VERSION = "0.12.1"
URL = f"https://registry.npmjs.org/elkjs/-/elkjs-{VERSION}.tgz"
# The registry's ``dist.integrity`` for this version.
INTEGRITY = ("sha512-IhMYKHE4S2vtx0QrhBP3lYOIKDeIiJXBrdq9MGYkuB8ZHqhrBnHNfSUndjXFewrX1"
             "CPK8chwq+2NA0K0hliYuw==")
FILES = ("lib/elk.bundled.js", "LICENSE.md")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "src", "sphinx_systemverilog", "diagram", "js")


def _write_version() -> None:
    with open(os.path.join(DEST, "VERSION"), "w") as f:
        f.write(VERSION + "\n")


def copy_from(src: str) -> None:
    os.makedirs(DEST, exist_ok=True)
    for rel in FILES:
        shutil.copyfile(os.path.join(src, rel), os.path.join(DEST, os.path.basename(rel)))
    _write_version()


def download() -> None:
    with urllib.request.urlopen(URL, timeout=60) as r:
        data = r.read()
    algo, want = INTEGRITY.split("-", 1)
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != want:
        sys.exit(f"fetch_elkjs: integrity mismatch for {URL}")
    os.makedirs(DEST, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for rel in FILES:
            member = tf.extractfile(f"package/{rel}")
            with open(os.path.join(DEST, os.path.basename(rel)), "wb") as f:
                f.write(member.read())
    _write_version()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", metavar="DIR",
                    help="copy from an unpacked elkjs npm package instead of downloading")
    args = ap.parse_args(argv)
    if args.src:
        copy_from(args.src)
    else:
        download()
    print(f"elkjs {VERSION} -> {os.path.relpath(DEST, ROOT)}")


if __name__ == "__main__":
    main()
