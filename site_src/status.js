// Status page for one request: shows progress, then the results, without leaving the website.
(function () {
  var REPO = "sahiljangra12/replicaudit";
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
  var VERD = { exact: ["Reproduced", "p-exact"], close: ["Close", "p-close"], same_sign: ["Size differs", "p-same_sign"],
               different: ["Sign differs", "p-different"], failed: ["Not rebuilt", "p-failed"], not_found: ["Not found", "p-failed"] };
  var METHOD = { authors_code: "Authors' own code", ai_rebuild: "Rebuilt by the AI stage" };
  var timer;

  function step(id, state, text) {
    var el = $(id); el.className = "st " + state;
    if (text) el.querySelector(".st-s").textContent = text;
  }
  function fmt(x) { return x == null ? "—" : Number(x).toFixed(4); }

  function load(r) {
    clearTimeout(timer);
    $("ask").hidden = true; $("track").hidden = false;
    fetch("https://api.github.com/repos/" + REPO + "/issues/" + r)
      .then(function (res) { if (res.status === 404) throw new Error("No request with number " + r + "."); if (!res.ok) throw new Error("The status service is busy. It will retry shortly."); return res.json(); })
      .then(function (iss) {
        var labels = (iss.labels || []).map(function (l) { return l.name; });
        $("t-title").textContent = (iss.title || "").replace(/^\[Audit\]\s*/, "");
        $("t-meta").textContent = "Request #" + r + " · received " + new Date(iss.created_at).toLocaleString();
        step("s1", "done", "We have your request and materials.");
        var done = labels.indexOf("results-ready") >= 0, failed = labels.indexOf("audit-failed") >= 0, running = labels.indexOf("running") >= 0;
        if (failed) { step("s2", "done"); step("s3", "bad", "The audit couldn't be completed. The details are below."); }
        else if (done) { step("s2", "done", "Finished."); step("s3", "done", "Results are below."); }
        else if (running) { step("s2", "now", "Running the authors' code and checking every number. This usually takes 20–90 minutes."); step("s3", "todo"); }
        else { step("s2", "now", "Waiting to start. Audits run one at a time."); step("s3", "todo"); }
        if (done || failed) return showResults(iss);
        timer = setTimeout(function () { load(r); }, 90000);
      })
      .catch(function (e) { $("t-err").textContent = e.message; timer = setTimeout(function () { load(r); }, 120000); });
  }

  function showResults(iss) {
    return fetch(iss.comments_url).then(function (r) { return r.json(); }).then(function (cs) {
      var slug = null;
      (cs || []).forEach(function (c) { var m = /slug:([a-z0-9-]+)/.exec(c.body || ""); if (m) slug = m[1]; });
      if (!slug) { $("results").innerHTML = '<p class="sub">Results are being published. Refresh in a minute.</p>'; return; }
      var raw = "https://raw.githubusercontent.com/" + REPO + "/main/audits/" + slug + "/";
      return Promise.all([fetch(raw + "submission.json").then(function (r) { return r.json(); }),
                          fetch(raw + "audit.json").then(function (r) { return r.ok ? r.json() : null; })])
        .then(function (x) { render(x[0], x[1], slug); });
    }).catch(function () { $("results").innerHTML = '<p class="sub">Results are being published. Refresh in a minute.</p>'; });
  }

  function render(sub, au, slug) {
    var h = [];
    if (sub.status === "could not fetch" || !au) {
      h.push('<div class="note amber"><b>The materials could not be downloaded.</b> ' + esc(sub.error || "") + "</div>");
      $("results").innerHTML = h.join(""); return;
    }
    var cl = au.claims || [], n = cl.length, cnt = {};
    cl.forEach(function (c) { var v = (c.compare || {}).verdict || "not_found"; cnt[v] = (cnt[v] || 0) + 1; });
    var ac = au.authors_code || {};
    h.push('<div class="note amber"><b>Automated result, not yet reviewed.</b> A person checks every audit before it is published with its full report.</div>');
    h.push('<div class="grid g3" style="margin:20px 0">' +
      '<div class="card stat"><div class="num green">' + (cnt.exact || 0) + '<span style="font-size:26px">/' + n + '</span></div><div class="lbl">estimates reproduced to the printed precision</div></div>' +
      '<div class="card stat"><div class="num">' + esc(ac.language || "—") + '</div><div class="lbl">language of the authors\' code · ' + esc({ ran: "ran successfully", "ran with errors": "ran with some errors", "needs translation": "translated by the AI stage", "no code": "no code found" }[ac.status] || ac.status || "") + '</div></div>' +
      '<div class="card stat"><div class="num">' + esc(au.backend && au.backend !== "none" ? "Yes" : "No") + '</div><div class="lbl">AI stage used' + (au.model ? " · " + esc(au.model) : "") + '</div></div></div>');
    if (au.problem) h.push('<div class="note amber">' + esc(au.problem) + "</div>");
    h.push('<div class="table"><table><thead><tr><th>ID</th><th>Estimate</th><th class="n">Paper</th><th class="n">Found</th><th>How</th><th>Verdict</th></tr></thead><tbody>');
    cl.forEach(function (c) {
      var rb = c.rebuilt || {}, cm = c.compare || {}, v = VERD[cm.verdict] || VERD.not_found;
      h.push("<tr><td class='mono'>" + esc(c.id) + "</td><td class='desc'>" + esc(c.description) + (c.main ? ' <span class="pill p-published" style="padding:2px 8px;font-size:11px">Headline</span>' : "") +
        "</td><td class='n'>" + esc(c.b) + (c.se ? "<div class='sub'>(" + esc(c.se) + ")</div>" : "") + "</td><td class='n'>" + (rb.b != null ? fmt(rb.b) + "<div class='sub'>(" + fmt(rb.se) + ")</div>" : "—") +
        "</td><td class='sub'>" + esc(METHOD[cm.method] || "—") + "</td><td><span class='pill " + v[1] + "'>" + v[0] + "</span></td></tr>");
    });
    h.push("</tbody></table></div>");
    h.push('<div class="btns"><a class="btn" href="audits/' + esc(slug) + '/index.html">Open the full audit</a></div>' +
      '<p class="tiny" style="margin-top:10px">The full page appears a minute or two after the results.</p>');
    $("results").innerHTML = h.join("");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var r = new URLSearchParams(location.search).get("r");
    if (!r) { try { r = localStorage.getItem("ra-last-request"); } catch (e) {} if (r) history.replaceState(null, "", "?r=" + r); }
    $("go-track").addEventListener("click", function () {
      var v = ($("rnum").value || "").replace(/\D/g, ""); if (v) { history.replaceState(null, "", "?r=" + v); load(v); }
    });
    if (r && /^\d+$/.test(r)) load(r); else { $("ask").hidden = false; $("track").hidden = true; }
  });
})();
