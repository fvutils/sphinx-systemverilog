# Linking against a VIP's database

A testbench uses a VIP: it imports the VIP's package, extends its classes,
instantiates its interface and includes its macros. Normally the VIP's sources
have to be part of the build for any of that to compile. With *linking*, the
build uses the VIP's database instead. The VIP is parsed once, by whoever has
its sources, and every testbench that uses it links against the result.

```console
$ svdb build --build-unit vip/axi_vip.sv -I vip -o axi_vip.svdb      # once, with the VIP's sources
$ svdb build --build-unit tb/tb.sv --link axi_vip.svdb -o tb.svdb    # without them
$ svdb uvm-tree -d tb.svdb -d axi_vip.svdb                           # the same tree as one build of both
```

## What linking does

When the testbench uses a name its sources do not define (`import
axi_vip_pkg::*`, `axi_if bus (...)`, `` `include "axi_macros.svh" ``), and a
linked database does define it, the compile gets that name's *declarations*
from the database:

* packages: parameters, typedefs, classes with their properties, method
  prototypes and constructors, functions and tasks;
* interfaces and modules: parameters, ports, modports, clocking blocks,
  typedefs, functions and tasks;
* include files: the `` `define ``s the database recorded from them.

Bodies, constraints, covergroups and assertions are not included. Anything
the testbench can check when it compiles comes from the database exactly:
signatures, types, parameter values and port lists. So a testbench that
overrides a VIP method with the wrong argument type gets the same error it
would get with the VIP's sources.

A linked database also brings what the named package or definition needs:
the packages it imports and the interfaces its types name.

## What the testbench's database holds

Nothing of the VIP. The testbench's database has no objects, UVM records or
elaborations for linked declarations. Its references keep the VIP's qualified
names (`vip_pkg::vip_driver`), and its header records what it was linked
against:

```json
"links": [{"origin": "axi_vip", "path": "/proj/_db/axi_vip.svdb", "hash": "…",
           "units": ["axi_if", "axi_types_pkg", "axi_vip_pkg"], "includes": ["axi_macros.svh"]}]
```

Open both databases to read across them. The UVM tree is stitched from both,
with the testbench's factory overrides applied to the VIP's components:

```console
$ svdb uvm-tree -d tb.svdb -d axi_vip.svdb
$ svdb uvm-tree -d tb.svdb --follow-links         # opens axi_vip.svdb from the header
```

## Rules

* **A source always wins.** A name the testbench's sources define is never
  linked, even when a linked database also has it. If the testbench parses
  `uvm_pkg`, `uvm_pkg` comes from the sources.
* **The first database wins.** With several `--link` databases, a name comes
  from the first one that defines it.
* **Only complete databases are linked.** A database whose `objects` section
  is not `complete` (for example, a vendor's hand-written one) is not linked:
  it could leave out ports or members, and the compile would then report
  errors that are not real. Use it for links only (see {doc}`external`).
* **`$unit` declarations cannot be linked.** A class or typedef declared
  outside any package is not recorded, so a VIP interface that uses one
  cannot be linked whole. The build warns about this, naming the database.

## Relinking

A testbench's database is tied to the VIP database it was linked against.
When the VIP's database is rebuilt, the testbench's database must be rebuilt
too:

* opening both warns: `tb.svdb was linked against a different axi_vip`;
* `svdb stats tb.svdb` lists each link and its state;
* the Sphinx cache includes each linked database's content, so a Sphinx build
  relinks by itself.

## In a Sphinx project

Every `sv_databases` entry is linked by default:

```python
sv_build_units = ["tb/tb.sv"]
sv_databases = [{"path": "_db/axi_vip.svdb", "role": "external"}]
```

Two settings answer two different questions:

* **`link`** (default `True`) decides whether the compile may use the
  database. A linked declaration is not part of your project's database, so
  you no longer need to list the VIP in `sv_external_sources`.
* **`role`** decides where the VIP's pages are. Use `local` to document them
  in this project, or `external` to link out to documentation elsewhere.

The UVM testbench views read every linked database, whatever its role, so
`sv:uvm-tree` with `:resolved:` expands the VIP's agent even when the VIP is
`external`.

Set `"link": False` for a database that must not satisfy the compile, such as
one built with different defines, or an older VIP version kept only for its
documentation.

## Settings

| Setting | Meaning |
|---|---|
| `svdb build --link DB` | Link against *DB* (repeat; the first that defines a name wins). |
| `svdb uvm-tree --follow-links` | Also open the databases the given ones were linked against. |
| `sv_databases` entry `link` | `True` (default): the sources link against it. `False`: they don't. |
