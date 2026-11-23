"""Check svdb records against the contract.

Two layers:

* **Schema**: every record against ``svdb-1.schema.json``, when the optional
  ``jsonschema`` package is installed (``pip install sphinx-systemverilog[validate]``).
* **Semantics**: what a schema cannot say, found by importing into an
  in-memory database with a non-strict :class:`Writer` -- duplicate keys
  (with both locations), parent kinds (plan §5.2), dangling parents, bodies
  and elaboration links, records in a section the header declares absent.
  Unresolved references are counted, not reported as errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from . import schema as _schema
from .issues import Issue, SvdbError
from .writer import Writer


@dataclass
class Report:
    """The outcome of :func:`validate`."""

    issues: list[Issue] = field(default_factory=list)
    records: int = 0
    objects: int = 0
    references: int = 0
    #: References with no producer target that the importer could not resolve.
    unresolved: int = 0
    #: References whose producer target is not in this file (another database).
    external: int = 0
    schema_checked: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _schema_validator():
    try:
        import jsonschema
    except ImportError:
        return None
    return jsonschema.Draft202012Validator(_schema())


def validate(recs: Iterable[tuple[dict, str]] | Iterable[dict], *, check_schema: bool = True) -> Report:
    """Validate records (header first).  *recs* yields records, or
    ``(record, where)`` pairs as :func:`importer.read_ndjson` does."""
    report = Report()
    validator = _schema_validator() if check_schema else None
    if check_schema and validator is None:
        report.issues.append(Issue("warning", "NoJsonSchema",
                                   "jsonschema is not installed; only the built-in checks ran"))
    report.schema_checked = validator is not None
    w = Writer(":memory:", strict=False)
    try:
        for item in recs:
            rec, where = item if isinstance(item, tuple) else (item, "")
            report.records += 1
            where = where or f"record {report.records}"
            if validator is not None:
                for e in sorted(validator.iter_errors(rec), key=lambda e: e.json_path):
                    report.issues.append(Issue("error", "Schema", f"{e.json_path}: {e.message}", where))
            if rec.get("r") == "object":
                report.objects += 1
            w.add(rec, where)
        w.finish()
    except SvdbError as e:
        report.issues.extend(w.issues)
        report.issues.append(Issue("error", "Fatal", str(e)))
        w.abort()
        return report
    report.issues.extend(w.issues)
    c = w.conn
    report.references = c.execute("SELECT count(*) FROM ref").fetchone()[0]
    report.unresolved = c.execute("SELECT count(*) FROM ref WHERE target_id IS NULL AND given = 0").fetchone()[0]
    report.external = c.execute("SELECT count(*) FROM ref WHERE target_id IS NULL AND given = 1").fetchone()[0]
    c.close()
    return report
