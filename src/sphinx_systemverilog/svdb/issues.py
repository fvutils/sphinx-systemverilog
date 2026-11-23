"""Problems found while writing, importing or validating a database."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """One problem.  ``severity`` is ``error`` or ``warning``.

    ``where`` locates it: ``"<record n>"`` for a record in the input, or a
    source location (``path:line``) when the record had one.
    """

    severity: str
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        prefix = f"{self.where}: " if self.where else ""
        return f"{prefix}{self.severity}: [{self.code}] {self.message}"


class SvdbError(Exception):
    """A database could not be written, imported or opened.

    ``issues`` lists every error found (and the warnings collected with them).
    """

    def __init__(self, message: str, issues: list[Issue] | None = None):
        self.issues = list(issues or ())
        errors = [i for i in self.issues if i.severity == "error"]
        if errors:
            shown = "\n  ".join(str(i) for i in errors[:20])
            more = f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else ""
            message = f"{message}\n  {shown}{more}"
        super().__init__(message)
