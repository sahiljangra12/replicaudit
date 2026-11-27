"""Static website (GitHub Pages) built from the audits/ folder.

    python -m replicaudit site --audits audits --out _site [--include-drafts]

Only audits whose submission.json status is "published" appear unless --include-drafts is given.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from . import __version__
from .compare import VERDICTS, stars

REPO = "https://github.com/sahiljangra12/replicaudit"
SITE_TITLE = "ReplicAudit"
E = html.escape


def _f(x, d=4):
    return "—" if x is None else f"{x:.{d}f}"


def page(title, body, depth=0, active="", desc=""):
    up = "../" * depth
    nav = [("index.html", "Registry"), ("methods.html", "Methods"), ("submit.html", "Submit a paper"),
           ("policy.html", "Policy"), (REPO, "GitHub")]
    links = "".join(
        f'<a href="{h if h.startswith("http") else up + h}"{" aria-current=page" if h == active else ""}>{E(t)}</a>'
        for h, t in nav)
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} · {SITE_TITLE}</title>
<meta name="description" content="{E(desc or 'Open, automated replication audits of published empirical research.')}">
<link rel="stylesheet" href="{up}style.css"><script src="{up}site.js"></script></head>
<body><header class="site"><div class="wrap"><a class="brand" href="{up}index.html">Replic<span>Audit</span></a>
<nav>{links}<button class="theme" id="theme" type="button" aria-label="Switch colour theme">Dark</button></nav></div></header>
<main><div class="wrap">{body}</div></main>
<footer><div class="wrap">ReplicAudit v{__version__} · Code MIT, audit reports CC BY 4.0 ·
Audits are produced by an AI-assisted pipeline and reviewed by a person before publication. See <a href="{up}methods.html">Methods</a> and <a href="{up}policy.html">Policy</a>.</div></footer>
</body></html>"""


SHORT = {"exact": "Reproduced", "close": "Close", "same_sign": "Size differs", "different": "Sign differs",
         "failed": "Not rebuilt", "pending": "Pending"}


def badge(v):
    return f'<span class="badge v-{E(v)}" title="{E(VERDICTS.get(v, v))}">{E(SHORT.get(v, v))}</span>'


# ------------------------------------------------------------------ loading
def front_matter(text):
    meta, body = {}, text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body


def md_to_html(text):
    """Small, safe Markdown subset: paragraphs, bullet lists, **bold**, *italic*, `code`, [links](url)."""
    out, para, items = [], [], []

    def inline(s):
        s = E(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in text.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith(("- ", "* ")):
            if para:
                flush()
            items.append(s[2:])
        elif s.startswith("#"):
            flush()
            out.append(f"<h3>{inline(s.lstrip('#').strip())}</h3>")
        else:
            para.append(s)
    flush()
    return "\n".join(out)


def load_audits(root: Path, include_drafts=False):
    audits = []
    for d in sorted(Path(root).glob("*/")):
        sj = d / "submission.json"
        if not sj.exists():
            continue
        sub = json.loads(sj.read_text())
        if sub.get("status") != "published" and not include_drafts:
            continue
        aj = d / "audit.json"
        audit = json.loads(aj.read_text()) if aj.exists() else {"claims": []}
        review = front_matter((d / "review.md").read_text()) if (d / "review.md").exists() else ({}, "")
        response = front_matter((d / "author_response.md").read_text()) if (d / "author_response.md").exists() else ({}, "")
        audits.append({"dir": d, "slug": d.name, "sub": sub, "audit": audit, "review": review, "response": response})
    return audits


def summarize(a):
    claims = a["audit"].get("claims", [])
    v = [(c.get("compare") or {}).get("verdict", "failed") for c in claims]
    head = next((c for c in claims if c.get("main")), None)
    rs = ((head or {}).get("robustness") or {}).get("summary") or {}
    return {"n": len(claims), "exact": v.count("exact"), "close": v.count("close"),
            "counts": {k: v.count(k) for k in VERDICTS}, "head": head, "rs": rs}


# ------------------------------------------------------------------ pages
def index_page(audits):
    sums = [summarize(a) for a in audits]
    n_claims = sum(s["n"] for s in sums)
    n_exact = sum(s["exact"] for s in sums)
    n_fragile = sum(1 for s in sums if s["rs"].get("fragile"))
    fields = sorted({a["sub"].get("field") or "Other" for a in audits})
    rows = []
    for a, s in zip(audits, sums):
        sub = a["sub"]
        rob = ("—" if not s["rs"].get("n") else
               (f'<span class="flag">Fragile</span> ({s["rs"]["share_same_sign_sig05"]:.0%} of {s["rs"]["n"]})'
                if s["rs"].get("fragile") else
                f'<span class="good">Holds</span> ({s["rs"]["share_same_sign_sig05"]:.0%} of {s["rs"]["n"]})'))
        status = sub.get("status", "")
        text = " ".join(str(sub.get(k) or "") for k in ("title", "authors", "journal_year", "doi", "field")).lower()
        rows.append(
            f'<tr data-text="{E(text)}" data-field="{E(sub.get("field") or "Other")}">'
            f'<td><a href="audits/{E(a["slug"])}/index.html"><b>{E(sub.get("title") or a["slug"])}</b></a>'
            f'<div class="meta">{E(sub.get("authors") or "")} · {E(sub.get("journal_year") or "")}</div></td>'
            f'<td>{E(sub.get("field") or "")}</td>'
            f'<td class="num">{s["exact"]} / {s["n"]}</td><td>{rob}</td>'
            f'<td>{E(status.capitalize())}</td>'
            f'<td class="num">{E((a["review"][0] or {}).get("date") or sub.get("submitted") or "")}</td></tr>')
    table = ("".join(rows) if rows else
             '<tr><td colspan="6" class="empty">No audits have been published yet. '
             '<a href="submit.html">Submit the first paper.</a></td></tr>')
    body = f"""
<div class="kicker">Open replication registry</div>
<h1>Does the published result hold up?</h1>
<p class="lede">ReplicAudit re-runs the analyses of published empirical papers from their public data and code,
checks every reported number, and then tests whether the headline result survives reasonable alternative choices.
Every script, log and checksum is public, and a person reviews each audit before it is published.</p>
<p><a class="btn" href="submit.html">Submit a paper</a> &nbsp; <a class="btn ghost" href="methods.html">Read the protocol</a></p>
<div class="stats">
 <div class="stat"><b>{len(audits)}</b><span>papers audited</span></div>
 <div class="stat"><b>{n_claims}</b><span>reported estimates checked</span></div>
 <div class="stat"><b>{(n_exact / n_claims if n_claims else 0):.0%}</b><span>reproduced to the reported precision</span></div>
 <div class="stat"><b>{n_fragile}</b><span>headline results flagged fragile</span></div>
</div>
<h2>Registry</h2>
<div class="filters"><input id="q" type="search" placeholder="Search title, author, journal, DOI" aria-label="Search the registry">
<select id="field" aria-label="Filter by field"><option value="">All fields</option>{"".join(f"<option>{E(f)}</option>" for f in fields)}</select></div>
<div class="tablewrap"><table id="registry"><thead><tr><th>Paper</th><th>Field</th><th class="num">Reproduced</th>
<th>Headline robustness</th><th>Status</th><th class="num">Date</th></tr></thead><tbody>{table}</tbody></table></div>
<p class="meta">“Reproduced” counts estimates whose coefficient, standard error and sample size match the paper at the precision it reports.
“Holds” means at least 75% of robustness variants keep the same sign and 5% significance. Definitions are in the <a href="methods.html">protocol</a>.</p>"""
    return page("Registry", body, 0, "index.html")


def spec_chart(base, variants):
    ok = [v for v in variants if v.get("b") is not None and v.get("se")]
    if not ok or not base or base.get("b") is None:
        return ""
    rows = [("Original specification (rebuilt)", base["b"], base["se"])] + [(v["name"], v["b"], v["se"]) for v in ok]
    lo = min(min(b - 1.96 * s for _, b, s in rows), 0)
    hi = max(max(b + 1.96 * s for _, b, s in rows), 0)
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad
    W, L, R, rh = 880, 310, 24, 26
    H = rh * len(rows) + 46
    x = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Point estimates with 95% confidence intervals">',
         f'<line x1="{x(0):.1f}" y1="8" x2="{x(0):.1f}" y2="{H-30}" stroke="currentColor" opacity=".35" stroke-dasharray="4 3"/>']
    for i, (name, b, s) in enumerate(rows):
        y = 22 + i * rh
        sig = abs(b / s) > 1.96 and (b > 0) == (base["b"] > 0)
        col = "var(--ink)" if i == 0 else ("var(--accent)" if sig else "var(--bad)")
        p.append(f'<text x="{L-12}" y="{y+4}" text-anchor="end" font-size="12.5">{E(str(name))[:46]}</text>')
        p.append(f'<line x1="{x(b-1.96*s):.1f}" y1="{y}" x2="{x(b+1.96*s):.1f}" y2="{y}" stroke="{col}" stroke-width="2.2"/>')
        p.append(f'<circle cx="{x(b):.1f}" cy="{y}" r="4.8" fill="{col}"/>')
    for t in (lo, 0, hi):
        p.append(f'<text class="axis" x="{x(t):.1f}" y="{H-10}" text-anchor="middle" font-size="11.5">{t:.4f}</text>')
    p.append("</svg>")
    return '<div class="chart">' + "".join(p) + "</div>"


def bibtex(a):
    sub = a["sub"]
    year = (a["review"][0] or {}).get("date", sub.get("submitted", ""))[:4]
    return (f"@misc{{replicaudit_{a['slug'].replace('-', '_')},\n"
            f"  title  = {{Replication audit of: {sub.get('title')}}},\n"
            f"  author = {{{(a['review'][0] or {}).get('reviewer', 'ReplicAudit')} and ReplicAudit}},\n"
            f"  year   = {{{year}}},\n  howpublished = {{\\url{{https://sahiljangra12.github.io/replicaudit/audits/{a['slug']}/}}}},\n"
            f"  note   = {{Audit of doi:{sub.get('doi')}}}\n}}")


def audit_page(a):
    sub, au = a["sub"], a["audit"]
    s = summarize(a)
    claims = au.get("claims", [])
    rmeta, rbody = a["review"]
    pkg = sub.get("package") or {}
    env = au.get("environment") or {}
    doi = (sub.get("doi") or "").replace("https://doi.org/", "").replace("doi:", "")
    parts = [f'<div class="kicker">Replication audit · {E(sub.get("status", ""))}</div>',
             f'<h1>{E(sub.get("title") or a["slug"])}</h1>',
             f'<p class="cite">{E(sub.get("authors") or "")} · <i>{E(sub.get("journal_year") or "")}</i> · '
             f'<a href="https://doi.org/{E(doi)}">doi:{E(doi)}</a></p>']
    if sub.get("status") != "published":
        parts.append('<div class="box warn"><p><b>Draft.</b> This audit has not been reviewed and published. Do not cite it.</p></div>')

    # summary
    c = s["counts"]
    summ = [f"<b>{c['exact']} of {s['n']}</b> reported estimates reproduced to the paper's precision"]
    if c.get("close"):
        summ.append(f"{c['close']} close")
    if c.get("same_sign") or c.get("different"):
        summ.append(f"{c.get('same_sign', 0) + c.get('different', 0)} differ")
    if c.get("failed"):
        summ.append(f"{c['failed']} could not be rebuilt")
    rs = s["rs"]
    rob = ""
    if rs.get("n"):
        rob = (f"<p>Headline result: same sign and significant at 5% in <b>{rs['share_same_sign_sig05']:.0%}</b> of "
               f"{rs['n']} robustness variants (range {rs['min_b']:.4f} to {rs['max_b']:.4f}) — "
               + ('<span class="flag">fragile</span>.' if rs.get("fragile") else '<span class="good">holds</span>.') + "</p>")
    parts.append('<h2>Summary</h2><div class="box"><p>' + "; ".join(summ) + ".</p>" + rob + "</div>")
    if rbody.strip():
        parts.append(f'<h3>Reviewer’s assessment</h3><div class="prose">{md_to_html(rbody)}</div>'
                     f'<p class="meta">Reviewed by {E(rmeta.get("reviewer", "—"))}, {E(rmeta.get("date", ""))}.</p>')
    if au.get("note"):
        parts.append(f'<div class="box warn"><p>{E(au["note"])}</p></div>')

    # claims
    rows = []
    for cl in claims:
        rb = cl.get("rebuilt") or {}
        cm = cl.get("compare") or {}
        pb = f"{E(str(cl['b']))}{cm.get('target_stars', '')}" + (f" ({E(str(cl['se']))})" if cl.get("se") else "")
        mine = f"{_f(rb.get('b'))}{stars(cm.get('p'))} ({_f(rb.get('se'))})" if rb else "—"
        script = (f'<a href="{REPO}/blob/main/audits/{a["slug"]}/scripts/{E(cl["script"])}">script</a>'
                  if cl.get("script") else "")
        rows.append(f"<tr><td class='mono'>{E(cl['id'])}</td><td class='desc'>{E(cl['description'])}</td><td class='num'>{pb}</td>"
                    f"<td class='num'>{mine}</td><td class='num'>{E(str(cl.get('n') or ''))}</td>"
                    f"<td class='num'>{E(str(rb.get('n') or ''))}</td><td>{badge(cm.get('verdict', 'pending'))}</td>"
                    f"<td class='num'>{len(cl.get('attempts', []))}</td><td>{script}</td></tr>")
    parts.append('<h2>Reported estimates</h2><div class="tablewrap"><table><thead><tr><th>ID</th><th>Estimate</th>'
                 '<th class="num">Paper b (se)</th><th class="num">Rebuilt b (se)</th><th class="num">Paper N</th>'
                 '<th class="num">Rebuilt N</th><th>Verdict</th><th class="num">Tries</th><th></th></tr></thead><tbody>'
                 + "".join(rows) + "</tbody></table></div>"
                 '<p class="meta">Stars: *** p&lt;0.01, ** p&lt;0.05, * p&lt;0.10 (normal approximation from b/se).</p>')

    # robustness
    for cl in claims:
        R = cl.get("robustness") or {}
        if not R.get("variants"):
            continue
        parts.append(f"<h2>Robustness of {E(cl['id'])}</h2><p class='meta'>{E(cl['description'])}. "
                     "Points are estimates with 95% intervals; teal = same sign and significant at 5%, red = not.</p>")
        parts.append(spec_chart(cl.get("rebuilt"), R["variants"]))
        vr = "".join(
            f"<tr><td>{E(str(v.get('name')))}</td><td>{E(str(v.get('why') or ''))}</td>"
            f"<td class='num'>{_f(v.get('b'))}{stars(v.get('p'))}</td><td class='num'>{_f(v.get('se'))}</td>"
            f"<td class='num'>{E(str(v.get('n', '')))}</td></tr>" if v.get("b") is not None else
            f"<tr><td>{E(str(v.get('name')))}</td><td colspan=4 class='meta'>failed: {E(str(v.get('error', ''))[:160])}</td></tr>"
            for v in R["variants"])
        parts.append('<div class="tablewrap"><table><thead><tr><th>Variant</th><th>Rationale</th><th class="num">b</th>'
                     '<th class="num">se</th><th class="num">N</th></tr></thead><tbody>' + vr + "</tbody></table></div>")

    # provenance
    prov = [("Paper DOI", f'<a href="https://doi.org/{E(doi)}">{E(doi)}</a>'),
            ("Replication package", f'<a href="{E(pkg.get("resolved_url") or pkg.get("source") or "")}">{E(pkg.get("source") or "—")}</a>'),
            ("Package type / version", E(" · ".join(str(x) for x in (pkg.get("kind"), pkg.get("version") or pkg.get("commit")) if x))),
            ("Package files (SHA-256 manifest)", f'{len(pkg.get("manifest", []))} files · <span class="mono">{E(pkg.get("package_sha256", "")[:24])}…</span>'),
            ("Supplementary materials", E((sub.get("supplement") or {}).get("source", "—") if isinstance(sub.get("supplement"), dict) else "—")),
            ("Claims source", "submitted table" if (a["dir"] / "claims_submitted.csv").exists() or (a["dir"] / "claims.csv").exists()
             else "extracted from the paper by the model"),
            ("Model", E(f"{au.get('backend', '')} {au.get('model') or ''}")),
            ("Pipeline", E(f"ReplicAudit {env.get('replicaudit', '')} · Python {env.get('python', '')} · pandas {env.get('pandas', '')} · pyfixest {env.get('pyfixest', '')}")),
            ("Run", E(f"{au.get('started', '')} → {au.get('finished', '')} · {au.get('llm_calls', '—')} model calls")),
            ("Submitted by", E(f"{sub.get('relationship') or ''}" + (f" · issue #{sub['issue']}" if sub.get("issue") else ""))),
            ("All files", f'<a href="{REPO}/tree/main/audits/{a["slug"]}">audits/{E(a["slug"])}</a> (scripts, model prompts and answers, audit.json, results.csv)')]
    parts.append('<h2>Provenance</h2><dl class="prov">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in prov) + "</dl>")

    rm, rbody2 = a["response"]
    parts.append("<h2>Authors’ response</h2>" + (
        f'<div class="prose">{md_to_html(rbody2)}</div><p class="meta">{E(rm.get("by", ""))} {E(rm.get("date", ""))}</p>'
        if rbody2.strip() else
        (f'<p class="meta">The corresponding authors were invited to respond on {E(sub["authors_contacted"])}. '
         'No response has been received. Authors can respond at any time; see the <a href="../../policy.html">policy</a>.</p>'
         if sub.get("authors_contacted") else
         '<p class="meta">The authors have not yet been contacted. Under the <a href="../../policy.html">policy</a> they are '
         'invited to respond before this audit is published.</p>')))

    parts.append('<h2>Cite this audit</h2><pre>' + E(bibtex(a)) + "</pre>"
                 f'<p class="meta">Downloads: <a href="results.csv">results.csv</a> · <a href="audit.json">audit.json</a> · '
                 '<a href="report.html">full machine report</a></p>')
    return page(sub.get("title") or a["slug"], "\n".join(parts), 2,
                desc=f"Replication audit of {sub.get('title')}")


METHODS = """
<div class="kicker">Protocol v1 · ReplicAudit {version}</div>
<h1>Methods</h1>
<p class="lede">A fixed, published procedure applied the same way to every paper. Anything that changes the procedure changes its version number, and every audit records the version it used.</p>
<div class="prose">
<h2>1. Scope</h2>
<p>We audit quantitative empirical papers whose data and code (a <i>replication package</i>) are publicly available. Priority goes to environmental, ecological, energy and sustainability research. We do not collect new data. An audit therefore tests <b>computational reproducibility</b> (same data, same method, same numbers) and <b>robustness</b> (same data, reasonable alternative choices). It does not test <b>replicability</b> in new samples.</p>
<h2>2. Inputs and provenance</h2>
<p>For each paper we record the DOI, the exact source of the replication package (repository, version or commit), and a SHA-256 checksum of every file. Packages and papers are downloaded for the run and are not redistributed by us. The checksums let anyone confirm that they are auditing the same files.</p>
<h2>3. Claims</h2>
<p>A <i>claim</i> is a single reported estimate: a coefficient with its standard error and sample size, in a named table and column. Claims come from a table submitted with the request or are extracted from the paper and supplementary materials by the model. A reviewer checks the claims list against the paper before publication, and the audit records which source was used. The paper's headline result is marked as the <i>main</i> claim.</p>
<h2>4. Rebuilding the analysis</h2>
<p>A language model (recorded on each audit page) writes Python code in two stages. First it writes one script that builds the analysis dataset, following the authors' own data-preparation code. Then it writes one script per claim that re-estimates it. Each script runs in a separate process, with no credentials and a time limit. If a script fails, or its result does not match, the error or the mismatch is returned to the model, up to four attempts per claim. The number of attempts is reported. Scripts that contain the paper's reported value as a literal number are rejected automatically, so every result must be computed from the data.</p>
<h2>5. Verdicts</h2>
<ul>
<li><b>Reproduced</b>: the coefficient and standard error equal the paper's values after rounding to the number of decimals the paper prints, and the sample size matches where it is reported.</li>
<li><b>Close</b>: same sign and within 5% of the reported coefficient, or an exact coefficient with a different sample size.</li>
<li><b>Same sign, different size</b>: the direction holds but the magnitude does not.</li>
<li><b>Different</b>: the sign is reversed.</li>
<li><b>Could not rebuild</b>: no working script within the attempt limit. This is a statement about our pipeline, not about the paper.</li>
</ul>
<h2>6. Robustness</h2>
<p>For the main claim, the model proposes up to eight alternative specifications that a careful referee could reasonably ask for. These include alternative controls, samples, fixed effects, clustering, outcome measures and outlier treatment, and checks of the measurement or observation process. Each variant is run and shown with a 95% interval. A headline result is called <b>fragile</b> when fewer than 75% of variants keep the original sign and significance at the 5% level. Robustness variants are not pre-registered against the paper. They are a structured sensitivity analysis, and a reviewer removes any variant that is not a defensible alternative before publication.</p>
<h2>7. Human review</h2>
<p>No audit is published automatically. A named reviewer checks the claims list, reads the scripts behind every non-reproduced verdict, checks that the robustness variants are reasonable, and writes a short assessment. Audits appear as pull requests, so the review and any changes are on the public record.</p>
<h2>8. Authors' right of reply</h2>
<p>Corresponding authors are contacted before publication and given at least 14 days to respond. Their response is published on the audit page without editing.</p>
<h2>9. Openness</h2>
<p>For every audit we publish the scripts, the full model prompts and answers, the verdicts and the provenance. A run can be repeated exactly by replaying the saved answers with <code>--backend replay</code>, or repeated independently with a live model.</p>
<h2>10. Limitations</h2>
<ul>
<li>Translating code between languages (e.g. Stata to Python) can produce small numerical differences, such as different small-sample corrections or percentile definitions. A “Close” verdict often reflects this rather than an error in the paper.</li>
<li>A model can misread a specification. That is why every verdict links to its script and every non-reproduced verdict is checked by a person.</li>
<li>Robustness checks are chosen after seeing the data and cannot cover every defensible analysis. A fragile result is a reason for scrutiny, not proof that the result is wrong.</li>
<li>Packages with restricted data, or data that need a login, cannot be audited automatically.</li>
</ul>
<h2>Related work</h2>
<p>This project builds on computational-reproducibility benchmarks for AI agents (CORE-Bench, REPRO-Bench, ReplicatorBench, PaperBench, ReplicationBench) and on human replication efforts such as the Institute for Replication. It differs in running audits on published literature, not benchmarks, and in reporting robustness alongside reproduction.</p>
</div>"""

SUBMIT = """
<div class="kicker">Submit a paper</div>
<h1>Request an audit</h1>
<p class="lede">Anyone can request an audit: authors, referees, students or readers. Requests are made through a structured form on GitHub, and everything after that is public.</p>
<p><a class="btn" href="{repo}/issues/new?template=audit-request.yml">Open the submission form</a></p>
<h2>What you need</h2>
<div class="tablewrap"><table><thead><tr><th>Item</th><th>Required</th><th>How to provide it</th></tr></thead><tbody>
<tr><td><b>Paper DOI</b> and title</td><td>Yes</td><td>Type them into the form.</td></tr>
<tr><td><b>Replication package</b> (data + code)</td><td>Yes</td><td>A DOI or link to Zenodo, Harvard Dataverse (or any Dataverse), OSF, a GitHub repository, or a direct .zip link. Or drag a .zip of up to 25 MB into the form. Archives inside the package (.zip, .rar, .7z, .tar.gz) are unpacked automatically.</td></tr>
<tr><td><b>Paper PDF</b></td><td>Recommended</td><td>An open-access link, or attach the PDF. It is used to find the reported estimates and is not stored.</td></tr>
<tr><td><b>Supplementary materials</b> (SM)</td><td>If the estimates are there</td><td>Link or attach the supplement PDF.</td></tr>
<tr><td><b>Claims table</b></td><td>Optional</td><td>Rows of <code>id,description,b,se,n,main</code>, with numbers exactly as printed, e.g. <code>T1c3,"Table 1 col 3: outcome on treatment",-.0125,.0037,46371,true</code>. If you leave it out, the claims are extracted from the PDF and checked by the reviewer.</td></tr>
</tbody></table></div>
<p class="meta">Packages behind a login, such as openICPSR, cannot be fetched automatically. Attach them as a .zip if their licence allows it.</p>
<h2>What happens next</h2>
<ol class="steps">
<li>A maintainer checks that the request is in scope and labels it <code>run-audit</code>.</li>
<li>The pipeline downloads the materials, records checksums and runs the audit. The results are opened as a pull request linked to your request.</li>
<li>A reviewer checks the claims, the scripts and the robustness variants and writes an assessment.</li>
<li>The corresponding authors are invited to respond, with at least 14 days to do so.</li>
<li>The audit is merged and published in the registry with its response, if any.</li>
</ol>
<h2>Run it yourself</h2>
<pre>pip install -r requirements.txt
python -m replicaudit run --package path/to/package --paper paper.pdf --out runs/mypaper</pre>
<p class="meta">See the <a href="{repo}#readme">README</a> for using Claude, a free local model through Ollama, or replaying a published audit.</p>"""

POLICY = """
<div class="kicker">Policy</div>
<h1>Conduct, corrections and disclosure</h1>
<div class="prose">
<h2>Purpose</h2>
<p>Audits exist to make published results easier to trust and to build on. They are not judgements of authors. A result that fails to reproduce or is fragile under our protocol is reported in neutral terms, together with the exact code that produced the finding.</p>
<h2>Language</h2>
<p>We describe what our scripts found under a stated protocol, for example “not reproduced under protocol v1”. We do not use words such as “wrong”, “error” or “misconduct”. When we cannot rebuild an estimate, we say so and attribute it to our pipeline unless the reviewer finds a specific cause.</p>
<h2>Authors' right of reply</h2>
<p>Corresponding authors are contacted before publication and have at least 14 days to respond. Responses are published unedited. Authors may add or update a response at any time by opening an issue or emailing the maintainer.</p>
<h2>Corrections</h2>
<p>If an audit contains a mistake, open an issue. Corrections are made in a new commit, the audit page states what changed, and earlier versions stay in the Git history.</p>
<h2>Use of AI</h2>
<p>The analysis code in each audit is written by a large language model, named on each audit page. All prompts and answers are published. A person reviews every audit before publication and is responsible for it.</p>
<h2>Data and licences</h2>
<p>We do not redistribute authors' data or papers. We publish file checksums, our own scripts and our results. Code is released under the MIT licence and audit reports under CC BY 4.0.</p>
<h2>Conflicts of interest</h2>
<p>Reviewers state any relationship with the authors or the paper. Requests from authors of a competing paper are marked as such.</p>
<h2>Contact</h2>
<p>Maintainer: Sahil, Johns Hopkins University · <a href="mailto:sfnu1@jh.edu">sfnu1@jh.edu</a> · <a href="{repo}/issues">GitHub issues</a></p>
</div>"""


def build_site(audits_dir="audits", out="_site", include_drafts=False, static_dir=None):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    static = Path(static_dir) if static_dir else Path(__file__).resolve().parent.parent / "site_src"
    for f in ("style.css", "site.js"):
        shutil.copy(static / f, out / f)
    audits = load_audits(audits_dir, include_drafts)
    (out / "index.html").write_text(index_page(audits), encoding="utf-8")
    (out / "methods.html").write_text(page("Methods", METHODS.format(version=__version__), 0, "methods.html"), encoding="utf-8")
    (out / "submit.html").write_text(page("Submit a paper", SUBMIT.format(repo=REPO), 0, "submit.html"), encoding="utf-8")
    (out / "policy.html").write_text(page("Policy", POLICY.format(repo=REPO), 0, "policy.html"), encoding="utf-8")
    for a in audits:
        d = out / "audits" / a["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(audit_page(a), encoding="utf-8")
        for f in ("results.csv", "audit.json", "report.html"):
            if (a["dir"] / f).exists():
                shutil.copy(a["dir"] / f, d / f)
    (out / ".nojekyll").write_text("")
    return out
