// "Audit a paper": paste a DOI or paper link; everything else is found automatically where possible.
//  • paper details from Crossref, an open-access PDF from Unpaywall
//  • the replication package from DataCite (datasets that declare themselves supplements to the paper),
//    Crossref relations, and data-availability links inside a dropped PDF
//  • one drop zone: PDFs become the paper or supplements; any other files or a whole folder are zipped
//    in the browser into the data-and-code package
// Then files are sent in parts to the intake service and the visitor lands on their status page.
(function () {
  var API = document.body.getAttribute("data-api");
  var $ = function (id) { return document.getElementById(id); };
  var PART = 3 * 1024 * 1024, MAXFILE = 100 * 1024 * 1024;
  var st = { doi: "", meta: null, oaPdf: "", candidates: [], pick: "", link: "", files: [], suggestions: [], picked: {}, busy: false, apiOk: null };

  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
  function cleanDoi(s) {
    s = (s || "").trim();
    var m = s.match(/10\.\d{4,9}\/[^\s"<>]+/);
    return m ? m[0].replace(/[.,;)]+$/, "").replace(/\/(full|abstract|pdf|epdf)$/i, "") : "";
  }
  function show(id, on) { $(id).hidden = !on; }
  function getJSON(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }

  // ------------------------------------------------------------ is the submission service up?
  function health() {
    fetch(API + "/api/health", { method: "GET" }).then(function (r) { st.apiOk = r.ok; })
      .catch(function () { st.apiOk = false; })
      .then(function () { show("down", st.apiOk === false); render(); });
  }

  // ------------------------------------------------------------ step 1: find the paper
  var lookTimer;
  function lookup() {
    var doi = cleanDoi($("q").value);
    $("q-msg").className = "detect";
    if (!doi) {
      $("q-msg").textContent = $("q").value.trim() ? "That doesn't contain a DOI. Most journal article pages show one, starting with 10." : "";
      return;
    }
    if (doi === st.doi) return;
    st = Object.assign(st, { doi: doi, meta: null, oaPdf: "", candidates: [], pick: "" });
    $("q-msg").className = "detect info"; $("q-msg").textContent = "Looking up the paper…";
    show("found", true); render();
    var crossref = getJSON("https://api.crossref.org/works/" + encodeURIComponent(doi)).then(function (j) {
      var m = j.message || {};
      var authors = (m.author || []).map(function (a) {
        return a.family ? a.family + (a.given ? ", " + a.given.split(/[\s-]+/).filter(Boolean).map(function (g) { return g[0] + "."; }).join(" ") : "") : (a.name || "");
      }).filter(Boolean);
      var year = ((m.issued || m.published || {})["date-parts"] || [[null]])[0][0];
      st.meta = { title: (m.title || [""])[0], authors: authors.length > 6 ? authors.slice(0, 6).join("; ") + "; et al." : authors.join("; "),
                  journal: ((m["container-title"] || [""])[0] + (m.volume ? " " + m.volume + (m.page ? ":" + m.page : "") : "") + (year ? ", " + year : "")).trim(),
                  field: (m.subject || [])[0] || "" };
      var rel = m.relation || {};
      ["is-supplemented-by", "has-related-material", "references", "is-related-to"].forEach(function (k) {
        (rel[k] || []).forEach(function (r) { if (r["id-type"] === "doi" && /^10\.(5281|7910|5061|3886|6084|17605|5878)\//.test(r.id)) addCandidate("https://doi.org/" + r.id, "Linked by the journal", r.id); });
      });
    }).catch(function () { st.meta = st.meta || { title: "", authors: "", journal: "", field: "", missing: true }; });
    var unpaywall = getJSON("https://api.unpaywall.org/v2/" + encodeURIComponent(doi) + "?email=sfnu1@jh.edu").then(function (j) {
      st.oaPdf = (j.best_oa_location || {}).url_for_pdf || "";
    }).catch(function () {});
    var datacite = getJSON("https://api.datacite.org/dois?page[size]=10&query=" + encodeURIComponent('relatedIdentifiers.relatedIdentifier:"' + doi.toLowerCase() + '"'))
      .then(function (j) {
        (j.data || []).forEach(function (d) {
          var a = d.attributes || {}, t = (a.types || {}).resourceTypeGeneral || "";
          if (/^(Dataset|Software|Collection|Workflow|Other)$/i.test(t) || /zenodo|dataverse|dryad|icpsr|figshare|osf/i.test(a.publisher || "")) {
            addCandidate("https://doi.org/" + a.doi, (a.publisher || "Repository") + " · " + (t || "data"), ((a.titles || [{}])[0] || {}).title || a.doi);
          }
        });
      }).catch(function () {});
    Promise.all([crossref, unpaywall, datacite]).then(function () {
      if (st.meta && st.meta.missing) { $("q-msg").className = "detect bad"; $("q-msg").textContent = "Couldn't find this DOI. Check it, or type the details below."; show("edit-box", true); }
      else { $("q-msg").className = "detect ok"; $("q-msg").textContent = "Found it."; }
      if (!st.pick && st.candidates.length) st.pick = st.candidates[0].url;
      render(); save();
    });
  }
  function addCandidate(url, where, label) {
    if (st.candidates.some(function (c) { return c.url.toLowerCase() === url.toLowerCase(); })) return;
    st.candidates.push({ url: url, where: where, label: label });
  }

  // ------------------------------------------------------------ files: one drop zone
  function role(f) { return /\.pdf$/i.test(f.name) ? "pdf" : "data"; }
  function addFiles(list) {
    list.forEach(function (f) {
      var p = f.path || f.webkitRelativePath || f.name;
      if (!f.size || /(^|\/)(\.[^\/]*|__MACOSX)(\/|$)/.test(p)) return;
      var item = { file: f, path: p, kind: role(f) };
      if (item.kind === "pdf") item.pdfRole = st.files.some(function (x) { return x.pdfRole === "paper"; }) || /supp|appendix|\bsm\b|_si\b|online/i.test(f.name) ? "supplement" : "paper";
      st.files.push(item);
    });
    st.files.filter(function (x) { return x.kind === "pdf" && !x.scanned; }).forEach(function (x) { x.scanned = true; scanPdf(x); });
    render(); save();
  }
  function scanPdf(item) {
    if (!window.RAEstimates || !window.pdfjsLib) return;
    $("sugg-status").textContent = "Reading " + item.file.name + "…";
    item.file.arrayBuffer().then(function (buf) {
      return Promise.all([window.RAEstimates.textOf(buf.slice(0)), window.RAEstimates.fromArrayBuffer(buf.slice(0), { source: item.file.name })]);
    }).then(function (r) {
      window.RAEstimates.repoLinks(r[0]).forEach(function (u) { addCandidate(u, "Found in " + item.file.name, u.replace(/^https?:\/\//, "")); });
      if (!st.pick && st.candidates.length && !dataFiles().length) st.pick = st.candidates[0].url;
      r[1].forEach(function (s) { s.key = s.source + "|" + s.id; if (!st.suggestions.some(function (x) { return x.key === s.key; })) st.suggestions.push(s); });
      st.suggestions.forEach(function (s) { if (s.suggestedMain && !(s.key in st.picked)) st.picked[s.key] = true; });
      $("sugg-status").textContent = st.suggestions.length ? st.suggestions.length + " estimates found in the tables. The likely headline is ticked; tick any others to check." : "";
      render();
    }).catch(function () { $("sugg-status").textContent = ""; });
  }
  function readEntry(entry, path) {
    return new Promise(function (res) {
      if (entry.isFile) entry.file(function (f) { f.path = path + f.name; res([f]); }, function () { res([]); });
      else if (entry.isDirectory) {
        var reader = entry.createReader(), all = [];
        (function more() {
          reader.readEntries(function (ents) {
            if (!ents.length) return Promise.all(all).then(function (x) { res([].concat.apply([], x)); });
            ents.forEach(function (e) { all.push(readEntry(e, path + entry.name + "/")); });
            more();
          }, function () { res([]); });
        })();
      } else res([]);
    });
  }
  function onDrop(e) {
    e.preventDefault(); $("drop").classList.remove("over");
    var items = e.dataTransfer.items;
    if (items && items.length && items[0].webkitGetAsEntry) {
      var jobs = [];
      for (var i = 0; i < items.length; i++) { var en = items[i].webkitGetAsEntry(); if (en) jobs.push(readEntry(en, "")); }
      Promise.all(jobs).then(function (x) { addFiles([].concat.apply([], x)); });
    } else addFiles(Array.prototype.slice.call(e.dataTransfer.files));
  }
  function dataFiles() { return st.files.filter(function (x) { return x.kind === "data"; }); }

  // ------------------------------------------------------------ render
  function ok(t, s) { return '<div class="mrow ok"><i>✓</i><div><b>' + t + "</b><span>" + s + "</span></div></div>"; }
  function opt(t, s) { return '<div class="mrow opt"><i>○</i><div><b>' + t + "</b><span>" + s + "</span></div></div>"; }
  function need(t, s) { return '<div class="mrow need"><i>!</i><div><b>' + t + "</b><span>" + s + "</span></div></div>"; }

  function render() {
    var m = st.meta || {};
    if (st.meta) ["title", "authors", "journal"].forEach(function (k) { if ($(k).getAttribute("data-touched") !== "1") $(k).value = m[k] || ""; });
    $("paper-title").textContent = $("title").value || (st.doi ? "doi:" + st.doi : "");
    $("paper-meta").textContent = [$("authors").value, $("journal").value].filter(Boolean).join(" · ");

    var paperFile = st.files.filter(function (x) { return x.pdfRole === "paper"; })[0];
    $("m-paper").innerHTML = paperFile ? ok("Paper PDF", esc(paperFile.file.name))
      : st.oaPdf ? ok("Paper PDF", 'Open-access copy found · <a href="' + esc(st.oaPdf) + '" target="_blank" rel="noopener">view</a>')
      : opt("Paper PDF", "Not found automatically. Add it below if you have it.");

    var dfs = dataFiles();
    var cands = st.candidates.map(function (c) {
      return '<label class="cand"><input type="radio" name="cand" value="' + esc(c.url) + '"' + (st.pick === c.url && !dfs.length && !st.link.trim() ? " checked" : "") + (dfs.length ? " disabled" : "") +
        '><span><b>' + esc(c.label) + '</b><span class="small">' + esc(c.where) + " · " + esc(c.url.replace(/^https?:\/\//, "")) + "</span></span></label>";
    }).join("");
    var dataStatus = dfs.length
      ? ok("Data and code", dfs.length + " file" + (dfs.length > 1 ? "s" : "") + " from your computer" +
           ((dfs.length > 1 || !/\.(zip|tgz|gz)$/i.test(dfs[0].file.name)) ? ", zipped automatically" : "") + " · " + size(dfs.reduce(function (t, x) { return t + x.file.size; }, 0)))
      : st.link.trim() ? ok("Data and code", "Your link: " + esc(st.link.trim()))
      : st.pick ? ok("Data and code", st.candidates.length > 1 ? "Found " + st.candidates.length + " possible packages. Check the right one is chosen." : "Found automatically. Check it's the right one.")
      : need("Data and code", "Not found automatically. Paste a link below or add the files.");
    $("m-data").innerHTML = dataStatus + (cands ? '<div class="cands">' + cands + "</div>" : "");
    document.querySelectorAll('input[name="cand"]').forEach(function (r) {
      r.addEventListener("change", function () { st.pick = r.value; st.link = ""; $("link").value = ""; render(); save(); });
    });
    var sups = st.files.filter(function (x) { return x.pdfRole === "supplement"; });
    $("m-supp").innerHTML = sups.length ? ok("Supplementary material", sups.map(function (x) { return esc(x.file.name); }).join(", "))
      : opt("Supplementary material", "Optional. Add the supplement if estimates are reported there.");

    $("chips").innerHTML = st.files.map(function (x, i) {
      var sel = x.kind === "pdf"
        ? '<select data-i="' + i + '" class="chip-role" aria-label="What is this PDF?"><option value="paper"' + (x.pdfRole === "paper" ? " selected" : "") + '>Paper</option><option value="supplement"' + (x.pdfRole === "supplement" ? " selected" : "") + ">Supplement</option></select>"
        : '<span class="small">Data &amp; code</span>';
      return '<div class="item"><div class="ic">' + esc((x.file.name.split(".").pop() || "").slice(0, 4).toUpperCase()) + '</div><div class="nm" title="' + esc(x.path) + '">' + esc(x.path) +
        "</div>" + sel + '<div class="sz">' + size(x.file.size) + '</div><button type="button" class="x" data-x="' + i + '" aria-label="Remove">×</button></div>';
    }).join("");
    document.querySelectorAll("[data-x]").forEach(function (b) { b.addEventListener("click", function () { st.files.splice(+b.getAttribute("data-x"), 1); render(); save(); }); });
    document.querySelectorAll(".chip-role").forEach(function (s) { s.addEventListener("change", function () { st.files[+s.getAttribute("data-i")].pdfRole = s.value; render(); }); });

    $("sugg").innerHTML = st.suggestions.map(function (s) {
      return '<label class="sg"><input type="checkbox" data-k="' + esc(s.key) + '"' + (st.picked[s.key] ? " checked" : "") + '><span class="v idc">' + esc(s.id) + '</span><span class="d">' + esc(s.description) +
        (s.suggestedMain ? ' <span class="tag">Likely headline</span>' : "") + '</span><span class="v">' + esc(s.b + s.stars) + " (" + esc(s.se) + ')</span><span class="v">' + (s.n ? "N " + esc(s.n) : "") + "</span></label>";
    }).join("");
    document.querySelectorAll("#sugg input").forEach(function (c) { c.addEventListener("change", function () { st.picked[c.getAttribute("data-k")] = c.checked; }); });

    var p = problems();
    $("go").disabled = st.busy;
    $("why").innerHTML = p.length && st.tried ? p.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") : "";
    show("found", !!st.doi || st.files.length > 0 || !!$("title").value);
  }

  function problems() {
    var p = [];
    if (!st.doi) p.push("Paste the paper's DOI or a link to the paper");
    if (!$("title").value.trim()) p.push("Add the paper's title (Edit details)");
    if (!dataFiles().length && !st.pick && !st.link.trim()) p.push("Add the data and code: choose a found package, paste a link, or add the files");
    if (st.link.trim() && !/^(https?:\/\/|10\.\d{4,9}\/)/i.test(st.link.trim())) p.push("The data link should start with https://");
    st.files.forEach(function (x) { if (x.file.size > MAXFILE) p.push(x.file.name + " is over 100 MB. Upload it to Zenodo and paste the link instead"); });
    if (st.apiOk === false) p.push("Submissions are closed right now. Please try again later");
    return p;
  }

  // ------------------------------------------------------------ send
  function rid() {
    var a = new Uint8Array(8); crypto.getRandomValues(a);
    return Array.prototype.map.call(a, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  function progress(done, total, label) {
    show("send-box", true);
    $("send-bar").style.width = Math.round(100 * done / Math.max(total, 1)) + "%";
    $("send-label").textContent = label;
  }
  function uploadBlob(id, name, blob, sent, total) {
    var parts = Math.max(1, Math.ceil(blob.size / PART)), i = 0;
    function next() {
      if (i >= parts) return Promise.resolve("upload://" + id + "/" + encodeURIComponent(name.replace(/[^\w.\- ]+/g, "_").replace(/\s+/g, "_")));
      var piece = blob.slice(i * PART, (i + 1) * PART);
      return fetch(API + "/api/upload?rid=" + id + "&name=" + encodeURIComponent(name) + "&part=" + (i + 1) + "&parts=" + parts,
                   { method: "POST", body: piece, headers: { "content-type": "application/octet-stream" } })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "upload failed"); }); })
        .then(function () { sent.n += piece.size; i++; progress(sent.n, total, "Uploading " + name + "…"); return next(); });
    }
    return next();
  }
  function packageBlob() {
    var dfs = dataFiles();
    if (!dfs.length) return Promise.resolve(null);
    if (dfs.length === 1 && /\.(zip|tgz|gz)$/i.test(dfs[0].file.name)) return Promise.resolve({ name: dfs[0].file.name, blob: dfs[0].file });
    progress(0, 1, "Zipping " + dfs.length + " files…");
    var zip = new window.JSZip();
    dfs.forEach(function (x) { zip.file(x.path, x.file); });
    return zip.generateAsync({ type: "blob", compression: "DEFLATE" }).then(function (b) { return { name: "data-and-code.zip", blob: b }; });
  }
  function claimsCsv() {
    var rows = st.suggestions.filter(function (s) { return st.picked[s.key]; }).map(function (s) {
      return [s.id, '"' + s.description.replace(/"/g, "'") + '"', s.b, s.se, s.n || "", s.suggestedMain ? "true" : "false"].join(",");
    });
    var typed = ($("paste").value || "").trim().split(/\r?\n/).filter(function (l) { return l.trim() && !/^id\s*[,\t]/i.test(l); })
      .map(function (l) { return l.indexOf("\t") >= 0 ? l.split("\t").map(function (c) { c = c.trim(); return /,/.test(c) ? '"' + c + '"' : c; }).join(",") : l; });
    rows = rows.concat(typed);
    return rows.length ? "id,description,b,se,n,main\n" + rows.join("\n") : "";
  }
  function send() {
    st.tried = true;
    var p = problems();
    if (p.length) { render(); $("why").scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    st.busy = true; render(); $("send-error").textContent = "";
    var id = rid(), sent = { n: 0 }, refs = { supp: [] };
    var pdfs = st.files.filter(function (x) { return x.kind === "pdf"; });
    packageBlob().then(function (pkg) {
      var total = (pkg ? pkg.blob.size : 0) + pdfs.reduce(function (t, x) { return t + x.file.size; }, 0) + 1;
      if (pkg && pkg.blob.size > MAXFILE) throw new Error("the data and code come to more than 100 MB once zipped. Please upload them to Zenodo and paste the link");
      var chain = Promise.resolve();
      if (pkg) chain = chain.then(function () { return uploadBlob(id, pkg.name, pkg.blob, sent, total).then(function (r) { refs.pkg = r; }); });
      pdfs.forEach(function (x) {
        chain = chain.then(function () {
          return uploadBlob(id, x.file.name, x.file, sent, total).then(function (r) { if (x.pdfRole === "paper" && !refs.paper) refs.paper = r; else refs.supp.push(r); });
        });
      });
      return chain;
    }).then(function () {
      progress(1, 1, "Starting the audit…");
      var body = {
        title: $("title").value.trim(), authors: $("authors").value.trim(), journal: $("journal").value.trim(), doi: st.doi,
        field: (st.meta || {}).field || "", relationship: $("mine").checked ? "I am an author" : "Not stated",
        package: refs.pkg || st.link.trim() || st.pick, paper: refs.paper || st.oaPdf || "",
        supplement: refs.supp.join("\n"), claims: claimsCsv(), notes: $("notes").value.trim(), website: $("website").value
      };
      return fetch(API + "/api/submit", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "could not send"); return j; }); });
    }).then(function (j) {
      try { localStorage.removeItem("ra-draft2"); localStorage.setItem("ra-last-request", String(j.number)); } catch (e) {}
      location.href = "status.html?r=" + j.number;
    }).catch(function (e) {
      st.busy = false; render();
      $("send-error").textContent = /load failed|failed to fetch|networkerror/i.test(e.message)
        ? "The submission service couldn't be reached. Your entries are kept; please try again in a few minutes."
        : "Couldn't send: " + e.message + ".";
    });
  }

  // ------------------------------------------------------------ keep typed entries in this browser (files can't be kept)
  function save() {
    try { localStorage.setItem("ra-draft2", JSON.stringify({ q: $("q").value, link: st.link, title: $("title").value, authors: $("authors").value, journal: $("journal").value })); } catch (e) {}
  }
  function restore() {
    var d;
    try { d = JSON.parse(localStorage.getItem("ra-draft2") || "null"); } catch (e) {}
    if (!d) return;
    $("q").value = d.q || ""; st.link = d.link || ""; $("link").value = st.link;
    ["title", "authors", "journal"].forEach(function (k) { if (d[k]) { $(k).value = d[k]; $(k).setAttribute("data-touched", "1"); } });
    if (d.q) lookup();
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
    $("q").addEventListener("input", function () { clearTimeout(lookTimer); lookTimer = setTimeout(lookup, 400); save(); });
    $("q").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); lookup(); } });
    $("find").addEventListener("click", lookup);
    $("link").addEventListener("input", function () { st.link = $("link").value; render(); save(); });
    ["title", "authors", "journal"].forEach(function (k) { $(k).addEventListener("input", function () { $(k).setAttribute("data-touched", "1"); render(); save(); }); });
    var dz = $("drop");
    ["dragenter", "dragover"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("over"); }); });
    dz.addEventListener("dragleave", function () { dz.classList.remove("over"); });
    dz.addEventListener("drop", onDrop);
    $("pick-files").addEventListener("change", function (e) { addFiles(Array.prototype.slice.call(e.target.files)); e.target.value = ""; });
    $("pick-folder").addEventListener("change", function (e) { addFiles(Array.prototype.slice.call(e.target.files)); e.target.value = ""; });
    $("go").addEventListener("click", send);
    $("edit").addEventListener("click", function () { var f = $("edit-box"); f.hidden = !f.hidden; });
    restore(); health(); render();
  });
})();
