// Finds regression estimates in a PDF, entirely in the browser (nothing is uploaded).
// Heuristic: a coefficient (optionally with stars) with a standard error in brackets directly
// below it or right after it. Table number, column, row label and N are read from the layout.
// Exposes window.RAEstimates.fromArrayBuffer(buf, {source}) -> Promise<[suggestion]>
(function () {
  var NUM = /^[-+]?(\d+)?\.\d+$|^[-+]?\d+$/;
  var COEF = /^([-+]?(?:\d+)?\.\d+|[-+]?\d+\.\d*)(\*{1,3}|†)?$/;
  var SE = /^[\(\[]([-+]?(?:\d+)?\.\d+)[\)\]]$/;
  var HEADNUM = /^\((\d{1,2})\)$/;
  var TABLE = /^(?:Table|TABLE)\s+(S?\d+[A-Za-z]?)[\.:]?/;
  var NROW = /^(observations|obs\.?|n|number of obs\.?|sample size|no\. of observations)$/i;

  function norm(s) { return s.replace(/[−–—]/g, "-").replace(/∗/g, "*").trim(); }

  function tokensOf(item) {
    var s = norm(item.str);
    if (!s) return [];
    var parts = s.split(/\s+/), out = [], x = item.x, per = item.w / Math.max(s.length, 1), pos = 0;
    parts.forEach(function (p) {
      var i = s.indexOf(p, pos);
      out.push({ t: p, x: x + i * per, w: p.length * per, y: item.y, h: item.h });
      pos = i + p.length;
    });
    return out;
  }

  function linesOf(items) {
    var toks = [];
    items.forEach(function (it) { toks = toks.concat(tokensOf(it)); });
    toks.sort(function (a, b) { return b.y - a.y || a.x - b.x; });
    var lines = [];
    toks.forEach(function (t) {
      var L = lines[lines.length - 1];
      if (L && Math.abs(L.y - t.y) <= Math.max(2.5, t.h * 0.35)) L.toks.push(t);
      else lines.push({ y: t.y, h: t.h, toks: [t] });
    });
    // superscript stars sit a little higher: move them onto the nearest line below them
    lines = lines.filter(function (L, i) {
      if (/^[\*†]+$/.test(L.toks.map(function (t) { return t.t; }).join("")) && i + 1 < lines.length && L.y - lines[i + 1].y < L.h * 0.9 + 3) {
        lines[i + 1].toks = lines[i + 1].toks.concat(L.toks); return false;
      }
      return true;
    });
    var numish = /^[-+.\d,*†]+$/;
    lines.forEach(function (L) {
      L.toks.sort(function (a, b) { return a.x - b.x; });
      // glue pieces of one number that the PDF stores separately ("-", "0", ".", "150", "**")
      var merged = [];
      L.toks.forEach(function (t) {
        var p = merged[merged.length - 1];
        var gap = p ? t.x - (p.x + p.w) : 99;
        var stars = /^(\*{1,3}|†)$/.test(t.t);
        if (p && ((numish.test(p.t) && numish.test(t.t) && gap < 2.5 && !/\*/.test(p.t)) ||
                  (stars && gap < 14 && /\d/.test(p.t) && !/\*/.test(p.t)))) {
          if (!stars) p.nw = t.x + t.w - p.x;
          p.t += t.t; p.w = t.x + t.w - p.x;
        } else { var c = Object.assign({}, t); c.nw = /^(\*{1,3}|†)$/.test(t.t) ? 0 : t.w; merged.push(c); }
      });
      L.toks = merged;
      L.text = merged.map(function (t) { return t.t; }).join(" ");
    });
    return lines;
  }

  function cx(t) { return t.x + (t.nw || t.w) / 2; }

  function analysePage(lines, state, pageNo, source) {
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var L = lines[i];
      var tm = L.text.match(TABLE);
      if (tm) { state.table = tm[1]; state.heads = null; state.title = L.text.slice(0, 120); state.nrows = []; continue; }
      var heads = L.toks.filter(function (t) { return HEADNUM.test(t.t); });
      if (heads.length >= 2 && heads.length >= L.toks.length - 1) { state.heads = heads.map(function (t) { return { n: +t.t.match(HEADNUM)[1], x: cx(t) }; }); continue; }
      var label = L.toks.filter(function (t) { return !NUM.test(t.t.replace(/\*+$/, "").replace(/,/g, "")) && !SE.test(t.t) && !/^[\*†]+$/.test(t.t); }).map(function (t) { return t.t; }).join(" ");
      if (NROW.test(label.replace(/[:.]$/, "")) && state.table) {
        L.toks.forEach(function (t) { var v = t.t.replace(/,/g, ""); if (/^\d{2,}$/.test(v)) state.nrows.push({ x: cx(t), n: v, idx: out.length }); });
        // fill N for suggestions already found in this table
        out.forEach(function (s) { if (s.table === state.table && !s.n) s.n = nearest(state.nrows, s.cx); });
        continue;
      }
      var coefs = L.toks.filter(function (t) { return COEF.test(t.t) && /\./.test(t.t); });
      if (!coefs.length) continue;
      var next = lines[i + 1];
      coefs.forEach(function (c, k) {
        var se = null;
        var after = L.toks[L.toks.indexOf(c) + 1];
        if (after && SE.test(after.t) && after.x - (c.x + c.w) < 30) se = after.t.match(SE)[1];
        else {
          // look in the next few lines below for the closest bracketed number in the same column
          var best = null, bd = 1e9;
          for (var j = i + 1; j < Math.min(lines.length, i + 4); j++) {
            var Lj = lines[j];
            if (L.y - Lj.y > Math.max(L.h, 7) * 2.6) break;
            Lj.toks.forEach(function (t) {
              if (!SE.test(t.t)) return;
              var d = Math.abs(cx(t) - cx(c));
              if (d < Math.max(24, (c.nw || c.w)) && d < bd) { bd = d; best = t; }
            });
            if (best) break;
          }
          if (best) se = best.t.match(SE)[1];
        }
        if (se === null) return;
        var m = c.t.match(COEF);
        var col = state.heads ? nearestHead(state.heads, cx(c)) : k + 1;
        var lab = label || state.lastLabel || "";
        out.push({ source: source, page: pageNo, table: state.table || null, col: col, label: lab.slice(0, 70),
                   b: m[1], stars: m[2] || "", se: se, n: "", cx: cx(c) });
      });
      if (label) state.lastLabel = label;
    }
    return out;
  }

  function nearest(arr, x) {
    var best = null, d = 1e9;
    arr.forEach(function (a) { var dd = Math.abs(a.x - x); if (dd < d) { d = dd; best = a; } });
    return best && d < 60 ? best.n : "";
  }
  function nearestHead(heads, x) {
    var best = heads[0], d = 1e9;
    heads.forEach(function (h) { var dd = Math.abs(h.x - x); if (dd < d) { d = dd; best = h; } });
    return best.n;
  }

  function finish(all) {
    // drop duplicates, give IDs and descriptions, propose a headline
    var seen = {}, out = [];
    all.forEach(function (s) {
      var key = [s.table, s.col, s.b, s.se].join("|");
      if (seen[key]) return; seen[key] = 1;
      var t = s.table ? "T" + s.table.replace(/^S/, "S") : "P" + s.page;
      s.id = (t + "c" + s.col).replace(/\s+/g, "");
      s.description = (s.table ? "Table " + s.table : "Page " + s.page) + " col " + s.col + (s.label ? ": " + s.label : "");
      out.push(s);
    });
    var occ = {};
    out.forEach(function (s) { occ[s.id] = (occ[s.id] || 0) + 1; if (occ[s.id] > 1) s.id += "r" + occ[s.id]; });
    // headline guess: first main-text table, first row, last column
    var main = out.filter(function (s) { return s.table && !/^S/.test(s.table); });
    if (main.length) {
      var t0 = main[0].table, row = main.filter(function (s) { return s.table === t0 && s.label === main[0].label; });
      var h = row.reduce(function (a, b) { return b.col > a.col ? b : a; }, row[0]);
      h.suggestedMain = true;
    }
    return out;
  }

  function fromArrayBuffer(buf, opts) {
    opts = opts || {};
    var lib = window.pdfjsLib;
    if (!lib) return Promise.reject(new Error("PDF reader not loaded"));
    return lib.getDocument({ data: new Uint8Array(buf) }).promise.then(function (pdf) {
      var all = [], state = {}, chain = Promise.resolve();
      var pages = Math.min(pdf.numPages, opts.maxPages || 80);
      for (var p = 1; p <= pages; p++) (function (p) {
        chain = chain.then(function () { return pdf.getPage(p); }).then(function (page) {
          return page.getTextContent().then(function (tc) {
            var items = tc.items.filter(function (it) { return it.str && it.str.trim(); }).map(function (it) {
              return { str: it.str, x: it.transform[4], y: it.transform[5], w: it.width, h: Math.abs(it.transform[3]) || it.height || 8 };
            });
            all = all.concat(analysePage(linesOf(items), state, p, opts.source || "PDF"));
          });
        });
      })(p);
      return chain.then(function () { return finish(all); });
    });
  }

  window.RAEstimates = { fromArrayBuffer: fromArrayBuffer };
})();
