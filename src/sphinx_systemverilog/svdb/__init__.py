"""svdb: a database of SystemVerilog design and testbench information.

The interchange contract is the JSON Schema in ``schema/svdb-1.schema.json``
(see ``docs/design/svdb-schema-plan.md``).  This package must not import
Sphinx or pyslang, so that it can be used -- and later distributed -- on its
own.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

#: MAJOR.MINOR of the interchange schema this package reads and writes.
SCHEMA_VERSION = "1.1"


def schema_text() -> str:
    """The normative JSON Schema, as text."""
    return resources.files(__name__).joinpath("schema", "svdb-1.schema.json").read_text("utf-8")


@lru_cache(maxsize=1)
def schema() -> dict:
    """The normative JSON Schema, parsed."""
    return json.loads(schema_text())


@lru_cache(maxsize=1)
def uvm_tree_schema() -> dict:
    """The JSON Schema of :meth:`UvmTree.to_json` output (``svdb-uvm-tree``)."""
    text = resources.files(__name__).joinpath("schema", "svdb-uvm-tree-1.schema.json").read_text("utf-8")
    return json.loads(text)


def example_names() -> list[str]:
    """Names of the bundled example files (``schema/examples/*.ndjson``)."""
    root = resources.files(__name__).joinpath("schema", "examples")
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".ndjson"))


def example_text(name: str) -> str:
    """The text of one bundled example file."""
    return resources.files(__name__).joinpath("schema", "examples", name).read_text("utf-8")


from .database import AmbiguousKey, Database, Object, TreeNode, Unresolved  # noqa: E402
from .uvm_tree import UvmLink, UvmNode, UvmTree  # noqa: E402
from .exporter import export_file  # noqa: E402
from .importer import import_file  # noqa: E402
from .issues import Issue, SvdbError  # noqa: E402
from .validate import validate  # noqa: E402
from .writer import Writer  # noqa: E402

__all__ = [
    "SCHEMA_VERSION", "schema", "schema_text", "example_names", "example_text",
    "Database", "Object", "TreeNode", "Unresolved", "AmbiguousKey", "Writer", "import_file", "export_file",
    "validate", "Issue", "SvdbError", "UvmTree", "UvmNode", "UvmLink", "uvm_tree_schema",
]
