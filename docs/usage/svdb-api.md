# The svdb Python API

`sphinx_systemverilog.svdb` reads and writes **svdb** databases: SystemVerilog
design and testbench information (declarations, documentation, structure,
connectivity, elaboration and the UVM layer) in a form any tool can produce.
The interchange format is NDJSON, defined by the JSON Schema
`svdb/schema/svdb-1.schema.json`. An `.svdb` file is that content imported into
SQLite and indexed for queries. The package does not import Sphinx or pyslang.

```{note}
This page is a stub. The format documentation (records, kinds, identity rules,
the producer guide) comes in a later phase. The SQLite layout is internal and
may change between releases; use NDJSON for interchange.
```

## Quick start

```python
from sphinx_systemverilog import svdb

svdb.import_file("design.ndjson", "design.svdb")   # NDJSON -> indexed SQLite

with svdb.Database.open(["tb.svdb", "vip.svdb"]) as db:   # earlier files win
    item = db.get("axi_pkg::axi_item")                     # or "package:foo", "$unit[cu0]::t"
    print(item.kind, item.sig, item.doc and item.doc.text)
    for m in db.members(item):
        print(" ", m.kind, m.name)
    print([d.qname for d in db.derived(item, transitive=True)])
```

The same operations are on the command line:

```text
svdb import design.ndjson -o design.svdb
svdb validate design.ndjson
svdb stats design.svdb --unresolved
svdb query -d design.svdb members axi_pkg::axi_item
svdb export design.svdb -o design.ndjson
```

## Reading

```{eval-rst}
.. automodule:: sphinx_systemverilog.svdb.database
   :members: Database, Object, Loc, Doc, Reference, Connection, TreeNode, Unresolved, AmbiguousKey
   :member-order: bysource
```

## Writing and importing

```{eval-rst}
.. automodule:: sphinx_systemverilog.svdb.writer
   :members: Writer, write

.. automodule:: sphinx_systemverilog.svdb.importer
   :members: import_file, import_stream, read_ndjson

.. automodule:: sphinx_systemverilog.svdb.exporter
   :members: export_file, export, iter_records
```

## Validation and problems

```{eval-rst}
.. automodule:: sphinx_systemverilog.svdb.validate
   :members: validate, Report

.. automodule:: sphinx_systemverilog.svdb.issues
   :members: Issue, SvdbError
```

## Canonical forms

```{eval-rst}
.. automodule:: sphinx_systemverilog.svdb.canon
   :members: parse_qname, format_qname, join, parse_key, format_key, Key, genblk_names,
             disambiguate, anonymous_name, elab_key, elab_ref, object_hash, canonical_json
```
