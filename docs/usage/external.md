# External components

A design often instantiates code the documentation project does not have: a
vendor's verification IP delivered as an encrypted library, a hard macro, a
block that another team documents. This page shows the three ways to describe
such a component, from the least work to the most information:

| Way | Setting | What you give | What the docs show |
|---|---|---|---|
| Name pattern | `sv_external` | the names | instances drawn dotted, `(not in build)`, no warning |
| Stub sources | `sv_external_sources` | header or stub `.sv` files | instances drawn dashed, `(external)`, ports known |
| External database | `sv_databases` with `role: external` | an `.svdb` describing the component | links to its documentation, ports on diagram edges |

They combine: a pattern keeps the build quiet, and a database or a URL template
(`sv_external_docs`) adds the links.

The examples below use this testbench, whose VIP sources are not part of the
build:

```systemverilog
module tb;
  wire clk, rst_n;
  wire [31:0] awaddr;

  axi_vip_mst u_mst (.aclk(clk), .aresetn(rst_n), .awaddr(awaddr));
  axi_vip_slv u_slv (.aclk(clk), .aresetn(rst_n), .awaddr(awaddr));
endmodule
```

Without any of the settings on this page, each instance warns
`unknown module 'axi_vip_mst'`, and a build under `-W` fails.

## Name patterns: `sv_external`

List the names that are defined elsewhere, as glob patterns (`fnmatch`,
case-sensitive):

```python
sv_external = ["axi_vip_*"]
```

For a matching name, and only for it, the "unknown module", "unknown
interface", "unknown class", "unknown package" and "undeclared identifier"
diagnostics are dropped. A name that matches no pattern still warns, so a typo
in your own design is not hidden.

The instances stay in the design:

- `sv:instance-tree` lists them with ` (not in build)` after the type, and
  their parameters as written at the instantiation site (`#(W=8)`), since
  nothing can evaluate them.
- `sv:instance-diagram` draws their type with a **dotted** border.
- The database records them as `state: unresolved`, with the connections
  written at the instantiation site.

A UVM component whose class is not available is handled by `sv_uvm_blackbox`
instead (see {doc}`uvm-testbench`).

## Stub sources: `sv_external_sources`

When you have a header, a package or a port-only stub of the component, let the
build read it but mark everything it declares as someone else's:

```python
sv_external_sources = ["vip/axi_vip_mst.sv"]          # each path is its own origin
sv_external_sources = {"axi_vip": ["vip/*.sv"]}       # or name the origin
```

Paths and globs are relative to `conf.py`. The files are parsed with the
project (once, even if a source directory also holds them), so their
declarations resolve, ports have directions, and types check. Then:

- every object they declare carries the `external` flag and the origin label
  in the database;
- an instance of a module they define is `state: external`: the instance tree
  shows ` (external)`, and the diagram draws its type with a **dashed** border.

## External databases: `role: external`

The most complete description is a database of the component, made by whoever
has its sources or its documentation. List it in `sv_databases` with the
`external` role:

```python
sv_external = ["axi_vip_*"]
sv_databases = [{"path": "_db/axi_vip.svdb", "role": "external"}]
```

An external database is the same format as any other (see {doc}`database`), but
its objects are not documented in your project: no `autosv*` directive reads
them, and they are not in your index. They serve two purposes.

**Links.** A reference to a name the project does not define (in an instance
tree, a signature, or `` :sv:module:`axi_vip_mst` ``) links to the component's
documentation when exactly one object of that name is in an external database.
The URL is, in order:

1. the object's own `url`;
2. the header's `docs.url_template`, with `{name}`, `{qname}`, `{kind}` and
   `{anchor}` filled (`{anchor}` is `sv-` and the qualified name with `::`
   replaced by `-`, the anchor this extension gives its own objects).

Both are relative to the header's `docs.base_url`. With neither, the name is
not linked by the database.

**Ports on diagram edges.** For an instance of a module, interface or program
that is not in the build, the diagram edge to it lists the definition's ports
by direction, taken from the database's `port` objects (`detail.dir`):

```text
u_mst
in: aclk, aresetn
out: awaddr
```

All of the definition's ports are listed, not only the ones the instance
connects.

### Writing one by hand

A vendor or another tool can write the database as NDJSON and import it with
`svdb import`. A minimal description of two VIP modules:

```json
{"r":"header","format":"svdb","schema":"1.0","producer":{"name":"vip docs"},"role":"external","origin":"axi_vip","docs":{"base_url":"https://vip.example/axi/","url_template":"sv/{kind}/{name}.html#{anchor}"},"sections":{"files":"partial","objects":"partial","docs":"absent"}}
{"r":"object","kind":"module","ns":"design","qname":"axi_vip_mst","name":"axi_vip_mst","pos":0}
{"r":"object","kind":"port","ns":"design","qname":"axi_vip_mst::aclk","name":"aclk","parent":"axi_vip_mst","pos":0,"detail":{"dir":"input"}}
{"r":"object","kind":"port","ns":"design","qname":"axi_vip_mst::aresetn","name":"aresetn","parent":"axi_vip_mst","pos":1,"detail":{"dir":"input"}}
{"r":"object","kind":"port","ns":"design","qname":"axi_vip_mst::awaddr","name":"awaddr","parent":"axi_vip_mst","pos":2,"detail":{"dir":"output"}}
{"r":"object","kind":"module","ns":"design","qname":"axi_vip_slv","name":"axi_vip_slv","pos":1,"url":"slave.html"}
```

```console
$ svdb validate axi_vip.ndjson
$ svdb import axi_vip.ndjson -o _db/axi_vip.svdb
```

Here `axi_vip_mst` links to
`https://vip.example/axi/sv/module/axi_vip_mst.html#sv-axi_vip_mst` and its
diagram edges list its ports; `axi_vip_slv` links to
`https://vip.example/axi/slave.html`.

### Publishing one from a VIP's own documentation

A component documented with this extension can publish a database next to its
HTML, for its users to list as external:

```console
$ svdb build --sphinx-conf vip/docs/conf.py -o axi_vip.svdb
$ svdb export axi_vip.svdb -o axi_vip.ndjson
```

`svdb build` does not know where the HTML will be served, so add the `docs`
member (`base_url`, `url_template`) to the header line of the exported NDJSON,
then `svdb import` it. If the VIP's documentation also publishes a Sphinx
inventory, `sphinx.ext.intersphinx` gives exact links to its pages and the
database adds the ports.

A VIP's database also describes its UVM classes, each on its own, so
`svdb uvm-tree -d tb.svdb -d axi_vip.svdb` expands the VIP's agents inside the
testbench's tree, with the testbench's factory overrides applied inside them.
Classes are matched by qualified name; one that two databases describe
differently is taken from the first and reported
([Several databases](uvm-tree-several)).

## URL templates: `sv_external_docs`

For a component with documentation but no database, map name patterns to URL
templates:

```python
sv_external_docs = {
    "axi_vip_*": "https://vip.example/axi/{name}.html",
}
```

`{name}`, `{qname}`, `{kind}` and `{anchor}` are filled as above. A pattern
matches the name as written or its last segment (`axi_pkg::axi_vip_cfg` matches
`axi_vip_*`). The first matching pattern wins.

## Which link wins

A reference to a SystemVerilog name is resolved in this order:

1. an object documented in this project (its sources or a `role: local`
   database);
2. an object in a `role: external` database;
3. intersphinx inventories;
4. `sv_external_docs` templates;
5. otherwise plain text. An explicit typed role (`` :sv:class:`x` ``) warns
   that it cannot be resolved; names in generated content (instance trees,
   signatures) do not.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `sv_external` | `[]` | Glob patterns of names defined outside the sources: no "unknown" warning, instances kept as unresolved. |
| `sv_external_sources` | `[]` | Stub or header sources parsed with the project but flagged external: a list of paths/globs (relative to `conf.py`), or `{origin: [paths]}`. |
| `sv_databases` | `[]` | `{"path": ..., "role": "external"}` entries add link targets and diagram ports. |
| `sv_external_docs` | `{}` | `{glob: url_template}` for components documented elsewhere. |
