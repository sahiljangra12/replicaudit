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
  function validDoi(s) { return /^(https?:\/\/(dx\.)?doi\.org\/|doi:)?10\.\d{4,9}\/\S+$/i.test((s || "").trim()); }

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
      '<td><input class="field-in" placeholder="-.0125" data-k="b" style="width:96px" inputmode="decimal"></td>' +
      '<td><input class="field-in" placeholder=".0037" data-k="se" style="width:90px" inputmode="decimal"></td>' +
      '<td><input class="field-in" placeholder="46371" data-k="n" style="width:96px" inputmode="numeric"></td>' +
      '<td style="text-align:center"><input type="radio" name="mainclaim" data-k="main" aria-label="Headline result" style="width:18px;height:18px;accent-color:var(--blue)"></td>' +
      '<td><button type="button" class="x" aria-label="Remove row">×</button></td>';
    tr.querySelector(".x").addEventListener("click", function () { tr.remove(); update(); });
    tr.querySelectorAll("input").forEach(function (i) {
      if (v[i.getAttribute("data-k")]) i.value = v[i.getAttribute("data-k")];
      i.addEventListener("input", update); i.addEventListener("change", update);
    });
    tbody.appendChild(tr);
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

  var tried = false;
  var req = ["title", "authors", "journal", "doi", "package", "field", "relationship"];
  function values() {
    var v = {};
    ["title", "authors", "journal", "doi", "paper", "package", "supplement", "field", "relationship", "notes"].forEach(function (k) { v[k] = $(k).value.trim(); });
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
    addRow();
    $("addrow").addEventListener("click", function () { addRow(); });
    $("package").addEventListener("input", function () { setDetect($("package"), $("package-detect"), detect); });
    $("doi").addEventListener("input", function () {
      var ok = validDoi($("doi").value); var o = $("doi-detect");
      o.className = "detect " + (!$("doi").value ? "" : ok ? "ok" : "bad");
      o.textContent = !$("doi").value ? "" : ok ? "Valid DOI format" : "A DOI starts with 10. (for example 10.1126/science.aee0747)";
    });
    document.querySelectorAll("#form input, #form textarea, #form select").forEach(function (el) {
      el.addEventListener("input", update); el.addEventListener("change", update);
    });
    $("go").addEventListener("click", function () {
      tried = true; update();
      if ($("go").getAttribute("data-ok") === "1") window.open($("go").getAttribute("data-url"), "_blank", "noopener");
      else $("problems").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    update();
  });
})();
