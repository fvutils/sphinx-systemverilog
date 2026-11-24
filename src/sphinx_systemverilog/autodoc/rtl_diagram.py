"""RTL block diagrams: one module's child instances and the nets between them.

:func:`build_block_diagram` reads the svdb database (ports, instances and
their connections) and returns a :class:`~sphinx_systemverilog.diagram.Diagram`
for ``sv:block-diagram``.  One level only: each child instance is a box, the
module's own ports sit on the root's border, and a net becomes an edge from
the port that drives it to the ports that read it.

Two ways to draw the connections:

* **nets**: one port per connected formal port, one edge per net.
* **bundled**: every net from one block to another is merged into one bus.
  A block has a single output port; each block it reads from gets one input
  port, labelled with the source and the bus's signal count and width.  The
  module itself counts as a block: one port for its inputs, one per source
  for its outputs.  This
  is what keeps a CVA6-sized module readable (see
  ``docs/design/block-diagram-layout.md``).

``auto`` (the default) uses nets while the diagram stays small.

Widths come from the declared type text (``logic [31:0]``) when its ranges
are constant; svdb stores no elaborated widths, so a parameterized range is
counted as unknown.  Nets driven by ``assign`` statements or processes in the
module are invisible to svdb: their readers get an unconnected input, and the
diagram's notes count them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from ..diagram import Diagram

#: Clock and reset nets, hidden by default: they reach every block and say
#: nothing about the dataflow.
DEFAULT_HIDE = r"^(clk|clock|rst|reset)\w*$|^\w*_(clk|clock|rst|rst_n|rstn|reset|reset_n)$"

#: ``auto`` switches to bundled above this many per-net edges.
AUTO_MAX_NETS = 40

MODES = ("auto", "nets", "bundled")

ROOT = "@root"

_SIDE = {"input": "WEST", "output": "EAST", "inout": "SOUTH", "ref": "SOUTH"}

_ATOM_WIDTH = {"bit": 1, "logic": 1, "reg": 1, "wire": 1, "byte": 8, "shortint": 16,
               "int": 32, "integer": 32, "longint": 64, "time": 64}
_ARITH = re.compile(r"^[\d\s+\-*/()]+$")
_RANGE = re.compile(r"\[([^\]:]+):([^\]]+)\]")


def type_width(text: str | None) -> int | None:
    """Bit width of a declared type, or None when it isn't constant.

    ``logic [31:0]`` is 32, ``logic [3:0][7:0]`` 32, ``int`` 32; a range over
    a parameter, a typedef or a struct is unknown.
    """
    if not text:
        return 1
    words = re.sub(r"\[.*?\]", " ", text).split()
    words = [w for w in words if w not in ("signed", "unsigned", "var", "wire", "tri")] \
        or ["logic"]
    base = _ATOM_WIDTH.get(words[0])
    if base is None or len(words) > 1:
        return None
    width = base
    for lo, hi in _RANGE.findall(text):
        a, b = _const(lo), _const(hi)
        if a is None or b is None:
            return None
        width *= abs(a - b) + 1
    return width


def _const(expr: str) -> int | None:
    expr = expr.strip()
    if not _ARITH.match(expr):
        return None
    try:
        return int(eval(expr, {"__builtins__": {}}, {}))  # digits and + - * / only
    except Exception:
        return None


@dataclass
class _End:
    """One end of a net: a formal port of an instance, or a module port."""

    owner: str              # instance name, or ROOT
    port: str
    dir: str                # input/output/inout/"" (unknown)
    width: int | None
    intf: str = ""          # interface name for an interface port


@dataclass
class _Net:
    name: str
    drivers: list[_End] = field(default_factory=list)
    loads: list[_End] = field(default_factory=list)
    intf: str = ""

    @property
    def width(self) -> int | None:
        for e in self.drivers + self.loads:
            if e.width is not None:
                return e.width
        return None


@dataclass
class _Inst:
    name: str
    type_name: str
    path: str = ""          # generate scope, ``g_wide`` or ``g_lane[0]``
    count: int = 1
    state: str = "ok"
    ports: list[_End] = field(default_factory=list)


@dataclass
class BlockModel:
    """The connectivity of one module, before it is drawn."""

    module: str
    ports: list[_End] = field(default_factory=list)
    instances: list[_Inst] = field(default_factory=list)
    nets: dict[str, _Net] = field(default_factory=dict)
    hidden: list[str] = field(default_factory=list)
    #: Nets read by an instance or a module output with no driver svdb can see
    #: (an ``assign`` or a process in the module).
    undriven: list[str] = field(default_factory=list)


def _dir(port_obj: Any, conn_dir: str | None) -> str:
    if conn_dir:
        return conn_dir
    if port_obj is not None:
        return port_obj.detail.get("dir") or ""
    return ""


def _intf(port_obj: Any) -> str:
    if port_obj is None:
        return ""
    ref = port_obj.detail.get("interface")
    if not ref:
        return ""
    name = (ref.get("ref") or {}).get("name") or "interface"
    return f"{name}.{ref['modport']}" if ref.get("modport") else name


def _type_text(obj: Any) -> str | None:
    if obj is None:
        return None
    return (obj.detail.get("type") or {}).get("text")


def collect(db: Any, module: Any, hide: str | None = DEFAULT_HIDE) -> BlockModel:
    """Read *module*'s ports, instances and nets from the database *db*."""
    hide_re = re.compile(hide) if hide else None
    model = BlockModel(module.name)
    prefix = module.qname + "::"

    def net(key: str, name: str) -> _Net | None:
        if hide_re and hide_re.search(name):
            if name not in model.hidden:
                model.hidden.append(name)
            return None
        return model.nets.setdefault(key, _Net(name))

    last_dir = ""
    for p in db.members(module, ["port"]):
        intf = _intf(p)
        # ``input a, b``: svdb records the direction on ``a`` only.
        d = "" if intf else (p.detail.get("dir") or last_dir)
        last_dir = d or last_dir
        end = _End(ROOT, p.name, d, None if intf else type_width(_type_text(p)), intf)
        n = net(p.qname, p.name)
        if n is None:
            continue
        model.ports.append(end)
        n.intf = n.intf or intf
        # Seen from inside, a module input drives its net and an output reads it.
        if d == "input":
            n.drivers.append(end)
        elif d in ("output", "inout") or intf:
            n.loads.append(end)

    for inst in sorted(db.instances(module), key=lambda o: o.pos):
        rel = inst.qname[len(prefix):] if inst.qname.startswith(prefix) else inst.name
        scope = rel.rsplit("::", 1)[0] if "::" in rel else ""
        array = inst.detail.get("array") or {}
        it = _Inst(inst.name, (inst.detail.get("of") or {}).get("name", "?"), scope,
                   int(array.get("count") or 1), inst.detail.get("state") or "ok")
        model.instances.append(it)
        for c in db.connections(inst):
            if c.port is None:          # positional or the ``.*`` marker itself
                continue
            intf = _intf(c.port_object)
            d = _dir(c.port_object, c.dir)
            end = _End(it.name, c.port, d,
                       None if intf else type_width(_type_text(c.port_object)), intf)
            sigs = [s for s in c.signals if getattr(s, "qname", None)]
            if not sigs:
                continue                # unconnected, or tied to a constant
            shown = False
            for s in sigs:
                n = net(s.qname, s.name)
                if n is None:
                    continue
                shown = True
                n.intf = n.intf or intf
                if d == "output":
                    n.drivers.append(end)
                else:
                    n.loads.append(end)
            if shown:
                it.ports.append(end)

    for key, n in model.nets.items():
        if n.loads and not n.drivers and not n.intf:
            model.undriven.append(n.name)
    return model


def _edge_count(model: BlockModel) -> int:
    return sum(1 for n in model.nets.values() if (n.drivers and n.loads) or n.intf)


def build_block_diagram(
    model: BlockModel, mode: str = "auto", order: Iterable[str] = (),
) -> "Diagram":
    """Draw *model* as a :class:`~sphinx_systemverilog.diagram.Diagram`."""
    from ..diagram import Box, Bundle, Diagram, Edge, Port
    from ..diagram.sphinx import XREF

    if mode == "auto":
        mode = "nets" if _edge_count(model) <= AUTO_MAX_NETS else "bundled"
    order = list(order)

    def pid(owner: str, port: str) -> str:
        return f"{owner}:{port}"

    def port_title(e: _End) -> str:
        what = e.intf or e.dir or "port"
        width = f" [{e.width}]" if e.width and e.width > 1 else ""
        return f"{e.port} : {what}{width}"

    def side(e: _End, root: bool = False) -> str:
        if e.intf:
            return "WEST"
        s = _SIDE.get(e.dir, "WEST")
        if root and s in ("WEST", "EAST"):
            return s        # module inputs on the left, outputs on the right
        return s

    # In nets mode every module port is on the border, used or not.  Bundled
    # mode treats the module like any other block and adds only the ports its
    # bundles need (its interface ports stay individual).
    root_ports = [Port(pid(ROOT, e.port), e.port, side(e, True),
                       "intf" if e.intf else e.dir, title=port_title(e))
                  for e in model.ports if mode == "nets" or e.intf]
    boxes: dict[str, Box] = {}
    for it in model.instances:
        sub = it.type_name + (f" ×{it.count}" if it.count > 1 else "")
        cls = "leaf"
        if it.state != "ok":
            cls += " opaque"
            sub += f" [{it.state}]"
        boxes[it.name] = Box(
            it.name, it.name, sub, cls=cls, href=XREF + it.type_name,
            title=f"{it.name} : {it.type_name}" + (f" (in {it.path})" if it.path else ""))

    edges: list[Edge] = []
    bundles: list[Bundle] = []
    have: set[str] = {p.id for p in root_ports}

    def ensure(owner: str, port_id: str, label: str, s: str, kind: str, title: str) -> str:
        if port_id in have:
            return port_id
        have.add(port_id)
        ports = root_ports if owner == ROOT else boxes[owner].ports
        ports.append(Port(port_id, label, s, kind, title=title))
        return port_id

    def end_id(e: _End) -> str:
        return ensure(e.owner, pid(e.owner, e.port), e.port, side(e),
                      "intf" if e.intf else e.dir, port_title(e))

    for n in model.nets.values():
        if not n.intf:
            continue
        ends = n.drivers + n.loads
        if len(ends) < 2:
            continue
        src = next((e for e in ends if e.owner == ROOT), ends[0])
        tgts = [end_id(e) for e in ends if e is not src]
        edges.append(Edge(end_id(src), tgts, "intf", title=f"{n.name} : {n.intf}"))

    if mode == "nets":
        for n in model.nets.values():
            if n.intf or not n.drivers:
                continue
            if not n.loads:
                continue
            src = end_id(n.drivers[0])
            tgts = [end_id(e) for e in n.loads]
            w = n.width
            edges.append(Edge(src, tgts, "net" if (w or 1) == 1 else "bus",
                              priority=_priority(w),
                              title=f"{n.name}" + (f" [{w}]" if w and w > 1 else "")))
    else:
        # Group per (driver block, reader block), the module itself being one
        # more block: its inputs leave one port on the left, and what it reads
        # arrives at one port per source on the right.
        groups: dict[tuple[str, str], list[_Net]] = {}
        for n in model.nets.values():
            if n.intf or not n.drivers or not n.loads:
                continue
            d = n.drivers[0]
            for e in n.loads:
                if e.owner == d.owner:
                    continue
                lst = groups.setdefault((d.owner, e.owner), [])
                if n not in lst:
                    lst.append(n)
        name = {ROOT: model.module}
        for (src_key, dst), nets in groups.items():
            src_label = name.get(src_key, src_key)
            if src_key == ROOT:
                src = ensure(ROOT, pid(ROOT, "@in"), "", "WEST", "bus",
                             f"{model.module} inputs")
            else:
                src = ensure(src_key, pid(src_key, "@out"), "", "EAST", "bus",
                             f"{src_key} outputs")
            what = f"from {src_label}: " + ", ".join(n.name for n in nets)
            if dst == ROOT:
                tgt = ensure(ROOT, pid(ROOT, "@from:" + src_label),
                             _bus_label(src_label, nets), "EAST", "bus",
                             f"{model.module} outputs " + what)
            else:
                tgt = ensure(dst, pid(dst, "@from:" + src_label),
                             _bus_label(src_label, nets), "WEST", "bus", what)
            widths = [n.width for n in nets]
            total = sum(w for w in widths if w) if all(widths) else None
            if len(nets) == 1:
                n = nets[0]
                edges.append(Edge(src, [tgt], "net" if (n.width or 1) == 1 else "bus",
                                  priority=_priority(n.width), title=n.name))
                continue
            bundles.append(Bundle(
                src, [tgt],
                members=[Edge(src, [tgt], title=n.name) for n in nets],
                priority=_priority(total),
                title=f"{len(nets)} signals" + (f", {total} bits" if total else "")
                + ": " + ", ".join(n.name for n in nets)))

    # Inputs nobody drives that svdb can see: show the port, unconnected.
    undriven = set(model.undriven)
    for n in model.nets.values():
        if n.name not in undriven:
            continue
        for e in n.loads:
            if e.owner != ROOT:
                if mode == "nets":
                    end_id(e)
                else:
                    ensure(e.owner, pid(e.owner, "@logic"), "(logic)", "WEST", "nc",
                           "driven by logic in the module: " + n.name)

    children = list(boxes.values())
    if order:
        rank = {name: i for i, name in enumerate(order)}
        children = [b for _, b in sorted(enumerate(children),
                                         key=lambda x: (rank.get(x[1].id, len(rank)), x[0]))]
    root = Box(ROOT, model.module, cls="cont", ports=root_ports, children=children,
               title=model.module)
    return Diagram(root, edges=edges, bundles=bundles, model_order=bool(order))


def _priority(width: int | None) -> int:
    if not width:
        return 0
    return 10 if width >= 64 else 3 if width >= 8 else 0


def _bus_label(src: str, nets: list[_Net]) -> str:
    if len(nets) == 1:
        return nets[0].name
    widths = [n.width for n in nets]
    bits = f", {sum(widths)}b" if all(widths) else ""
    return f"{src} ({len(nets)}{bits})"
