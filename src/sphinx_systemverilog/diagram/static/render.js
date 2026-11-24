// Render a laid-out ELK graph (from sphinx_systemverilog.diagram.elk, with
// shapeCoords and edgeCoords ROOT) as an SVG string.
//
// Builds a string rather than DOM nodes, so the same function runs at build
// time (mini-racer or node) and in the browser.  Colours are not set here:
// every element carries a class, and sv-diagram.css maps the classes to
// theme colours, light and dark.
//
// Custom properties read from the graph (see elk.py): a node's cls, href and
// title; a port's kind and title; an edge's kind, conditional, title and
// group (the hyperedge it was split from); a label's style (name, sub, port,
// edge).
(function (root) {
  "use strict";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Class-safe form of a free-form kind.
  function kindClass(k) {
    return String(k || "wire").toLowerCase().replace(/[^a-z0-9_-]/g, "_");
  }

  function num(v) {
    return Math.round(v * 10) / 10;
  }

  // Kinds drawn without an arrowhead: undirected connections.
  const PLAIN = { wire: true, intf: true };

  function render(g, opts) {
    opts = opts || {};
    const pre = esc(opts.idPrefix || "svd");
    const out = [];
    const W = Math.ceil(g.width || 0), H = Math.ceil(g.height || 0);
    const label = opts.label ? ` role="img" aria-label="${esc(opts.label)}"` : "";
    out.push(`<svg xmlns="http://www.w3.org/2000/svg" class="svd" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"${label}>`);

    const kinds = new Set();
    (function collect(n) {
      for (const e of n.edges || []) kinds.add(kindClass(e.kind));
      for (const c of n.children || []) collect(c);
    })(g);
    out.push("<defs>");
    for (const k of Array.from(kinds).sort()) {
      if (PLAIN[k]) continue;
      out.push(`<marker id="${pre}-ah-${k}" viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="ah k-${k}"/></marker>`);
    }
    out.push("</defs>");

    function text(l, anchor, x) {
      const style = l.style || "port";
      return `<text x="${num(x)}" y="${num(l.y + l.height * 0.8)}" text-anchor="${anchor}" class="t-${style}">${esc(l.text)}</text>`;
    }

    function node(n) {
      const isCont = !!(n.children && n.children.length);
      const cls = n.cls || (isCont ? "cont" : "leaf");
      const tip = n.title || (n.labels || []).map(l => l.text).join(" : ");
      let s = `<g class="box ${esc(cls)}">`;
      // The link covers the box and its title, not the ports.
      let face = `<rect x="${num(n.x)}" y="${num(n.y)}" width="${num(n.width)}" height="${num(n.height)}" rx="${isCont ? 6 : 3}"><title>${esc(tip)}</title></rect>`;
      for (const l of n.labels || []) face += text(l, "middle", l.x + l.width / 2);
      s += n.href ? `<a href="${esc(n.href)}">${face}</a>` : face;
      for (const p of n.ports || []) {
        const ptip = p.title ? `<title>${esc(p.title)}</title>` : "";
        s += `<rect x="${num(p.x)}" y="${num(p.y)}" width="${p.width}" height="${p.height}" class="port k-${kindClass(p.kind)}">${ptip}</rect>`;
        for (const l of p.labels || []) {
          // Port labels sit inside the box: left-aligned on the west side,
          // right-aligned on the east.
          const side = (p.layoutOptions || {})["elk.port.side"];
          const anchor = side === "EAST" ? "end" : side === "WEST" ? "start" : "middle";
          let x = anchor === "start" ? l.x : anchor === "end" ? l.x + l.width : l.x + l.width / 2;
          let ll = l;
          if (isCont && anchor !== "middle") {
            // ELK puts a container's port labels below the port, where they
            // drift away from it.  Draw them just above it, inside the border:
            // level with it they would sit on the wire that runs inside.
            x = anchor === "start" ? p.x + 2 : p.x + p.width - 2;
            ll = Object.assign({}, l, { y: p.y - 1 - l.height * 0.8 });
          }
          s += text(ll, anchor, x);
        }
      }
      s += "</g>";
      if (isCont) for (const c of n.children) s += node(c);
      return s;
    }
    for (const c of g.children || []) out.push(node(c));

    // Junction dots where the edges of one split hyperedge (same "group")
    // part company: a bend of one path that lies on a sibling path, where the
    // path's next leg leaves the sibling.  Found from either side, so a
    // sibling that runs straight on past the bend still gets its dot.
    const paths = {}, elkDots = {};
    (function collectPaths(n) {
      for (const e of n.edges || []) {
        if (!e.group) continue;
        (elkDots[e.group] = elkDots[e.group] || []).push(...(e.junctionPoints || []));
        for (const sec of e.sections || [])
          (paths[e.group] = paths[e.group] || []).push(
            [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint]);
      }
      for (const c of n.children || []) collectPaths(c);
    })(g);
    function onSeg(p, a, b) {
      const eps = 0.5;
      if (Math.min(a.x, b.x) - eps > p.x || p.x > Math.max(a.x, b.x) + eps) return false;
      if (Math.min(a.y, b.y) - eps > p.y || p.y > Math.max(a.y, b.y) + eps) return false;
      return Math.abs((b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)) <=
        eps * Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y), 1);
    }
    function onPath(p, pts) {
      for (let i = 1; i < pts.length; i++) if (onSeg(p, pts[i - 1], pts[i])) return true;
      return false;
    }
    const junctions = {};
    for (const grp of Object.keys(paths)) {
      const ps = paths[grp], seen = new Set(), dots = [];
      // ELK reports some of them itself, on one edge or several.
      for (const b of elkDots[grp]) {
        const key = `${num(b.x)},${num(b.y)}`;
        if (!seen.has(key)) { seen.add(key); dots.push(b); }
      }
      ps.forEach((a, i) => {
        for (let k = 1; k < a.length - 1; k++) {
          const b = a[k], nxt = a[k + 1];
          const mid = { x: (b.x + nxt.x) / 2, y: (b.y + nxt.y) / 2 };
          const split = ps.some((o, j) => j !== i && onPath(b, o) && !onPath(mid, o));
          const key = `${num(b.x)},${num(b.y)}`;
          if (split && !seen.has(key)) { seen.add(key); dots.push(b); }
        }
      });
      junctions[grp] = dots;
    }
    const dotted = new Set();

    function edges(n) {
      for (const e of n.edges || []) {
        const k = kindClass(e.kind);
        const arrow = PLAIN[k] ? "" : ` marker-end="url(#${pre}-ah-${k})"`;
        const cls = `e k-${k}${e.conditional ? " cond" : ""}`;
        const tip = e.title ? `<title>${esc(e.title)}</title>` : "";
        out.push(`<g class="${cls}">`);
        for (const sec of e.sections || []) {
          const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
          const d = "M" + pts.map(p => `${num(p.x)},${num(p.y)}`).join(" L");
          out.push(`<path d="${d}"${arrow}>${tip}</path>`);
        }
        let js = e.group ? [] : e.junctionPoints || [];
        if (e.group && !dotted.has(e.group)) {
          dotted.add(e.group);
          js = junctions[e.group];
        }
        for (const j of js)
          out.push(`<circle cx="${num(j.x)}" cy="${num(j.y)}" r="2.5" class="j"/>`);
        for (const l of e.labels || []) out.push(text(l, "start", l.x));
        out.push("</g>");
      }
      for (const c of n.children || []) edges(c);
    }
    edges(g);
    out.push("</svg>");
    return out.join("");
  }

  root.svDiagramSvg = render;
  if (typeof module !== "undefined" && module.exports) module.exports = render;
})(typeof globalThis !== "undefined" ? globalThis : this);
