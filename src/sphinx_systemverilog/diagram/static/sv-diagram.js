// The interactive layer over the inline SVG diagrams (see render.js).
//
// Everything works on the static SVG written at build time:
//   - click a wire, or a port, to highlight its net end to end and fade the
//     rest; shift-click adds to the highlight; click the background or press
//     Escape to clear it;
//   - zoom with the toolbar or ctrl+wheel, and drag the background to pan.
// Diagrams with bundles also embed their unlaid ELK graph (a
// <script type="application/json" class="svd-graph">): double-click a bundle
// to expand it into its signals, double-click a signal to fold it back.  That
// lays the diagram out again here, with elkjs loaded on first use and the
// same render.js that drew it at build time.
//
// svDiagramExpand and svDiagramSizeLeaf don't touch the DOM, so the tests
// run them in mini-racer.
(function (root) {
  "use strict";

  // Must match ROW, MIN_W and MIN_H in elk.py.
  const ROW = 18, MIN_W = 70, MIN_H = 36;

  function side(p) {
    return (p.layoutOptions || {})["elk.port.side"];
  }

  function labelWidth(o) {
    return o && o.labels && o.labels.length ? o.labels[0].width : 0;
  }

  // Size a leaf and fix its port positions, as _size_leaf in elk.py does.
  function sizeLeaf(n) {
    const head = (n.labels || []).length > 1 ? 34 : 22;
    const west = n.ports.filter(p => side(p) === "WEST");
    const east = n.ports.filter(p => side(p) === "EAST");
    const lw = Math.max(0, ...west.map(labelWidth));
    const rw = Math.max(0, ...east.map(labelWidth));
    const tw = Math.max(...(n.labels || []).map(l => l.width), 0);
    n.width = Math.max(MIN_W, tw + 16, lw + rw + 34);
    n.height = Math.max(MIN_H, head + Math.max(west.length, east.length, 1) * ROW + 6);
    n.layoutOptions["elk.nodeSize.constraints"] = "[]";
    n.layoutOptions["elk.portConstraints"] = "FIXED_POS";
    const row = { WEST: 0, EAST: 0 };
    for (const p of n.ports) {
      const s = side(p);
      p.x = s === "WEST" ? -4 : n.width - 4;
      p.y = head + 5 + row[s] * ROW;
      row[s] += 1;
      if (p.labels && p.labels.length) {
        const w = p.labels[0].width;
        Object.assign(p.labels[0], { x: s === "WEST" ? 12 : -w - 4, y: -2 });
      }
    }
    return n;
  }

  // A copy of the unlaid graph *g* with the bundles named in *ids* replaced
  // by their member edges.  Each member port is added to its box next to the
  // bundle's own port there, and a bundle port no edge uses any more is
  // dropped.  Boxes that change are sized again.
  function expand(g, ids) {
    g = JSON.parse(JSON.stringify(g));
    const plan = g.expand || {};
    delete g.expand;
    const boxes = {}, owner = {}, holders = [];
    (function walk(n) {
      boxes[n.id] = n;
      for (const p of n.ports || []) owner[p.id] = n;
      if ((n.edges || []).length) holders.push(n);
      for (const c of n.children || []) walk(c);
    })(g);
    const changed = new Set(), freed = new Set();
    for (const bid of Array.from(ids).sort()) {
      const step = plan[bid];
      if (!step) continue;
      let into = null;
      for (const h of holders) {
        const keep = [];
        for (const e of h.edges) {
          if (e.bundle === bid) {
            into = h;
            for (const end of [...e.sources, ...e.targets]) freed.add(end);
          } else keep.push(e);
        }
        h.edges = keep;
      }
      if (!into) continue;
      for (const { box, port } of step.ports) {
        const n = boxes[box];
        if (!n || owner[port.id]) continue;
        const p = JSON.parse(JSON.stringify(port));
        let at = n.ports.findIndex(q => freed.has(q.id) && side(q) === side(p));
        at = at < 0 ? n.ports.length : at + 1;
        // after any member ports already placed behind that bundle port
        while (at < n.ports.length && n.ports[at].added && side(n.ports[at]) === side(p)) at++;
        p.added = true;
        n.ports.splice(at, 0, p);
        owner[p.id] = n;
        changed.add(n);
      }
      into.edges.push(...JSON.parse(JSON.stringify(step.edges)));
    }
    const used = new Set();
    for (const h of holders)
      for (const e of h.edges) for (const end of [...e.sources, ...e.targets]) used.add(end);
    for (const id of freed) {
      const n = owner[id];
      if (!n || used.has(id)) continue;
      n.ports = n.ports.filter(p => p.id !== id);
      changed.add(n);
    }
    for (const n of changed) {
      n.ports.forEach((p, i) => {
        delete p.added;
        p.layoutOptions["elk.port.index"] = String(i);
      });
      if (n.layoutOptions && n.layoutOptions["elk.portConstraints"] === "FIXED_POS") sizeLeaf(n);
    }
    return g;
  }

  root.svDiagramExpand = expand;
  root.svDiagramSizeLeaf = sizeLeaf;
  if (typeof module !== "undefined" && module.exports) module.exports = { expand, sizeLeaf };

  if (typeof document === "undefined") return;

  // ------------------------------------------------------------------ browser

  const here = document.currentScript && document.currentScript.src;
  const base = here ? here.replace(/[^/]*$/, "") : "_static/";
  let elk = null;

  function loadElk() {
    if (!elk) {
      elk = new Promise((resolve, reject) => {
        if (root.ELK) return resolve(new root.ELK());
        const s = document.createElement("script");
        s.src = base + "sv-diagram-elk.js";
        s.onload = () => resolve(new root.ELK());
        s.onerror = () => { elk = null; reject(new Error("could not load " + s.src)); };
        document.head.appendChild(s);
      });
    }
    return elk;
  }

  function button(text, title, act) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", ev => { ev.stopPropagation(); act(); });
    return b;
  }

  function enhance(div) {
    let svg = div.querySelector("svg.svd");
    if (!svg || div.classList.contains("svd-live")) return;
    const data = div.querySelector("script.svd-graph");
    const graph = data ? JSON.parse(data.textContent) : null;
    const prefix = div.getAttribute("data-prefix") || "svd";
    const label = svg.getAttribute("aria-label") || "";
    const original = svg;
    const expanded = new Set();
    let scale = 1, nets = new Set();

    div.classList.add("svd-live");
    const view = document.createElement("div");
    view.className = "svd-view";
    div.insertBefore(view, svg);
    view.appendChild(svg);

    const tools = document.createElement("div");
    tools.className = "svd-tools";
    const fold = button("Collapse", "Fold every expanded bundle back", () => {
      expanded.clear();
      relayout();
    });
    fold.hidden = true;
    tools.append(
      button("+", "Zoom in", () => zoom(scale * 1.25)),
      button("−", "Zoom out", () => zoom(scale / 1.25)),
      button("Fit", "Fit the diagram to the frame", fit),
      button("1:1", "Actual size", () => zoom(1)),
      fold);
    div.insertBefore(tools, view);

    function size() {
      const vb = svg.viewBox.baseVal;
      return { w: vb.width, h: vb.height };
    }

    // Zoom about a point of the frame (its centre by default).
    function zoom(s, cx, cy) {
      s = Math.min(4, Math.max(0.1, s));
      const { w, h } = size();
      if (cx === undefined) { cx = view.clientWidth / 2; cy = view.clientHeight / 2; }
      const fx = (view.scrollLeft + cx) / scale, fy = (view.scrollTop + cy) / scale;
      scale = s;
      svg.setAttribute("width", Math.round(w * s));
      svg.setAttribute("height", Math.round(h * s));
      view.scrollLeft = fx * s - cx;
      view.scrollTop = fy * s - cy;
    }

    function fit() {
      const { w, h } = size();
      const maxH = parseFloat(getComputedStyle(view).maxHeight) || window.innerHeight * 0.8;
      zoom(Math.min(view.clientWidth / w, maxH / h, 4), 0, 0);
    }

    function hitAreas() {
      // Thin wires are hard to click: give each a wide transparent twin.
      for (const p of svg.querySelectorAll("g.e > path:not(.hit)")) {
        const hit = p.cloneNode(true);
        hit.removeAttribute("marker-end");
        hit.setAttribute("class", "hit");
        p.parentNode.insertBefore(hit, p);
      }
    }

    function highlight(set) {
      nets = set;
      const ends = new Set();
      for (const e of svg.querySelectorAll("g.e")) {
        const on = nets.has(e.getAttribute("data-net"));
        e.classList.toggle("hl", on);
        if (on) for (const x of e.getAttribute("data-ends").split(" ")) ends.add(x);
      }
      for (const p of svg.querySelectorAll("[data-port]"))
        p.classList.toggle("hl", ends.has(p.getAttribute("data-port")));
      svg.classList.toggle("focus", nets.size > 0);
    }

    function netsAt(target) {
      const e = target.closest("g.e");
      if (e) return [e.getAttribute("data-net")];
      const p = target.closest("[data-port]");
      if (!p) return null;
      const id = p.getAttribute("data-port"), found = [];
      for (const g of svg.querySelectorAll("g.e"))
        if (g.getAttribute("data-ends").split(" ").includes(id)) found.push(g.getAttribute("data-net"));
      return found;
    }

    function relayout() {
      fold.hidden = expanded.size === 0;
      if (!expanded.size) return swap(original);
      div.classList.add("svd-busy");
      loadElk()
        .then(e => e.layout(root.svDiagramExpand(graph, expanded)))
        .then(laid => {
          const t = document.createElement("template");
          t.innerHTML = root.svDiagramSvg(laid, { idPrefix: prefix, label });
          swap(t.content.firstElementChild);
          hitAreas();
        })
        .catch(err => { console.error("sv-diagram:", err); })
        .finally(() => div.classList.remove("svd-busy"));
    }

    function swap(next) {
      if (next !== svg) view.replaceChild(next, svg);
      svg = next;
      const keep = nets;
      zoom(scale);
      highlight(keep);
    }

    // Pan by dragging the background; a drag doesn't count as a click.
    let drag = null, dragged = false;
    view.addEventListener("pointerdown", ev => {
      if (ev.button !== 0 || ev.target.closest("a, g.e, [data-port]")) return;
      drag = { x: ev.clientX, y: ev.clientY, l: view.scrollLeft, t: view.scrollTop };
      dragged = false;
    });
    view.addEventListener("pointermove", ev => {
      if (!drag) return;
      const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
      if (!dragged && Math.abs(dx) + Math.abs(dy) < 4) return;
      if (!dragged) { dragged = true; view.setPointerCapture(ev.pointerId); view.classList.add("panning"); }
      view.scrollLeft = drag.l - dx;
      view.scrollTop = drag.t - dy;
    });
    const stop = () => { drag = null; view.classList.remove("panning"); };
    view.addEventListener("pointerup", stop);
    view.addEventListener("pointercancel", stop);

    view.addEventListener("wheel", ev => {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      const r = view.getBoundingClientRect();
      zoom(scale * Math.exp(-ev.deltaY / 300), ev.clientX - r.left, ev.clientY - r.top);
    }, { passive: false });

    view.addEventListener("click", ev => {
      if (dragged) { dragged = false; return; }
      if (ev.target.closest("a")) return;
      const found = netsAt(ev.target);
      if (!found) return highlight(new Set());
      const next = ev.shiftKey ? new Set(nets) : new Set();
      for (const n of found) next.add(n);
      highlight(next);
    });

    view.addEventListener("dblclick", ev => {
      if (!graph) return;
      const e = ev.target.closest("g.e");
      if (!e) return;
      const b = e.getAttribute("data-bundle"), m = e.getAttribute("data-member");
      if (b && !expanded.has(b)) expanded.add(b);
      else if (m && expanded.has(m)) expanded.delete(m);
      else return;
      ev.preventDefault();
      highlight(new Set());
      relayout();
    });

    div.svDiagram = { highlight: s => highlight(new Set(s)), zoom, fit,
                      expand: id => { expanded.add(id); relayout(); } };
    hitAreas();
  }

  function start() {
    for (const div of document.querySelectorAll("div.sv-diagram")) enhance(div);
  }

  document.addEventListener("keydown", ev => {
    if (ev.key !== "Escape") return;
    for (const div of document.querySelectorAll("div.svd-live"))
      if (div.svDiagram) div.svDiagram.highlight([]);
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof globalThis !== "undefined" ? globalThis : this);
