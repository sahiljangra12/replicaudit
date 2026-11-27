// Submission form: validates input, detects the package source, and hands everything to
// the repository's GitHub issue form via URL prefill (field ids match audit-request.yml).
(function () {
  var REPO = document.body.getAttribute("data-repo");
  var $ = function (id) { return document.getElementById(id); };

  function detect(url) {
    var u = (url || "").trim();
    if (!u) return ["", ""];
    if (/openicpsr|icpsr\.umich\.edu/i.test(u)) return ["bad", "openICPSR needs a login, so it can't be fetched automatically. Upload a copy to Zenodo instead, if the licence allows it."];
    if (/zenodo\.org|10\.5281\/zenodo/i.test(u)) return ["ok", "Zenodo record detected"];
    if (/dataverse|10\.7910\/DVN/i.test(u)) return ["ok", "Dataverse dataset detected"];
    if (/osf\.io|10\.17605\/OSF/i.test(u)) return ["ok", "OSF project detected"];
    if (/github\.com\/[^\/]+\/[^\/]+/i.test(u)) return ["ok", "GitHub repository detected"];
    if (/^(doi:)?10\.\d{4,9}\/\S+$/i.test(u) || /doi\.org\/10\./i.test(u)) return ["ok", "DOI detected. It will be resolved automatically."];
    if (/^https?:\/\/\S+\.(zip|rar|7z|tar\.gz|tgz)(\?|$)/i.test(u)) return ["ok", "Direct archive link detected"];
    if (/^https?:\/\//i.test(u)) return ["info", "Link accepted. It must point directly at a downloadable file or repository."];
    return ["bad", "Enter a DOI or a link starting with https://"];
  }
  function validDoi(s) { return /^10\.\d{4,9}\/\S+$/i.test(cleanDoi(s)); }

  function setDetect(input, out, fn) {
    var r = fn(input.value); out.className = "detect " + r[0]; out.textContent = r[1];
  }

  // claims editor
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
      i.addEventListener("input", function () { update(); save(); }); i.addEventListener("change", function () { update(); save(); });
    });
    tbody.appendChild(tr);
  }
  function rowsData() {
    var out = [];
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var r = {}; tr.querySelectorAll("input").forEach(function (i) { var k = i.getAttribute("data-k"); r[k] = k === "main" ? i.checked : i.value; });
      out.push(r);
    });
    return out;
  }
  function claimsCsv() {
    var rows = [];
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var g = function (k) { return tr.querySelector('[data-k="' + k + '"]'); };
      var id = g("id").value.trim(), b = g("b").value.trim();
      if (!id && !b) return;
      var d = g("description").value.trim().replace(/"/g, "'");
      rows.push([id, '"' + d + '"', b, g("se").value.trim(), g("n").value.trim(), g("main").checked ? "true" : "false"].join(","));
    });
    return rows.length ? "id,description,b,se,n,main\n" + rows.join("\n") : "";
  }

  var tried = false, KEY = "ra-submit-draft", restoring = false;
  var FIELDS_ALL = ["title", "authors", "journal", "doi", "paper", "package", "supplement", "field", "relationship", "notes"];

  function cleanDoi(s) { return (s || "").trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, ""); }

  // ---- autosave (stays in this browser only)
  function save() {
    if (restoring) return;
    var d = {}; FIELDS_ALL.forEach(function (k) { d[k] = $(k).value; });
    d.rows = rowsData();
    try { localStorage.setItem(KEY, JSON.stringify(d)); } catch (e) {}
  }
  function restore() {
    var d; try { d = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { d = null; }
    if (!d) return false;
    restoring = true;
    FIELDS_ALL.forEach(function (k) { if (d[k]) $(k).value = d[k]; });
    (d.rows || []).forEach(function (r) { addRow(r); });
    restoring = false;
    $("restored").style.display = "";
    return (d.rows || []).length > 0;
  }

  // ---- look the paper up from its DOI (Crossref), and an open-access PDF (Unpaywall)
  var lookupTimer, lastLooked = "";
  function setAuto(id, val) {
    var el = $(id);
    if (val && (!el.value || el.getAttribute("data-auto") === "1")) { el.value = val; el.setAttribute("data-auto", "1"); }
  }
  function lookup() {
    var doi = cleanDoi($("doi").value), o = $("doi-detect");
    if (!validDoi(doi) || doi === lastLooked) return;
    lastLooked = doi;
    o.className = "detect info"; o.textContent = "Looking up the paper…";
    fetch("https://api.crossref.org/works/" + encodeURIComponent(doi))
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        var m = j.message || {};
        var authors = (m.author || []).map(function (a) {
          return a.family ? a.family + (a.given ? ", " + a.given.split(/[\s-]+/).map(function (g) { return g[0] + "."; }).join(" ") : "") : (a.name || "");
        }).filter(Boolean);
        var year = ((m.issued || m.published || {})["date-parts"] || [[null]])[0][0];
        var jn = (m["container-title"] || [""])[0];
        var vol = m.volume ? " " + m.volume + (m.page ? ":" + m.page : "") : "";
        setAuto("title", (m.title || [""])[0]);
        setAuto("authors", authors.length > 6 ? authors.slice(0, 6).join("; ") + "; et al." : authors.join("; "));
        setAuto("journal", (jn + vol + (year ? ", " + year : "")).trim());
        o.className = "detect ok"; o.textContent = "Found: " + ((m.title || [""])[0] || doi) + (jn ? " — " + jn : "");
        update(); save();
      })
      .catch(function () { o.className = "detect info"; o.textContent = "Couldn't look this DOI up automatically. Please type the details."; });
    fetch("https://api.unpaywall.org/v2/" + encodeURIComponent(doi) + "?email=sfnu1@jh.edu")
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        var l = j.best_oa_location || {}, url = l.url_for_pdf || "";
        if (url) { setAuto("paper", url); $("paper-detect").className = "detect ok"; $("paper-detect").textContent = "Open-access PDF found automatically"; update(); save(); }
      }).catch(function () {});
  }

  // ---- paste estimates from a spreadsheet or CSV
  function splitLine(line) {
    if (line.indexOf("\t") >= 0) return line.split("\t");
    var out = [], cur = "", q = false;
    for (var i = 0; i < line.length; i++) {
      var ch = line[i];
      if (ch === '"') q = !q; else if (ch === "," && !q) { out.push(cur); cur = ""; } else cur += ch;
    }
    out.push(cur); return out;
  }
  function pasteRows() {
    var lines = $("paste").value.split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean), n = 0;
    lines.forEach(function (l) {
      var c = splitLine(l).map(function (x) { return x.trim().replace(/^"(.*)"$/, "$1"); });
      if (/^id$/i.test(c[0])) return;
      if (c.length < 3) return;
      addRow({ id: c[0], description: c[1], b: c[2], se: c[3] || "", n: c[4] || "", main: /^(true|yes|1|x|main)$/i.test(c[5] || "") });
      n++;
    });
    // drop the empty starter row if real rows were added
    tbody.querySelectorAll("tr").forEach(function (tr) { if (n && !tr.querySelector('[data-k="id"]').value && !tr.querySelector('[data-k="b"]').value) tr.remove(); });
    $("paste").value = ""; $("pastebox").style.display = "none";
    $("paste-msg").textContent = n ? n + " estimate" + (n > 1 ? "s" : "") + " added." : "Nothing recognised: use one row per estimate (ID, description, coefficient, standard error, N).";
    update(); save();
  }
  var req = ["title", "authors", "journal", "doi", "package", "field", "relationship"];
  function values() {
    var v = {};
    FIELDS_ALL.forEach(function (k) { v[k] = $(k).value.trim(); });
    v.doi = cleanDoi(v.doi);
    v.claims = claimsCsv();
    return v;
  }
  function problems(v) {
    var p = [];
    req.forEach(function (k) { if (!v[k]) p.push($(k).getAttribute("data-label") + " is required"); });
    if (v.doi && !validDoi(v.doi)) p.push("The paper DOI doesn't look like a DOI (it should start with 10.)");
    if (v.package && detect(v.package)[0] === "bad") p.push("The replication package link can't be fetched");
    if (!v.paper && !v.claims) p.push("Give a paper PDF link or at least one estimate to check");
    if (!$("c1").checked || !$("c2").checked) p.push("Please confirm both statements");
    return p;
  }
  function buildUrl(v) {
    var q = new URLSearchParams();
    q.set("template", "audit-request.yml");
    q.set("title", "[Audit] " + v.title);
    q.set("labels", "audit-request");
    ["authors", "journal", "doi", "paper", "package", "supplement", "field", "relationship", "notes"].forEach(function (k) { if (v[k]) q.set(k, v[k]); });
    q.set("paper_title", v.title);
    if (v.claims) q.set("claims", v.claims);
    return REPO + "/issues/new?" + q.toString();
  }
  function update() {
    var v = values(), p = problems(v), list = $("problems"), go = $("go");
    var rows = [["Paper", v.title || "—"], ["DOI", v.doi || "—"], ["Replication package", v.package || "—"],
      ["Paper PDF", v.paper || "not given"], ["Supplement", v.supplement || "not given"],
      ["Estimates listed", v.claims ? (v.claims.split("\n").length - 1) + " (headline: " + (v.claims.indexOf(",true") > 0 ? "marked" : "not marked") + ")" : "none — extracted from the PDF"]];
    $("summary").innerHTML = rows.map(function (r) {
      var s = document.createElement("span"); s.textContent = r[1];
      return '<div class="summary-row"><span>' + r[0] + "</span>" + s.outerHTML + "</div>";
    }).join("");
    list.innerHTML = p.map(function (x) { var li = document.createElement("li"); li.textContent = x; return li.outerHTML; }).join("");
    list.style.display = p.length && tried ? "" : "none";
    var url = buildUrl(v);
    go.setAttribute("data-ok", p.length ? "0" : "1");
    go.setAttribute("data-url", url);
    $("toolong").style.display = url.length > 7800 ? "" : "none";
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!restore()) addRow();
    $("addrow").addEventListener("click", function () { addRow(); });
    $("pastebtn").addEventListener("click", function () { var b = $("pastebox"); b.style.display = b.style.display === "none" ? "" : "none"; if (b.style.display === "") $("paste").focus(); });
    $("pasteadd").addEventListener("click", pasteRows);
    $("clear").addEventListener("click", function () {
      try { localStorage.removeItem(KEY); } catch (e) {}
      FIELDS_ALL.forEach(function (k) { $(k).value = ""; $(k).removeAttribute("data-auto"); });
      tbody.innerHTML = ""; addRow(); $("c1").checked = $("c2").checked = false; tried = false; lastLooked = "";
      ["doi-detect", "package-detect", "paper-detect"].forEach(function (i) { $(i).textContent = ""; });
      $("restored").style.display = "none"; update();
    });
    ["title", "authors", "journal", "paper"].forEach(function (k) { $(k).addEventListener("input", function () { $(k).removeAttribute("data-auto"); }); });
    $("package").addEventListener("input", function () { setDetect($("package"), $("package-detect"), detect); });
    $("doi").addEventListener("input", function () {
      clearTimeout(lookupTimer); lookupTimer = setTimeout(lookup, 450);
      var ok = validDoi(cleanDoi($("doi").value)); var o = $("doi-detect");
      o.className = "detect " + (!$("doi").value ? "" : ok ? "ok" : "bad");
      o.textContent = !$("doi").value ? "" : ok ? "Valid DOI format" : "A DOI starts with 10. (for example 10.1000/xyz123)";
    });
    document.querySelectorAll("#form input, #form textarea, #form select").forEach(function (el) {
      if (el.id === "paste") return;
      el.addEventListener("input", function () { update(); save(); }); el.addEventListener("change", function () { update(); save(); });
    });
    if ($("doi").value) lookup();
    if ($("package").value) setDetect($("package"), $("package-detect"), detect);
    $("go").addEventListener("click", function () {
      tried = true; update();
      if ($("go").getAttribute("data-ok") === "1") window.open($("go").getAttribute("data-url"), "_blank", "noopener");
      else $("problems").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    update();
  });
})();
