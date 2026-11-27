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

  // ---------- progress bar ----------
  // The percentage comes from the live GitHub Actions run for this request: each finished step moves
  // the bar, and the long "run the audit" step advances with elapsed time (it is an estimate there).
  function setProgress(pct, label, note, mode) {
    pct = Math.max(0, Math.min(100, Math.round(pct)));
    var bar = $("pbar"); if (!bar) return;
    bar.className = "card pbar" + (mode ? " " + mode : "");
    $("p-fill").style.width = pct + "%";
    $("p-pct").textContent = pct + "%";
    $("p-track").setAttribute("aria-valuenow", pct);
    if (label) $("p-label").textContent = label;
    $("p-note").textContent = note || "";
  }
  var shown = 0; // never move backwards
  function moveTo(pct, label, note) { shown = Math.max(shown, pct); setProgress(shown, label, note, "live"); }

  function stepsDone(job) {
    var st = job.steps || [], n = st.length || 1, d = 0;
    st.forEach(function (x) { if (x.status === "completed") d++; else if (x.status === "in_progress") d += 0.5; });
    return d / n;
  }
  function mins(a, b) { return Math.max(0, ((b ? new Date(b) : new Date()) - new Date(a)) / 60000); }

  function fromJobs(jobs) {
    var byName = {}; jobs.forEach(function (j) { byName[j.name] = j; });
    var f = byName.fetch, a = byName.audit, p = byName.publish;
    if (p && p.status !== "queued") {
      return [90 + 9 * stepsDone(p), "Publishing the results, charts and report…", p.status === "completed"];
    }
    if (a && a.status !== "queued") {
      var st = a.steps || [], run = null, before = 0, total = 0;
      st.forEach(function (x) { if (/run the audit/i.test(x.name)) run = x; });
      if (run && run.status === "completed") return [89, "Audit finished; saving the results…", false];
      if (run && run.status === "in_progress") {
        var t = mins(run.started_at);
        return [50 + 38 * (1 - Math.exp(-t / 30)), "Running the authors' code and checking every number…",
                false, Math.round(t) + " min so far in this step. Typical total: 20–90 minutes."];
      }
      st.forEach(function (x) { if (run && x.number >= run.number) return; total++; if (x.status === "completed") before++; });
      return [25 + 25 * (total ? before / total : 0), "Preparing the computer: installing R, Python and the free model…", false];
    }
    if (f && f.status !== "queued") return [10 + 15 * stepsDone(f), "Downloading the paper, data and code…", false];
    return [10, "Waiting in line. Audits run one at a time.", false];
  }

  var runId = null, lastTitle = null;
  function busy(e, again) {
    $("t-err").textContent = /rate limit|403/i.test(e.message)
      ? "Live updates are paused for a few minutes (GitHub's limit for visitors). The audit itself keeps running."
      : e.message;
    timer = setTimeout(again, /rate limit|403/i.test(e.message) ? 300000 : 120000);
  }
  function gh(path) {
    return fetch("https://api.github.com/repos/" + REPO + path).then(function (res) {
      if (res.status === 404) throw new Error("No request with this number.");
      if (!res.ok) throw new Error(res.status === 403 ? "rate limit" : "The status service is busy. It will retry shortly.");
      return res.json();
    });
  }

  function load(r) {
    clearTimeout(timer);
    $("ask").hidden = true; $("track").hidden = false;
    gh("/issues/" + r).then(function (iss) {
      $("t-err").textContent = "";
      var labels = (iss.labels || []).map(function (l) { return l.name; });
      $("t-title").textContent = (iss.title || "").replace(/^\[Audit\]\s*/, "");
      $("t-meta").textContent = "Request #" + r + " · received " + new Date(iss.created_at).toLocaleString();
      step("s1", "done", "We have your request and materials.");
      var done = labels.indexOf("results-ready") >= 0, failed = labels.indexOf("audit-failed") >= 0;
      if (failed) { setProgress(100, "The audit stopped before finishing.", "Details are below.", "bad"); step("s2", "done"); step("s3", "bad", "The audit couldn't be completed. The details are below."); return showResults(iss); }
      if (done) { setProgress(100, "Done. Results are below.", "", "ok"); step("s2", "done", "Finished."); step("s3", "done", "Results are below."); return showResults(iss); }
      step("s2", "now", "Running the authors' code and checking every number. This usually takes 20–90 minutes."); step("s3", "todo");
      moveTo(8, "Request received. Starting the audit…");
      track(r);
    }).catch(function (e) { busy(e, function () { load(r); }); });
  }

  // One GitHub call per refresh while the audit runs (visitors may make 60 an hour).
  function track(r) {
    clearTimeout(timer);
    var findRun = runId ? Promise.resolve(runId) :
      gh("/actions/workflows/audit.yml/runs?per_page=40").then(function (j) {
        var hit = (j.workflow_runs || []).filter(function (w) { return w.display_title === "Audit request #" + r; })[0];
        if (hit) runId = hit.id;
        return runId;
      });
    findRun.then(function (id) {
      if (!id) { moveTo(8, "Request received. Starting the audit…", "The audit starts within a few minutes."); timer = setTimeout(function () { track(r); }, 75000); return; }
      return gh("/actions/runs/" + id + "/jobs").then(function (j) {
        $("t-err").textContent = "";
        var jobs = j.jobs || [];
        var allDone = jobs.length && jobs.every(function (x) { return x.status === "completed"; });
        var failedJob = jobs.some(function (x) { return x.conclusion === "failure" || x.conclusion === "cancelled"; });
        if (allDone || failedJob) { timer = setTimeout(function () { load(r); }, 15000); moveTo(99, "Finishing up…"); return; }
        var x = fromJobs(jobs);
        moveTo(x[0], x[1], x[3] || "Updates every minute or so. You can close this page and come back later.");
        timer = setTimeout(function () { track(r); }, 75000);
      });
    }).catch(function (e) { busy(e, function () { track(r); }); });
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

  // A request sent from the website first waits in the intake queue (code like 3fa9c01b5e2d4a77);
  // GitHub picks it up within a few minutes and gives it a request number.
  function loadQueued(q) {
    clearTimeout(timer);
    $("ask").hidden = true; $("track").hidden = false;
    var API = document.body.getAttribute("data-api") || "https://replicaudit-intake.netlify.app";
    fetch(API + "/api/status?id=" + q)
      .then(function (res) { return res.json().then(function (j) { if (!res.ok) throw new Error(j.error || "The status service is busy. It will retry shortly."); return j; }); })
      .then(function (j) {
        if (j.issue) {
          try { localStorage.setItem("ra-last-request", String(j.issue)); } catch (e) {}
          history.replaceState(null, "", "?r=" + j.issue); return load(String(j.issue));
        }
        $("t-title").textContent = (j.title || "").replace(/^\[Audit\]\s*/, "");
        $("t-meta").textContent = "Request code " + q + " · received " + new Date(j.created).toLocaleString();
        step("s1", "done", "We have your request and materials.");
        step("s2", "now", "Waiting to be picked up. New requests are collected every few minutes.");
        moveTo(4, "Received. Waiting to be picked up…", "New requests are collected every 5 minutes.");
        step("s3", "todo");
        timer = setTimeout(function () { loadQueued(q); }, 60000);
      })
      .catch(function (e) { $("t-err").textContent = e.message; timer = setTimeout(function () { loadQueued(q); }, 120000); });
  }
  function open(v) {
    v = (v || "").trim();
    if (/^[a-f0-9]{16}$/i.test(v)) { history.replaceState(null, "", "?q=" + v.toLowerCase()); return loadQueued(v.toLowerCase()); }
    v = v.replace(/\D/g, "");
    if (v) { history.replaceState(null, "", "?r=" + v); return load(v); }
    $("ask").hidden = false; $("track").hidden = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var p = new URLSearchParams(location.search), r = p.get("q") || p.get("r");
    if (!r) { try { r = localStorage.getItem("ra-last-request"); } catch (e) {} }
    $("go-track").addEventListener("click", function () { open($("rnum").value); });
    open(r);
  });
})();
