"""Write a database back out as NDJSON, in canonical order.

Canonical order (plan D1-IMPL-4): the header; then each record type in
:data:`layout.EXPORT_ORDER`; objects sorted by ``(ns, unit, qname)``,
bodies in the order of their objects, and every other record type in the
order it was written.  Fields come in schema order; ``flags`` in the
schema's enum order.  Refs are written as the producer gave them -- the
importer's best-effort resolutions stay in the ``ref`` table.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import IO, Iterator

from . import layout, records

_OBJECT_SQL = """
SELECT o.id, o.kind, o.ns, u.name, o.qname, o.name, p.qname, s.qname, o.pos,
       f.fid, o.line, o.col, o.end_line, o.end_col, o.extra, o.sig, o.quals,
       d.text, d.style, d.loc, d.grp, o.flags, g.name, o.url, o.hash, o.detail
FROM object o
LEFT JOIN unit u ON u.id = o.unit_id
LEFT JOIN object p ON p.id = o.parent_id
LEFT JOIN object s ON s.id = o.scope_id
LEFT JOIN file f ON f.id = o.file_id
LEFT JOIN doc d ON d.object_id = o.id
LEFT JOIN origin g ON g.id = o.origin_id
"""


def _ordered(rec: dict, r: str) -> dict:
    fields = records.record_types()[r].fields
    return {k: rec[k] for k in fields if k in rec}


def _object(row) -> dict:
    (_id, kind, ns, unit, qname, name, parent, scope, pos, fid, line, col, end_line, end_col, extra, sig, quals,
     dtext, dstyle, dloc, dgroup, flags, origin, url, digest, detail) = row
    rec: dict = {"r": "object", "kind": kind, "ns": ns}
    if unit is not None and ns == "unit":
        rec["unit"] = unit
    rec["qname"] = qname
    rec["name"] = name
    if parent is not None:
        rec["parent"] = parent
    if scope is not None:
        rec["scope"] = scope
    rec["pos"] = pos
    if fid is not None:
        loc = {"file": fid, "line": line}
        for k, v in (("col", col), ("end_line", end_line), ("end_col", end_col)):
            if v is not None:
                loc[k] = v
        rec["loc"] = loc
    if extra:
        rec.update(json.loads(extra))
    if sig is not None:
        rec["sig"] = sig
    if quals is not None:
        rec["quals"] = json.loads(quals)
    if dtext is not None:
        doc = {"text": dtext}
        if dstyle is not None:
            doc["style"] = dstyle
        if dloc is not None:
            doc["loc"] = json.loads(dloc)
        if dgroup is not None:
            doc["group"] = dgroup
        rec["doc"] = doc
    if flags:
        rec["flags"] = layout.bits_to_flags(flags)
    if origin is not None:
        rec["origin"] = origin
    if url is not None:
        rec["url"] = url
    if digest is not None:
        rec["hash"] = digest.hex()
    if detail is not None:
        rec["detail"] = json.loads(detail)
    return _ordered(rec, "object")


def object_record(conn: sqlite3.Connection, oid: int) -> dict:
    """The ``object`` record of row *oid*, as it would be exported."""
    return _object(conn.execute(_OBJECT_SQL + " WHERE o.id = ?", (oid,)).fetchone())


def iter_records(conn: sqlite3.Connection) -> Iterator[dict]:
    """Every record of the database on *conn*, in canonical order."""
    c = conn
    yield json.loads(c.execute("SELECT value FROM meta WHERE key = 'header'").fetchone()[0])
    for fid, path, sha, size, lang, prot, text in c.execute(
            "SELECT f.fid, f.path, f.sha256, f.size, f.lang, f.protected, t.text FROM file f"
            " LEFT JOIN file_text t ON t.file_id = f.id WHERE f.path IS NOT NULL ORDER BY f.seq"):
        rec = {"r": "file", "id": fid, "path": path}
        for k, v in (("sha256", sha), ("size", size), ("lang", lang)):
            if v is not None:
                rec[k] = v
        if prot is not None:
            rec["protected"] = json.loads(prot)
        if text is not None:
            rec["text"] = text
        yield rec
    for frm, to, line in c.execute(
            "SELECT a.fid, b.fid, i.line FROM include i JOIN file a ON a.id = i.from_id"
            " JOIN file b ON b.id = i.to_id ORDER BY i.seq"):
        rec = {"r": "include", "from": frm, "to": to}
        if line is not None:
            rec["line"] = line
        yield rec
    for uid, name, defines, nettype, timescale in c.execute(
            "SELECT id, name, defines, default_nettype, timescale FROM unit WHERE seq IS NOT NULL ORDER BY seq"):
        rec = {"r": "unit", "id": name}
        files = [r[0] for r in c.execute(
            "SELECT f.fid FROM unit_file x JOIN file f ON f.id = x.file_id WHERE x.unit_id = ? ORDER BY x.pos", (uid,))]
        if files:
            rec["files"] = files
        if defines is not None:
            rec["defines"] = json.loads(defines)
        if nettype is not None:
            rec["default_nettype"] = nettype
        if timescale is not None:
            rec["timescale"] = timescale
        yield rec
    order = " ORDER BY o.ns, coalesce(u.name, ''), o.qname"
    for row in c.execute(_OBJECT_SQL + order):
        yield _object(row)
    for qname, ns, unit, text in c.execute(
            "SELECT o.qname, o.ns, u.name, b.text FROM body b JOIN object o ON o.id = b.object_id"
            " LEFT JOIN unit u ON u.id = o.unit_id" + order):
        yield {"r": "body", "of": qname, "text": text}
    for table in ("import", "use", "elab", "top"):
        key = "id" if table == "elab" else "seq"
        for (rec,) in c.execute(f"SELECT rec FROM {table} ORDER BY {key}"):
            yield json.loads(rec)
    for r in (t for t in layout.EXPORT_ORDER if t.startswith("uvm.")):
        for (rec,) in c.execute("SELECT rec FROM uvm WHERE r = ? ORDER BY seq", (r,)):
            yield json.loads(rec)
    for (rec,) in c.execute("SELECT rec FROM diag ORDER BY seq"):
        yield json.loads(rec)


def dumps(rec: dict) -> str:
    """One NDJSON line (without the newline)."""
    return json.dumps(rec, ensure_ascii=False, separators=(",", ":"))


def export(conn: sqlite3.Connection, out: IO[str]) -> int:
    """Write every record to *out*; returns the number of records."""
    n = 0
    for rec in iter_records(conn):
        out.write(dumps(rec))
        out.write("\n")
        n += 1
    return n


def export_file(db_path: str | os.PathLike, out_path: str | os.PathLike) -> int:
    """Export the database at *db_path* to the NDJSON file *out_path*."""
    conn = sqlite3.connect(f"file:{os.fspath(db_path)}?mode=ro", uri=True)
    try:
        with open(out_path, "w", encoding="utf-8") as out:
            return export(conn, out)
    finally:
        conn.close()
