"""SQLite layout of an ``.svdb`` file (plan §7).

The layout is *not* the interchange contract -- NDJSON is.  It is versioned on
its own (:data:`LAYOUT_VERSION`); a reader that finds another version asks for
a re-import rather than guessing.

Row ids are internal.  The identity of an object is ``(ns, unit_id, qname)``
where ``unit_id`` is 0 outside the ``unit`` name space.  Records that are read
whole and rarely queried (``import``, ``use``, ``elab``, ``top``, ``uvm.*``,
``diag``) keep their record JSON in a ``rec`` column, next to the columns the
queries need; ``object`` is split into columns plus ``detail`` and ``extra``
JSON.
"""

from __future__ import annotations

#: Bump on any incompatible change to the tables below.
LAYOUT_VERSION = 1

#: ``object.flags`` bitmask, in the schema's enum order.
FLAGS = ("external", "protected", "implicit", "anonymous", "forward", "macro_generated", "extern_only")
FLAG_BIT = {name: 1 << i for i, name in enumerate(FLAGS)}

#: ``ref.src``: which kind of record a reference was found in.
SRC_OBJECT, SRC_IMPORT, SRC_USE, SRC_UVM = 0, 1, 2, 3

TABLES = """
CREATE TABLE meta      (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE section   (name TEXT PRIMARY KEY, status TEXT NOT NULL);
CREATE TABLE file      (id INTEGER PRIMARY KEY, fid TEXT UNIQUE NOT NULL, seq INT, path TEXT,
                        sha256 TEXT, size INT, lang TEXT, protected TEXT);
CREATE TABLE file_text (file_id INTEGER PRIMARY KEY, text TEXT);
CREATE TABLE include   (seq INTEGER PRIMARY KEY, from_id INT, to_id INT, line INT);
CREATE TABLE unit      (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, seq INT,
                        defines TEXT, default_nettype TEXT, timescale TEXT);
CREATE TABLE unit_file (unit_id INT, pos INT, file_id INT);
CREATE TABLE origin    (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);

CREATE TABLE object (
  id INTEGER PRIMARY KEY,
  ns TEXT NOT NULL, unit_id INT NOT NULL DEFAULT 0,
  qname TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  parent_id INT, scope_id INT, pos INT NOT NULL,
  file_id INT, line INT, col INT, end_line INT, end_col INT,
  flags INT NOT NULL DEFAULT 0,
  quals TEXT, sig TEXT, origin_id INT, url TEXT,
  hash BLOB, detail TEXT, extra TEXT);
CREATE TABLE doc   (object_id INTEGER PRIMARY KEY, text TEXT, style TEXT, grp TEXT, loc TEXT);
CREATE TABLE body  (object_id INTEGER PRIMARY KEY, text TEXT);

-- Every Ref and Span in a record, flattened.  target_* is the producer's
-- target (or, once resolved, the local object's key); target_id is the local
-- row, NULL when the target lives in another database or is unresolved.
CREATE TABLE ref (
  id INTEGER PRIMARY KEY, src INT NOT NULL, src_id INT NOT NULL,
  role TEXT NOT NULL, pos INT, seq INT, head INT NOT NULL DEFAULT 0,
  name TEXT NOT NULL, lookup TEXT, given INT NOT NULL DEFAULT 0,
  target_qname TEXT, target_ns TEXT, target_unit TEXT, target_id INT);

CREATE TABLE import (seq INTEGER PRIMARY KEY, scope_name TEXT, scope_id INT,
                     package_name TEXT, package_id INT, item TEXT, is_export INT, rec TEXT);
CREATE TABLE use    (seq INTEGER PRIMARY KEY, from_name TEXT, from_id INT, to_id INT, kind TEXT, rec TEXT);
CREATE TABLE diag   (seq INTEGER PRIMARY KEY, severity TEXT, code TEXT, rec TEXT);

CREATE TABLE inst      (object_id INTEGER PRIMARY KEY, def_id INT, of_name TEXT, of_id INT,
                        of_kind TEXT, state TEXT, array_count INT, bind_from_id INT);
CREATE TABLE port_conn (inst_id INT, pos INT, port TEXT, port_id INT, mode TEXT, dir TEXT, expr TEXT);
CREATE VIEW conn_sig AS
  SELECT src_id AS inst_id, pos AS conn_pos, target_id AS signal_id
  FROM ref WHERE src = 0 AND role = 'conns.expr';

CREATE TABLE elab      (id INTEGER PRIMARY KEY, def_name TEXT NOT NULL, def_id INT, key TEXT NOT NULL,
                        count INT, truncated INT, rec TEXT, UNIQUE (def_name, key));
CREATE TABLE elab_site (elab_id INT, pos INT, inst_name TEXT, inst_id INT, present INT, count INT,
                        child_def TEXT, child_key TEXT, child_elab_id INT);
CREATE TABLE elab_gen  (elab_id INT, pos INT, block_name TEXT, block_id INT, taken INT, iterations INT);
CREATE TABLE top       (seq INTEGER PRIMARY KEY, elab_def TEXT, elab_key TEXT, elab_id INT, origin TEXT, rec TEXT);

-- The uvm.* records, read whole; the derived views of D4 add their own tables.
CREATE TABLE uvm (seq INTEGER PRIMARY KEY, r TEXT NOT NULL, owner_id INT, type_id INT, field TEXT, rec TEXT);
"""

#: Built after the bulk load (plan D1-IMPL-1), one per hot query (§8.2).
INDEXES = (
    # qname first, so the key index also serves lookups by qname alone.
    "CREATE UNIQUE INDEX object_key ON object(qname, ns, unit_id)",
    "CREATE INDEX object_name ON object(name)",
    "CREATE INDEX object_parent ON object(parent_id, pos)",
    "CREATE INDEX object_kind ON object(kind)",
    "CREATE INDEX ref_target ON ref(target_id, role)",
    # Only references into another file are looked up by name (federation).
    "CREATE INDEX ref_target_qname ON ref(target_qname) WHERE target_id IS NULL",
    "CREATE INDEX ref_src ON ref(src, src_id)",
    "CREATE INDEX import_scope ON import(scope_name)",
    "CREATE INDEX inst_of ON inst(of_id)",
    "CREATE INDEX inst_of_name ON inst(of_name)",
    "CREATE INDEX inst_def ON inst(def_id)",
    "CREATE INDEX port_conn_inst ON port_conn(inst_id, pos)",
    "CREATE INDEX elab_def ON elab(def_id)",
    "CREATE INDEX elab_site_elab ON elab_site(elab_id, pos)",
    "CREATE INDEX elab_site_child ON elab_site(child_elab_id)",
    "CREATE INDEX elab_gen_elab ON elab_gen(elab_id, pos)",
    "CREATE INDEX uvm_owner ON uvm(r, owner_id)",
    "CREATE INDEX uvm_type ON uvm(r, type_id)",
    "CREATE INDEX uvm_field ON uvm(r, field)",
)

#: Section that a record type belongs to (header ``sections``).
RECORD_SECTION = {
    "file": "files", "include": "files", "unit": "files",
    "object": "objects", "import": "objects",
    "body": "bodies",
    "elab": "elaboration", "top": "elaboration",
    "use": "uses",
    "uvm.root": "uvm.tree", "uvm.type": "uvm.tree", "uvm.child": "uvm.tree", "uvm.conn": "uvm.tree",
    "uvm.config": "uvm.config", "uvm.override": "uvm.overrides", "uvm.binding": "uvm.bindings",
    "uvm.sequence": "uvm.sequences",
    "diag": "diagnostics",
}

#: Order of record types in an export (plan D1-IMPL-4).
EXPORT_ORDER = (
    "header", "file", "include", "unit", "object", "body", "import", "use", "elab", "top",
    "uvm.root", "uvm.type", "uvm.child", "uvm.conn", "uvm.config", "uvm.override",
    "uvm.binding", "uvm.sequence", "diag",
)


def flags_to_bits(flags) -> int:
    bits = 0
    for f in flags or ():
        bits |= FLAG_BIT.get(f, 0)
    return bits


def bits_to_flags(bits: int) -> list[str]:
    return [name for name in FLAGS if bits & FLAG_BIT[name]]
