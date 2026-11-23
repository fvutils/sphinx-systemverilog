"""D5-IMPL-1 / D5-TEST-3: ``sv_external`` name patterns.

A name matching a pattern is defined outside the sources: its "unknown
module" / "unknown class" diagnostic is dropped, and its instances are kept as
``unresolved`` with their connections.  Only matching names are silenced; any
other unknown module still warns, and so does every one without the setting.
"""

from __future__ import annotations

import pytest

from sphinx_systemverilog.frontend.build import Options, parse, records
from sphinx_systemverilog.model.builder import ModelBuilder

TB = """
module tb;
  wire a;
  axi_vip_mst u0 (.aclk(a));
  other_ip u1 (a);
endmodule
class env;
  axi_vip_cfg cfg;
  function void build(); cfg = axi_vip_cfg::type_id::create("cfg"); endfunction
endclass
"""


def _diagnostics(external=None) -> str:
    builder = ModelBuilder(external=external)
    builder.build_from_text(TB, "tb.sv")
    return "\n".join(builder.diagnostics)


def test_without_patterns_unknown_names_warn():
    text = _diagnostics()
    assert "unknown module 'axi_vip_mst'" in text
    assert "unknown module 'other_ip'" in text
    assert "axi_vip_cfg" in text


def test_patterns_silence_matching_names_only():
    text = _diagnostics(["axi_vip*"])
    assert "axi_vip" not in text
    assert "unknown module 'other_ip'" in text


def test_patterns_are_case_sensitive_globs():
    assert "axi_vip_mst" in _diagnostics(["AXI_VIP*"])
    assert "axi_vip_mst" not in _diagnostics(["axi_vip_m?t", "axi_vip_cfg"])


@pytest.mark.sphinx("html", testroot="external", confoverrides={"sv_external": ["axi_vip_*"]})
def test_external_vip_builds_without_warnings(app, warning):
    app.build()
    assert warning.getvalue().strip() == ""


def test_matching_instances_are_kept_unresolved_with_connections(tmp_path):
    src = tmp_path / "tb.sv"
    src.write_text(TB.split("class")[0])
    options = Options.make(build_units=[str(src)], external=["axi_vip*"])
    recs = list(records(parse(options), options))
    u0 = next(r for r in recs if r.get("qname") == "tb::u0")
    assert u0["detail"]["state"] == "unresolved"
    assert u0["detail"]["of"] == {"name": "axi_vip_mst"}
    assert [c["port"] for c in u0["detail"]["conns"]] == ["aclk"]
    assert not any(r["r"] == "diag" and "axi_vip" in r.get("message", "") for r in recs)
    assert any(r["r"] == "diag" and "other_ip" in r.get("message", "") for r in recs)


@pytest.mark.sphinx("html", testroot="external")
def test_unknown_module_still_warns_without_sv_external(app, warning):
    app.build()
    messages = warning.getvalue()
    assert "unknown module 'axi_vip_mst'" in messages
    assert "unknown module 'axi_vip_slv'" in messages


def test_packages_match_too():
    builder = ModelBuilder(external=["axi_vip*"])
    builder.build_from_text("module m; import axi_vip_pkg::*; axi_vip_pkg::cfg_t x; endmodule", "m.sv")
    assert builder.diagnostics == []


@pytest.mark.sphinx("html", testroot="external", confoverrides={"sv_external": ["axi_vip_*"]})
def test_absent_vip_appears_in_tree_and_diagram(app, warning):
    """D5-TEST-1: an instance of a definition outside the build is still a node."""
    from sphinx.ext.graphviz import graphviz

    app.build()
    assert warning.getvalue().strip() == ""
    doctree = app.env.get_doctree("index")
    tree = doctree.astext()
    assert "u_mst : axi_vip_mst   (not in build)" in tree
    assert "u_slv : axi_vip_slv   (not in build)" in tree
    code = next(iter(doctree.findall(graphviz)))["code"]
    assert '"tb" -> "axi_vip_mst" [label="u_mst"];' in code
    assert '"axi_vip_mst" [label="axi_vip_mst" style=dotted];' in code


def test_unresolved_instance_keeps_written_parameters():
    from sphinx_systemverilog.model.structure import StructureProvider

    builder = ModelBuilder(external=["axi_vip*"])
    builder.build_from_text(
        "module tb; axi_vip_mst #(.W(8), 3) u0 (); endmodule", "tb.sv"
    )
    structure = StructureProvider(builder.compilation, builder.source_manager).get()
    (inst,) = structure.children_of_elaboration("tb", ())
    assert inst.unresolved
    assert inst.param_text == "#(W=8, 3)"


@pytest.mark.sphinx("html", testroot="external", confoverrides={
    "sv_external": ["axi_vip_*"], "sv_external_sources": ["vip/axi_vip_mst.sv"]})
def test_stub_sources_make_instances_external(app, warning):
    """D5-IMPL-2: a stub from ``sv_external_sources`` is known but external."""
    from sphinx.ext.graphviz import graphviz

    app.build()
    assert warning.getvalue().strip() == ""
    doctree = app.env.get_doctree("index")
    tree = doctree.astext()
    assert "u_mst : axi_vip_mst #(W=32)   (external)" in tree
    assert "u_slv : axi_vip_slv   (not in build)" in tree
    code = next(iter(doctree.findall(graphviz)))["code"]
    assert '"axi_vip_mst" [label="axi_vip_mst" style=dashed];' in code
    assert '"axi_vip_slv" [label="axi_vip_slv" style=dotted];' in code


def test_stub_source_objects_are_flagged_with_origin(tmp_path):
    (tmp_path / "vip").mkdir()
    (tmp_path / "vip" / "axi_vip_mst.sv").write_text(
        "module axi_vip_mst (input wire aclk, output wire [31:0] awaddr); endmodule\n")
    (tmp_path / "tb.sv").write_text(
        "module tb; wire c; wire [31:0] a; axi_vip_mst u0 (.aclk(c), .awaddr(a)); endmodule\n")
    options = Options.make(build_units=["tb.sv"], base_path=str(tmp_path),
                           external_sources={"axi_vip": ["vip/*.sv"]})
    recs = list(records(parse(options), options))
    by = {r.get("qname"): r for r in recs if r["r"] == "object"}
    assert by["axi_vip_mst"]["flags"] == ["external"]
    assert by["axi_vip_mst"]["origin"] == "axi_vip"
    assert "external" not in by["tb"].get("flags", [])
    u0 = by["tb::u0"]
    assert u0["detail"]["state"] == "external"
    assert {c["port"]: c.get("dir") for c in u0["detail"]["conns"]} == {"aclk": "input", "awaddr": "output"}
    assert not any(r["r"] == "diag" for r in recs)


# -- D5-IMPL-3: link-out (plan §6.4) -----------------------------------------

VIP_NDJSON = "\n".join([
    '{"r":"header","format":"svdb","schema":"1.0","producer":{"name":"vip docs"},"role":"external",'
    '"origin":"axi_vip","docs":{"base_url":"https://vip.example/axi/","url_template":"sv/{kind}/{name}.html#{anchor}"},'
    '"sections":{"files":"partial","objects":"partial","docs":"absent"}}',
    '{"r":"object","kind":"module","ns":"design","qname":"axi_vip_mst","name":"axi_vip_mst","pos":0}',
    *(f'{{"r":"object","kind":"port","ns":"design","qname":"axi_vip_mst::{n}","name":"{n}",'
      f'"parent":"axi_vip_mst","pos":{i},"detail":{{"dir":"{d}"}}}}'
      for i, (n, d) in enumerate([("aclk", "input"), ("aresetn", "input"), ("awaddr", "output")])),
    '{"r":"object","kind":"module","ns":"design","qname":"axi_vip_slv","name":"axi_vip_slv","pos":1,'
    '"url":"slave.html"}',
]) + "\n"


def _external_db(tmp_path):
    from sphinx_systemverilog.svdb import import_file

    src = tmp_path / "axi_vip.ndjson"
    src.write_text(VIP_NDJSON)
    out = tmp_path / "axi_vip.svdb"
    assert not [i for i in import_file(src, out) if i.severity == "error"]
    return out


def _external_app(make_app, rootdir, tmp_path, **conf):
    import shutil

    src = tmp_path / "external"
    shutil.copytree(rootdir / "test-external", src)
    app = make_app("html", srcdir=src, confoverrides={"sv_external": ["axi_vip_*"], **conf})
    app.build()
    return app


def test_external_database_links_out(make_app, rootdir, tmp_path):
    """An instance of a VIP module described by a ``role: external`` database
    links to its documentation: ``url_template``, or the object's own ``url``,
    both relative to ``docs.base_url``."""
    db = _external_db(tmp_path)
    app = _external_app(make_app, rootdir, tmp_path,
                        sv_databases=[{"path": str(db), "role": "external"}])
    assert app._warning.getvalue().strip() == ""
    html = (app.outdir / "index.html").read_text()
    assert 'href="https://vip.example/axi/sv/module/axi_vip_mst.html#sv-axi_vip_mst"' in html
    assert 'href="https://vip.example/axi/slave.html"' in html
    # Not documented here: the external database brings no local objects.
    assert "axi_vip_mst" not in app.env.sv_index


def test_external_database_ports_label_diagram_edges(make_app, rootdir, tmp_path):
    """D5-TEST-2: a VIP described only by an external database: the diagram
    edge to its instance lists the port names by direction, and its name
    links to ``url_template``."""
    from sphinx.ext.graphviz import graphviz

    db = _external_db(tmp_path)
    app = _external_app(make_app, rootdir, tmp_path,
                        sv_databases=[{"path": str(db), "role": "external"}])
    assert app._warning.getvalue().strip() == ""
    code = next(iter(app.env.get_doctree("index").findall(graphviz)))["code"]
    assert '"tb" -> "axi_vip_mst" [label="u_mst\\nin: aclk, aresetn\\nout: awaddr"];' in code
    # No ports in the database for the slave: the instance name only.
    assert '"tb" -> "axi_vip_slv" [label="u_slv"];' in code
    html = (app.outdir / "index.html").read_text()
    assert 'href="https://vip.example/axi/sv/module/axi_vip_mst.html#sv-axi_vip_mst"' in html


def test_instance_dot_port_labels():
    from sphinx_systemverilog.autodoc.diagrams import _port_label

    assert _port_label([("a", "inout"), ("b", "input"), ("c", ""), ("d", "input")]) == \
        "in: b, d\\ninout: a\\nport: c"


def test_external_docs_templates_link_out(make_app, rootdir, tmp_path):
    app = _external_app(make_app, rootdir, tmp_path,
                        sv_external_docs={"axi_vip_m*": "https://vendor.example/{name}.html"})
    assert app._warning.getvalue().strip() == ""
    html = (app.outdir / "index.html").read_text()
    assert 'href="https://vendor.example/axi_vip_mst.html"' in html
    # No pattern for the slave: plain text, no warning.
    assert "vendor.example/axi_vip_slv" not in html


def test_external_database_comes_before_templates(make_app, rootdir, tmp_path):
    db = _external_db(tmp_path)
    app = _external_app(make_app, rootdir, tmp_path,
                        sv_databases=[{"path": str(db), "role": "external"}],
                        sv_external_docs={"axi_vip_*": "https://vendor.example/{name}.html"})
    html = (app.outdir / "index.html").read_text()
    assert "vip.example/axi/sv/module/axi_vip_mst.html" in html
    assert "vendor.example/axi_vip_mst" not in html


def test_template_url_matches_name_or_leaf():
    from sphinx_systemverilog.linkout import template_url

    pats = {"axi_*": "https://v/{name}.html", "pkg::x*": "https://v/{qname}"}
    assert template_url(pats, "axi_pkg::axi_cfg") == "https://v/axi_cfg.html"
    assert template_url(pats, "pkg.xy") == "https://v/pkg::xy"
    assert template_url(pats, "other") is None
