// Submission form. Checks entries, looks the paper up from its DOI, reads chosen PDFs in the browser to
// suggest estimates, then sends files (in parts) and the request to the ReplicAudit intake service.
// The visitor never leaves the website; they land on status.html to follow the audit.
(function () {
  var REPO = document.body.getAttribute("data-repo");
  var $ = function (id) { return document.getElementById(id); };
  var KEY = "ra-submit-draft", MAX = 25 * 1024 * 1024;
  var GH_OK = /\.(zip|gz|tgz|pdf|xlsx|xls|csv|docx|txt|json)$/i;
  var FIELDS_ALL = ["title", "authors", "journal", "doi", "paper", "package", "field", "relationship", "notes"];
  var tried = false, restoring = false;
  var mode = { package: "link", paper: "link" }, files = { package: null, paper: null }, supp = [];

  // ---------------------------------------------------------------- helpers
  function cleanDoi(s) { return (s || "").trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, ""); }
  function validDoi(s) { return /^10\.\d{4,9}\/\S+$/i.test(cleanDoi(s)); }
  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
  function ext(name) { var m = /\.([a-z0-9]+)$/i.exec(name || ""); return m ? m[1].toUpperCase().slice(0, 4) : "FILE"; }
  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function fileProblem(f) {
    if (!f) return "";
    if (f.size > MAX) return f.name + " is larger than 25 MB. Upload it to Zenodo and paste the link instead.";
    if (!GH_OK.test(f.name)) return f.name + ": accepted formats are .zip, .pdf, .xlsx, .csv, .docx and .txt. Zip other formats first.";
    return "";
  }
  function detect(url) {
    var u = (url || "").trim();
    if (!u) return ["", ""];
    if (/openicpsr|icpsr\.umich\.edu/i.test(u)) return ["bad", "openICPSR needs a login, so it can't be fetched automatically. Choose File and send a zip, if the licence allows it."];
    if (/zenodo\.org|10\.5281\/zenodo/i.test(u)) return ["ok", "Zenodo record detected"];
    if (/dataverse|10\.7910\/DVN/i.test(u)) return ["ok", "Dataverse dataset detected"];
    if (/osf\.io|10\.17605\/OSF/i.test(u)) return ["ok", "OSF project detected"];
    if (/github\.com\/[^\/]+\/[^\/]+/i.test(u)) return ["ok", "GitHub repository detected"];
    if (/^(doi:)?10\.\d{4,9}\/\S+$/i.test(u) || /doi\.org\/10\./i.test(u)) return ["ok", "DOI detected. It will be resolved automatically."];
    if (/^https?:\/\/\S+\.(zip|rar|7z|tar\.gz|tgz)(\?|$)/i.test(u)) return ["ok", "Direct archive link detected"];
    if (/^https?:\/\//i.test(u)) return ["info", "Link accepted. It must point directly at a downloadable file or repository."];
    return ["bad", "Enter a DOI or a link starting with https://"];
  }
  function show(id, kind, text) { var o = $(id); o.className = "detect " + (kind || ""); o.textContent = text || ""; }

  // ---------------------------------------------------------------- Link / File switches
  function setMode(target, m) {
    mode[target] = m;
    document.querySelectorAll('.seg[data-target="' + target + '"] button').forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-mode") === m); });
    document.querySelector('[data-pane="' + target + '-link"]').hidden = m !== "link";
    document.querySelector('[data-pane="' + target + '-file"]').hidden = m !== "file";
    refreshDetect(target); update(); save();
  }
  function refreshDetect(target) {
    if (mode[target] === "file") {
      var f = files[target];
      if (!f) return show(target + "-detect", "", "");
      var p = fileProblem(f);
      return show(target + "-detect", p ? "bad" : "ok", p || (f.name + " · " + size(f.size) + " · sent when you press Send"));
    }
    if (target === "package") { var r = detect($("package").value); show("package-detect", r[0], r[1]); }
    if (target === "paper" && !$("paper").value) show("paper-detect", "", "");
  }
  function setFile(target, f) {
    files[target] = f || null;
    var lbl = document.querySelector('label[for="' + target + '-file"] .drop-t');
    lbl.textContent = f ? f.name : (target === "paper" ? "Choose the PDF" : "Choose a .zip");
    refreshDetect(target); update(); save();
    if (target === "paper" && f) scan();
  }
  function wireDrop(target) {
    var input = $(target + "-file"), zone = document.querySelector('label[for="' + target + '-file"]');
    input.addEventListener("change", function () { setFile(target, input.files[0]); });
    ["dragenter", "dragover"].forEach(function (e) { zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (e) { zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.remove("over"); }); });
    zone.addEventListener("drop", function (ev) { if (ev.dataTransfer.files[0]) setFile(target, ev.dataTransfer.files[0]); });
  }

  // ---------------------------------------------------------------- supplementary list
  function renderSupp() {
    var list = $("supp-list");
    list.innerHTML = "";
    supp.forEach(function (s, i) {
      var row = document.createElement("div");
      row.className = "item";
      if (s.kind === "file") {
        var p = fileProblem(s.file);
        if (p) row.className += " bad";
        row.innerHTML = '<div class="ic">' + ext(s.file.name) + '</div><div class="nm" title="' + esc(p || s.file.name) + '">' + esc(s.file.name) +
          '</div><div class="sz">' + size(s.file.size) + '</div><button type="button" class="x" aria-label="Remove">×</button>';
      } else {
        row.innerHTML = '<div class="ic">URL</div><input class="field-in" placeholder="https://… link to a supplementary file" value="' + esc(s.url || "") +
          '" autocapitalize="off" spellcheck="false"><button type="button" class="x" aria-label="Remove">×</button>';
        row.querySelector("input").addEventListener("input", function (e) { s.url = e.target.value.trim(); update(); save(); });
      }
      row.querySelector(".x").addEventListener("click", function () { supp.splice(i, 1); renderSupp(); update(); save(); });
      list.appendChild(row);
    });
    var bad = supp.filter(function (s) { return s.kind === "file" && fileProblem(s.file); })[0];
    show("supp-detect", bad ? "bad" : "", bad ? fileProblem(bad.file) : "");
  }
  function addSuppFiles(fl) {
    var pdfs = [];
    Array.prototype.forEach.call(fl, function (f) { supp.push({ kind: "file", file: f }); if (/\.pdf$/i.test(f.name)) pdfs.push(f); });
    renderSupp(); update(); save();
    if (pdfs.length) scan();
  }

  // ---------------------------------------------------------------- estimates table
  var tbody = $("claims-body");
  function addRow(v) {
    v = v || {};
    var tr = document.createElement("tr");
    tr.innerHTML =
      '<td><input class="field-in" placeholder="T1c3" data-k="id" style="width:84px"></td>' +
      '<td><input class="field-in" placeholder="Table 1 col 3: outcome on treatment" data-k="description"></td>' +
      '<td><input class="field-in" placeholder="-.042" data-k="b" style="width:96px" inputmode="decimal"></td>' +
      '<td><input class="field-in" placeholder=".011" data-k="se" style="width:90px" inputmode="decimal"></td>' +
      '<td><input class="field-in" placeholder="1200" data-k="n" style="width:96px" inputmode="numeric"></td>' +
      '<td style="text-align:center"><input type="radio" name="mainclaim" data-k="main" aria-label="Headline result" style="width:18px;height:18px;accent-color:var(--blue)"></td>' +
      '<td><button type="button" class="x" aria-label="Remove row">×</button></td>';
    tr.querySelector(".x").addEventListener("click", function () { tr.remove(); update(); save(); });
    tr.querySelectorAll("input").forEach(function (i) {
      var k = i.getAttribute("data-k");
      if (k === "main") i.checked = !!v.main; else if (v[k]) i.value = v[k];
      i.addEventListener("input", function () { update(); save(); });
      i.addEventListener("change", function () { update(); save(); });
    });
    tbody.appendChild(tr);
  }
  function rowsData() {
    var out = [];
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var r = {};
      tr.querySelectorAll("input").forEach(function (i) { var k = i.getAttribute("data-k"); r[k] = k === "main" ? i.checked : i.value; });
      out.push(r);
    });
    return out;
  }
  function dropEmptyRows() {
    tbody.querySelectorAll("tr").forEach(function (tr) {
      if (!tr.querySelector('[data-k="id"]').value && !tr.querySelector('[data-k="b"]').value) tr.remove();
    });
  }
  function claimsCsv() {
    var rows = [];
    rowsData().forEach(function (r) {
      if (!r.id && !r.b) return;
      rows.push([r.id.trim(), '"' + r.description.trim().replace(/"/g, "'") + '"', r.b.trim(), r.se.trim(), r.n.trim(), r.main ? "true" : "false"].join(","));
    });
    return rows.length ? "id,description,b,se,n,main\n" + rows.join("\n") : "";
  }

  // ---------------------------------------------------------------- suggestions from PDFs
  var suggestions = [];
  function pdfSources() {
    var out = [];
    if (mode.paper === "file" && files.paper && /\.pdf$/i.test(files.paper.name)) out.push(files.paper);
    supp.forEach(function (s) { if (s.kind === "file" && /\.pdf$/i.test(s.file.name)) out.push(s.file); });
    return out;
  }
  function scanLink() {
    var url = $("paper").value.trim();
    if (!/^https?:\/\//.test(url)) return Promise.resolve([]);
    return fetch(url).then(function (r) { if (!r.ok) throw 0; return r.arrayBuffer(); })
      .then(function (b) { return window.RAEstimates.fromArrayBuffer(b, { source: "paper" }); });
  }
  function scan() {
    var srcs = pdfSources();
    $("scan").disabled = true;
    if (!window.RAEstimates || !window.pdfjsLib) { $("sugg-status").textContent = "The PDF reader is still loading. Try again in a moment."; $("scan").disabled = false; return; }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
    $("sugg-status").textContent = srcs.length ? "Reading " + srcs.map(function (f) { return f.name; }).join(", ") + "…" : "Trying to open the paper from its link…";
    var jobs = srcs.length ? srcs.map(function (f) {
      return f.arrayBuffer().then(function (b) { return window.RAEstimates.fromArrayBuffer(b, { source: f.name }); });
    }) : [scanLink()];
    Promise.all(jobs).then(function (lists) {
      var all = [].concat.apply([], lists);
      suggestions = all;
      renderSuggestions();
      $("sugg-status").textContent = all.length
        ? "Found " + all.length + " estimate" + (all.length > 1 ? "s" : "") + " with standard errors."
        : "No regression tables recognised. Add the estimates by hand or paste them from a spreadsheet.";
    }).catch(function () {
      $("sugg-status").textContent = srcs.length ? "Couldn't read that PDF. It may be scanned or protected. Add the estimates by hand."
        : "The publisher doesn't let browsers open this PDF directly. Download it, choose File above, and the estimates will be suggested.";
    }).then(function () { $("scan").disabled = false; });
  }
  function renderSuggestions() {
    var list = $("sugg-list");
    list.innerHTML = "";
    $("sugg-actions").hidden = !suggestions.length;
    var groups = {};
    suggestions.forEach(function (s, i) {
      var g = (s.table ? "Table " + s.table : "Page " + s.page) + " · " + s.source;
      (groups[g] = groups[g] || []).push(i);
    });
    Object.keys(groups).forEach(function (g) {
      var h = document.createElement("div");
      h.className = "sg-t";
      h.innerHTML = "<span>" + esc(g) + '</span><a href="#" data-g="' + esc(g) + '">Select all</a>';
      h.querySelector("a").addEventListener("click", function (e) {
        e.preventDefault();
        groups[g].forEach(function (i) { $("sg" + i).checked = true; });
      });
      list.appendChild(h);
      groups[g].forEach(function (i) {
        var s = suggestions[i], row = document.createElement("label");
        row.className = "sg";
        row.innerHTML = '<input type="checkbox" id="sg' + i + '"' + (s.suggestedMain ? " checked" : "") + '><span class="v idc">' + esc(s.id) +
          '</span><span class="d">' + esc(s.description) + (s.suggestedMain ? ' <span class="tag">Likely headline</span>' : "") +
          '</span><span class="v">' + esc(s.b + s.stars) + " (" + esc(s.se) + ")</span><span class=\"v\">" + (s.n ? "N " + esc(s.n) : "") + "</span>";
        list.appendChild(row);
      });
    });
  }
  function addSelected() {
    var picked = suggestions.filter(function (s, i) { return $("sg" + i) && $("sg" + i).checked; });
    if (!picked.length) return;
    var have = {};
    rowsData().forEach(function (r) { have[r.id] = 1; });
    dropEmptyRows();
    var anyMain = rowsData().some(function (r) { return r.main; });
    picked.forEach(function (s) {
      if (have[s.id]) return;
      addRow({ id: s.id, description: s.description, b: s.b, se: s.se, n: s.n, main: !anyMain && s.suggestedMain });
    });
    if (!tbody.children.length) addRow();
    $("sugg-status").textContent = picked.length + " added to the table below. Please check them against the paper.";
    update(); save();
  }

  // ---------------------------------------------------------------- paste from a spreadsheet
  function splitLine(line) {
    if (line.indexOf("\t") >= 0) return line.split("\t");
    var out = [], cur = "", q = false;
    for (var i = 0; i < line.length; i++) {
      var ch = line[i];
      if (ch === '"') q = !q; else if (ch === "," && !q) { out.push(cur); cur = ""; } else cur += ch;
    }
    out.push(cur);
    return out;
  }
  function pasteRows() {
    var lines = $("paste").value.split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean), n = 0;
    var parsed = [];
    lines.forEach(function (l) {
      var c = splitLine(l).map(function (x) { return x.trim().replace(/^"(.*)"$/, "$1"); });
      if (/^id$/i.test(c[0]) || c.length < 3) return;
      parsed.push({ id: c[0], description: c[1], b: c[2], se: c[3] || "", n: c[4] || "", main: /^(true|yes|1|x|main)$/i.test(c[5] || "") });
    });
    if (parsed.length) dropEmptyRows();
    parsed.forEach(function (r) { addRow(r); n++; });
    if (!tbody.children.length) addRow();
    $("paste").value = "";
    $("pastebox").style.display = "none";
    $("paste-msg").textContent = n ? n + " estimate" + (n > 1 ? "s" : "") + " added."
      : "Nothing recognised. Use one row per estimate: ID, description, coefficient, standard error, N.";
    update(); save();
  }

  // ---------------------------------------------------------------- DOI look-up
  var lookupTimer, lastLooked = "";
  function setAuto(id, val) {
    var el = $(id);
    if (val && (!el.value || el.getAttribute("data-auto") === "1")) { el.value = val; el.setAttribute("data-auto", "1"); }
  }
  function lookup() {
    var doi = cleanDoi($("doi").value);
    if (!validDoi(doi) || doi === lastLooked) return;
    lastLooked = doi;
    show("doi-detect", "info", "Looking up the paper…");
    fetch("https://api.crossref.org/works/" + encodeURIComponent(doi))
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        var m = j.message || {};
        var authors = (m.author || []).map(function (a) {
          return a.family ? a.family + (a.given ? ", " + a.given.split(/[\s-]+/).filter(Boolean).map(function (g) { return g[0] + "."; }).join(" ") : "") : (a.name || "");
        }).filter(Boolean);
        var year = ((m.issued || m.published || {})["date-parts"] || [[null]])[0][0];
        var jn = (m["container-title"] || [""])[0];
        var vol = m.volume ? " " + m.volume + (m.page ? ":" + m.page : "") : "";
        setAuto("title", (m.title || [""])[0]);
        setAuto("authors", authors.length > 6 ? authors.slice(0, 6).join("; ") + "; et al." : authors.join("; "));
        setAuto("journal", (jn + vol + (year ? ", " + year : "")).trim());
        show("doi-detect", "ok", "Found: " + ((m.title || [""])[0] || doi) + (jn ? " — " + jn : ""));
        update(); save();
      })
      .catch(function () { show("doi-detect", "info", "Couldn't look this DOI up automatically. Please type the details."); });
    fetch("https://api.unpaywall.org/v2/" + encodeURIComponent(doi) + "?email=sfnu1@jh.edu")
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        var url = (j.best_oa_location || {}).url_for_pdf || "";
        if (url && mode.paper === "link") { setAuto("paper", url); show("paper-detect", "ok", "Open-access PDF found automatically"); update(); save(); }
      }).catch(function () {});
  }

  // ---------------------------------------------------------------- values, checks, hand-off
  function values() {
    var v = {};
    FIELDS_ALL.forEach(function (k) { v[k] = $(k).value.trim(); });
    v.doi = cleanDoi(v.doi);
    v.paperText = mode.paper === "file" ? (files.paper ? files.paper.name : "") : v.paper;
    v.claims = claimsCsv();
    return v;
  }
  function problems(v) {
    var p = [];
    ["title", "authors", "journal", "doi", "field", "relationship"].forEach(function (k) { if (!v[k]) p.push($(k).getAttribute("data-label") + " is required"); });
    if (v.doi && !validDoi(v.doi)) p.push("The paper DOI doesn't look like a DOI (it should start with 10.)");
    if (mode.package === "link") {
      if (!v.package) p.push("Replication package is required: a link, or choose File");
      else if (detect(v.package)[0] === "bad") p.push("The replication package link can't be fetched");
    } else if (!files.package) p.push("Choose the replication package file, or switch to Link");
    [files.package && mode.package === "file" ? files.package : null, files.paper && mode.paper === "file" ? files.paper : null]
      .concat(supp.filter(function (s) { return s.kind === "file"; }).map(function (s) { return s.file; }))
      .forEach(function (f) { var q = fileProblem(f); if (q) p.push(q); });
    if (!v.paperText && !v.claims) p.push("Give the paper PDF, or at least one estimate to check");
    if (!$("c1").checked || !$("c2").checked) p.push("Please confirm both statements");
    return p;
  }
  function update() {
    var v = values(), p = problems(v), list = $("problems"), go = $("go");
    var nClaims = v.claims ? v.claims.split("\n").length - 1 : 0;
    var rows = [["Paper", v.title || "—"], ["DOI", v.doi || "—"],
      ["Replication package", mode.package === "file" ? (files.package ? files.package.name + " (file)" : "—") : (v.package || "—")],
      ["Paper PDF", mode.paper === "file" ? (files.paper ? files.paper.name + " (file)" : "not given") : (v.paper || "not given")],
      ["Supplementary", supp.length ? supp.length + " item" + (supp.length > 1 ? "s" : "") : "none"],
      ["Estimates listed", nClaims ? nClaims + (v.claims.indexOf(",true") > 0 ? ", headline marked" : ", headline not marked") : "none: extracted during the audit"]];
    $("summary").innerHTML = rows.map(function (r) { return '<div class="summary-row"><span>' + r[0] + "</span><span>" + esc(r[1]) + "</span></div>"; }).join("");
    list.innerHTML = p.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
    list.style.display = p.length && tried ? "" : "none";
    go.setAttribute("data-ok", p.length ? "0" : "1");
    $("scan").disabled = !(pdfSources().length || (mode.paper === "link" && /^https?:\/\//.test($("paper").value)));
  }

  // ---------------------------------------------------------------- sending (no GitHub account needed)
  var API = document.body.getAttribute("data-api"), PART = 3 * 1024 * 1024, sending = false;
  function rid() {
    var a = new Uint8Array(8); (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  function progress(done, total, label) {
    $("send-box").hidden = false;
    $("send-bar").style.width = Math.round(100 * done / Math.max(total, 1)) + "%";
    $("send-label").textContent = label;
  }
  function uploadFile(id, f, sent, total) {
    var parts = Math.max(1, Math.ceil(f.size / PART)), i = 0;
    function next() {
      if (i >= parts) return Promise.resolve("upload://" + id + "/" + encodeURIComponent(f.name.replace(/[^\w.\- ]+/g, "_").replace(/\s+/g, "_")));
      var blob = f.slice(i * PART, (i + 1) * PART);
      var q = "?rid=" + id + "&name=" + encodeURIComponent(f.name) + "&part=" + (i + 1) + "&parts=" + parts;
      return fetch(API + "/api/upload" + q, { method: "POST", body: blob, headers: { "content-type": "application/octet-stream" } })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "upload failed"); return j; }); })
        .then(function () { sent.n += blob.size; i++; progress(sent.n, total, "Uploading " + f.name + "…"); return next(); });
    }
    return next();
  }
  function send() {
    if (sending) return;
    var v = values(), id = rid(), sent = { n: 0 };
    var list = [];
    if (mode.package === "file" && files.package) list.push(["package", files.package]);
    if (mode.paper === "file" && files.paper) list.push(["paper", files.paper]);
    supp.forEach(function (s, k) { if (s.kind === "file") list.push(["supp" + k, s.file]); });
    var total = list.reduce(function (t, x) { return t + x[1].size; }, 0) + 1, refs = {};
    sending = true; $("go").disabled = true; $("send-error").textContent = "";
    progress(0, total, list.length ? "Uploading files…" : "Sending…");
    var chain = Promise.resolve();
    list.forEach(function (x) { chain = chain.then(function () { return uploadFile(id, x[1], sent, total).then(function (ref) { refs[x[0]] = ref; }); }); });
    chain.then(function () {
      progress(total - 1, total, "Sending the request…");
      var suppLines = supp.map(function (s, k) { return s.kind === "file" ? refs["supp" + k] : s.url; }).filter(Boolean);
      var body = {
        title: v.title, authors: v.authors, journal: v.journal, doi: v.doi, field: v.field, relationship: v.relationship,
        notes: v.notes, claims: v.claims, website: $("website").value,
        package: mode.package === "file" ? refs.package : v.package,
        paper: mode.paper === "file" ? (refs.paper || "") : v.paper,
        supplement: suppLines.join("\n")
      };
      return fetch(API + "/api/submit", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "could not send"); return j; }); });
    }).then(function (j) {
      progress(1, 1, "Sent. Opening your request's status page…");
      try { localStorage.removeItem(KEY); localStorage.setItem("ra-last-request", String(j.number)); } catch (e) {}
      window.location.href = "status.html?r=" + j.number;
    }).catch(function (e) {
      sending = false; $("go").disabled = false;
      $("send-error").textContent = "Couldn't send: " + e.message + ". Nothing was lost; please try again.";
    });
  }

  // ---------------------------------------------------------------- autosave (this browser only)
  function save() {
    if (restoring) return;
    var d = { mode: mode, rows: rowsData(), supp: supp.filter(function (s) { return s.kind === "link"; }) };
    FIELDS_ALL.forEach(function (k) { d[k] = $(k).value; });
    try { localStorage.setItem(KEY, JSON.stringify(d)); } catch (e) {}
  }
  function restore() {
    var d;
    try { d = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { d = null; }
    if (!d) return false;
    restoring = true;
    FIELDS_ALL.forEach(function (k) { if (d[k]) $(k).value = d[k]; });
    (d.rows || []).forEach(function (r) { addRow(r); });
    supp = (d.supp || []).map(function (s) { return { kind: "link", url: s.url }; });
    renderSupp();
    if (d.mode) { setMode("package", d.mode.package || "link"); setMode("paper", d.mode.paper || "link"); }
    restoring = false;
    $("restored").style.display = "";
    if ((d.mode || {}).package === "file" || (d.mode || {}).paper === "file")
      $("restored").innerHTML += " Files can't be kept between visits, so please choose them again.";
    return (d.rows || []).length > 0;
  }

  // ---------------------------------------------------------------- start
  document.addEventListener("DOMContentLoaded", function () {
    if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
    document.querySelectorAll(".seg").forEach(function (seg) {
      seg.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function () { setMode(seg.getAttribute("data-target"), b.getAttribute("data-mode")); });
      });
    });
    wireDrop("package"); wireDrop("paper");
    $("supp-files").addEventListener("change", function (e) { addSuppFiles(e.target.files); e.target.value = ""; });
    $("supp-addlink").addEventListener("click", function () {
      supp.push({ kind: "link", url: "" }); renderSupp();
      var ins = $("supp-list").querySelectorAll("input"); if (ins.length) ins[ins.length - 1].focus();
    });
    if (!restore()) addRow();
    $("addrow").addEventListener("click", function () { addRow(); });
    $("scan").addEventListener("click", scan);
    $("sugg-add").addEventListener("click", addSelected);
    $("pastebtn").addEventListener("click", function () {
      var b = $("pastebox"); b.style.display = b.style.display === "none" ? "" : "none"; if (b.style.display === "") $("paste").focus();
    });
    $("pasteadd").addEventListener("click", pasteRows);
    $("clear").addEventListener("click", function () {
      try { localStorage.removeItem(KEY); } catch (e) {}
      FIELDS_ALL.forEach(function (k) { $(k).value = ""; $(k).removeAttribute("data-auto"); });
      tbody.innerHTML = ""; addRow(); supp = []; renderSupp(); suggestions = []; renderSuggestions();
      setFile("package", null); setFile("paper", null); setMode("package", "link"); setMode("paper", "link");
      $("c1").checked = $("c2").checked = false; tried = false; lastLooked = "";
      ["doi-detect", "package-detect", "paper-detect", "supp-detect"].forEach(function (i) { show(i, "", ""); });
      $("sugg-status").textContent = ""; $("restored").style.display = "none"; update();
    });
    ["title", "authors", "journal", "paper"].forEach(function (k) { $(k).addEventListener("input", function () { $(k).removeAttribute("data-auto"); }); });
    $("package").addEventListener("input", function () { refreshDetect("package"); });
    $("doi").addEventListener("input", function () {
      clearTimeout(lookupTimer); lookupTimer = setTimeout(lookup, 450);
      var raw = $("doi").value, ok = validDoi(raw);
      show("doi-detect", !raw ? "" : ok ? "ok" : "bad", !raw ? "" : ok ? "Valid DOI format" : "A DOI starts with 10. (for example 10.1000/xyz123)");
    });
    document.querySelectorAll("#form input, #form textarea, #form select").forEach(function (el) {
      if (el.id === "paste" || el.type === "file" || el.closest("#supp-list") || el.closest("#sugg-list")) return;
      el.addEventListener("input", function () { update(); save(); });
      el.addEventListener("change", function () { update(); save(); });
    });
    $("go").addEventListener("click", function () {
      tried = true; update();
      if ($("go").getAttribute("data-ok") === "1") send();
      else $("problems").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    if ($("doi").value) lookup();
    refreshDetect("package");
    update();
  });
})();
