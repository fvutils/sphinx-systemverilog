"""Links to components documented outside the project (plan §6.4).

A reference the domain cannot resolve to a local object is tried, in order:

1. the ``role: external`` databases of ``sv_databases`` (in the domain's
   ``resolve_xref``): the object's own ``url``, else the file header's
   ``docs.url_template``, both relative to ``docs.base_url``;
2. intersphinx (its ``missing-reference`` handler, priority 500);
3. ``sv_external_docs`` URL templates (:func:`missing_reference`, priority 900);
4. plain text; only an explicit typed role (``:sv:class:``) warns.
"""

from __future__ import annotations

import fnmatch
import os
from typing import Any
from urllib.parse import urljoin

from docutils import nodes
from sphinx.util import logging

logger = logging.getLogger(__name__)

#: Priority of :func:`missing_reference`: after intersphinx (500).
PRIORITY = 900


class ExternalDatabases:
    """The ``role: external`` databases, opened on first use.

    Kept on the application, not the (pickled) environment: the open
    :class:`~.svdb.Database` holds SQLite connections.
    """

    def __init__(self, paths: list[str]):
        self.paths = paths
        self._db = None

    def _database(self):
        if self._db is None and self.paths:
            from .svdb import Database

            self._db = Database.open(self.paths)
        return self._db

    def url(self, target: str) -> tuple[str, str] | None:
        """``(url, qname)`` of the one external object *target* names, or None
        (not there, ambiguous, or its file gives no way to build a URL)."""
        db = self._database()
        if db is None:
            return None
        found = db.candidates(target)
        if len(found) != 1:
            return None
        o = found[0]
        docs = db.headers[o.source].get("docs") or {}
        base = docs.get("base_url", "")
        if o.url:
            return urljoin(base, o.url), o.qname
        template = docs.get("url_template")
        if template:
            return urljoin(base, expand(template, o.qname, o.kind)), o.qname
        return None

    def ports(self, definition: str) -> list[tuple[str, str]] | None:
        """``(name, dir)`` of the ports of the one external module, interface
        or program *definition* names, in declaration order; None when it is
        not there or ambiguous."""
        db = self._database()
        if db is None:
            return None
        found = [o for o in db.candidates(definition)
                 if o.kind in ("module", "interface", "program")]
        if len(found) != 1:
            return None
        members = sorted(db.members(found[0], kinds=["port"]), key=lambda o: o.pos)
        return [(p.name, str(p.detail.get("dir", ""))) for p in members]

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


def expand(template: str, qname: str, kind: str = "") -> str:
    """*template* with ``{name}``, ``{qname}``, ``{kind}`` and ``{anchor}`` filled."""
    return template.format(
        name=qname.rsplit("::", 1)[-1], qname=qname, kind=kind,
        anchor="sv-" + qname.replace("::", "-"),
    )


def open_external(app: Any) -> None:
    """Attach the ``role: external`` databases to *app* (``builder-inited``)."""
    paths = [
        d["path"] if os.path.isabs(d["path"]) else os.path.join(app.confdir, d["path"])
        for d in app.config.sv_databases if d["role"] == "external"
    ]
    app._sv_external_dbs = ExternalDatabases(paths)


def external_ports(app: Any, definition: str) -> list[tuple[str, str]] | None:
    """Ports of *definition* from the ``role: external`` databases, or None."""
    dbs = getattr(app, "_sv_external_dbs", None)
    return dbs.ports(definition) if dbs is not None else None


def database_ref(app: Any, target: str, contnode: nodes.Node) -> nodes.Node | None:
    """A link into an external database for *target*, or None."""
    dbs = getattr(app, "_sv_external_dbs", None)
    hit = dbs.url(target) if dbs is not None else None
    if hit is None:
        return None
    return _reference(hit[0], hit[1], contnode)


def template_url(patterns: dict[str, str], target: str) -> str | None:
    """The URL of the first ``sv_external_docs`` pattern *target* matches.

    A pattern is matched against the name as written and its last segment.
    """
    qname = target.replace(".", "::")
    leaf = qname.rsplit("::", 1)[-1]
    for pattern, template in patterns.items():
        if fnmatch.fnmatchcase(qname, pattern) or fnmatch.fnmatchcase(leaf, pattern):
            return expand(template, qname)
    return None


def missing_reference(app: Any, env: Any, node: Any, contnode: nodes.Node):
    """``sv_external_docs`` templates, then the warning for typed roles."""
    if node.get("refdomain") != "sv":
        return None
    target = node["reftarget"]
    url = template_url(app.config.sv_external_docs, target)
    if url is not None:
        return _reference(url, target, contnode)
    typ = node.get("reftype")
    if typ not in ("obj", None):
        domain = env.get_domain("sv")
        candidates = domain.candidates(target)
        detail = ""
        if candidates:
            detail = " (ambiguous; candidates: %s)" % ", ".join(sorted(candidates))
        logger.warning(
            "sphinx-systemverilog: cannot resolve sv:%s reference %r%s",
            typ, target, detail, type="systemverilog", location=node,
        )
    return None


def _reference(url: str, title: str, contnode: nodes.Node) -> nodes.reference:
    ref = nodes.reference("", "", internal=False, refuri=url, reftitle=title,
                          classes=["sv-external"])
    ref += contnode
    return ref
