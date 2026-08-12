#!/usr/bin/env python3
"""Fail if a documented SystemVerilog class never reached the built HTML.

The UVM reference splits 288 classes across pages by source path.  Nothing in
Sphinx notices when a class falls between two of those patterns -- the build
succeeds and the class is simply absent -- so this compares what the extension
parsed against what the build actually published, via ``objects.inv``.

    ./scripts/check-docs-coverage.py [--html docs/_build/html] [--uvm packages/uvm/src]

Exits 0 when every documented class is present (or when the UVM sources are
absent, which is a legitimate fixtures-only build), 1 when any is missing.
"""

from __future__ import annotations

import argparse
import os
import sys


def parsed_classes(uvm_src: str) -> set[str]:
    from sphinx_systemverilog.model.index import build_index

    index = build_index(
        source_dirs=[],
        build_units=[os.path.join(uvm_src, "uvm_pkg.sv")],
        doc_style="auto",
        include_dirs=[uvm_src],
        defines=[],
        base_path=os.getcwd(),
        nodocs_policy=None,
        document_macros=False,
    )
    return {
        obj.qualified_name or obj.name
        for root in index.roots
        for obj in root.walk()
        if obj.kind == "class" and obj.is_documented
    }


def published_classes(html_dir: str) -> set[str]:
    from sphinx.util.inventory import InventoryFile

    with open(os.path.join(html_dir, "objects.inv"), "rb") as f:
        inv = InventoryFile.load(f, "", lambda base, target: target)
    return set(inv.get("sv:class", {}))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="docs/_build/html")
    ap.add_argument("--uvm", default="packages/uvm/src")
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.uvm, "uvm_pkg.sv")):
        print(f"no UVM sources at {args.uvm}; nothing to check")
        return 0

    parsed = parsed_classes(args.uvm)
    published = published_classes(args.html)
    missing = sorted(parsed - published)

    print(f"parsed {len(parsed)} documented classes, published {len(published)}")
    if missing:
        print(f"ERROR: {len(missing)} documented class(es) reached no page:")
        for name in missing:
            print(f"  {name}")
        print("Add the file they live in to a :files: pattern under docs/uvm/.")
        return 1
    print("OK: every documented class is published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
