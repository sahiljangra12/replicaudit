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
API = "https://replicaudit-intake.netlify.app"
SITE_URL = "https://sahiljangra12.github.io/replicaudit"
E = html.escape

SHORT = {"exact": "Reproduced", "close": "Close", "same_sign": "Size differs", "different": "Sign differs",
         "failed": "Not rebuilt", "not_found": "Not found", "pending": "Pending"}
METHOD = {"authors_code": "Authors' own code", "ai_rebuild": "AI rebuild"}

LOGO = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="10.5" stroke="currentColor" '
        'stroke-width="1.6"/><path d="M7.2 12.4l3.1 3.1 6.5-7" stroke="var(--blue)" stroke-width="2.1" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
SUN = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
       '<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>')
ICONS = {
    "fetch": '<path d="M12 3v12m0 0l-4.5-4.5M12 15l4.5-4.5M4 17v2.5A1.5 1.5 0 005.5 21h13a1.5 1.5 0 001.5-1.5V17"/>',
    "check": '<path d="M9 11.5l2.5 2.5L16 9.5"/><rect x="3.5" y="3.5" width="17" height="17" rx="4"/>',
    "stress": '<path d="M3 17l5-6 4 4 8-9"/><path d="M15 6h5v5"/>',
    "open": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5l3 2"/>',
    "review": '<path d="M16 3.5l4.5 4.5L9 19.5H4.5V15z"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 018 0v3"/>',
}


def icon(name):
    return (f'<div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg></div>')


def _f(x, d=4):
    return "—" if x is None else f"{x:.{d}f}"


def pill(kind, text=None):
    return f'<span class="pill p-{E(kind)}" title="{E(VERDICTS.get(kind, kind))}">{E(text or SHORT.get(kind, kind))}</span>'


def page(title, body, depth=0, active="", desc="", extra_js="", body_attrs=""):
    up = "../" * depth
    nav = [("index.html", "Registry"), ("submit.html", "Audit a paper"), ("status.html", "Track a request"),
           ("methods.html", "Methods"), ("policy.html", "Policy")]
    links = "".join(
        f'<a href="{h if h.startswith("http") else up + h}"{" aria-current=page" if h == active else ""}>{E(t)}</a>'
        for h, t in nav)
    d = E(desc or "Open, automated replication audits of published empirical research.")
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)} — ReplicAudit</title>
<meta name="description" content="{d}"><meta property="og:title" content="{E(title)} — ReplicAudit">
<meta property="og:description" content="{d}"><meta name="theme-color" content="#f5f5f7">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='10.5' fill='%231d1d1f'/%3E%3Cpath d='M7.2 12.4l3.1 3.1 6.5-7' stroke='%23fff' stroke-width='2.2' fill='none' stroke-linecap='round'/%3E%3C/svg%3E">
<link rel="stylesheet" href="{up}style.css"><script src="{up}site.js"></script>{extra_js}</head>
<body{body_attrs}>
<nav class="nav" aria-label="Main"><div class="wrap"><a class="brand" href="{up}index.html">{LOGO}ReplicAudit</a>
<div class="nav-links">{links}</div>
<button class="theme" id="theme" type="button" aria-label="Switch between light and dark">{SUN}</button>
<button class="menu" id="menu" type="button" aria-label="Menu" aria-expanded="false"><svg width="18" height="18" viewBox="0 0 18 18" stroke="currentColor" stroke-width="1.6"><path d="M2 6h14M2 12h14"/></svg></button>
</div></nav>
<main>{body}</main>
<footer><div class="wrap"><div class="cols">
<div>Audits are produced by an automated pipeline and checked by a person before publication.<br>
Each published audit comes with a full PDF report.</div>
<div class="links"><a href="{up}index.html">Registry</a><a href="{up}submit.html">Audit a paper</a><a href="{up}methods.html">Methods</a><a href="{up}policy.html">Policy</a><a href="{REPO}">Source code</a></div></div>
<div>ReplicAudit v{__version__} · Code MIT · Audit reports CC BY 4.0 · Maintained by Sahil, Johns Hopkins University</div></div></footer>
</body></html>"""


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
        if sub.get("status") in ("draft",) and not include_drafts:
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



def bibtex(a):
    sub = a["sub"]
    year = (a["review"][0] or {}).get("date", sub.get("submitted", ""))[:4]
    return (f"@misc{{replicaudit_{a['slug'].replace('-', '_')},\n"
            f"  title  = {{Replication audit of: {sub.get('title')}}},\n"
            f"  author = {{{(a['review'][0] or {}).get('reviewer', 'ReplicAudit')} and ReplicAudit}},\n"
            f"  year   = {{{year}}},\n  howpublished = {{\\url{{https://sahiljangra12.github.io/replicaudit/audits/{a['slug']}/}}}},\n"
            f"  note   = {{Audit of doi:{sub.get('doi')}}}\n}}")



# ------------------------------------------------------------------ pages
FIELDS = ["Ecology & biodiversity", "Climate & energy", "Environmental economics & policy",
          "Environment & health", "Agriculture & land use", "Other"]


def index_page(audits):
    audits = [a for a in audits if a["sub"].get("status") == "published" or a.get("show_in_registry")]
    sums = [summarize(a) for a in audits]
    n_claims = sum(s["n"] for s in sums)
    n_exact = sum(s["exact"] for s in sums)
    n_rob = sum(1 for s in sums if s["rs"].get("n"))
    n_fragile = sum(1 for s in sums if s["rs"].get("fragile"))
    fields = sorted({a["sub"].get("field") or "Other" for a in audits})
    rows = []
    for a, s in zip(audits, sums):
        sub = a["sub"]
        rs = s["rs"]
        rob = (pill("fragile", "Headline fragile") if rs.get("fragile") else pill("holds", "Headline holds")) if rs.get("n") else ""
        st = sub.get("status", "")
        stp = pill("published", "Published") if st == "published" else pill("draft", st.capitalize() or "Draft")
        text = " ".join(str(sub.get(k) or "") for k in ("title", "authors", "journal_year", "doi", "field")).lower()
        rows.append(
            f'<a class="row" href="audits/{E(a["slug"])}/index.html" data-text="{E(text)}" data-field="{E(sub.get("field") or "Other")}">'
            f'<div><div class="t">{E(sub.get("title") or a["slug"])}</div>'
            f'<div class="m">{E(sub.get("authors") or "")} · {E(sub.get("journal_year") or "")} · {E(sub.get("field") or "")}</div></div>'
            f'<div><b style="font-size:20px">{s["exact"]}/{s["n"]}</b> <span class="small">reproduced</span></div>'
            f'<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-start">{rob}{stp}</div>'
            f'<div class="chev">›</div></a>')
    listing = "".join(rows) or ('<div class="empty"><div class="h3" style="margin-bottom:8px">No published audits yet.</div>'
                                'Audits appear here once they have been reviewed and published with their report.<br><br>'
                                '<a class="btn small" href="submit.html">Audit the first paper</a></div>')
    pct = f"{n_exact / n_claims:.0%}" if n_claims else "—"
    stats = f"""<section class="sec alt tight"><div class="wrap wide"><div class="grid g4">
<div class="card stat reveal"><div class="num">{len(audits)}</div><div class="lbl">papers audited</div></div>
<div class="card stat reveal"><div class="num">{n_claims}</div><div class="lbl">reported estimates checked</div></div>
<div class="card stat reveal"><div class="num green">{pct}</div><div class="lbl">reproduced to the precision the paper reports</div></div>
<div class="card stat reveal"><div class="num{' red' if n_fragile else ''}">{n_fragile}<span class="small" style="font-size:20px;font-weight:600"> / {n_rob}</span></div><div class="lbl">headline results that failed robustness checks</div></div>
</div></div></section>

""" if audits else ""
    body = f"""
<section class="sec center" style="padding-top:110px"><div class="wrap">
<p class="eyebrow reveal">Open replication registry</p>
<h1 class="display reveal">Does the published<br>result hold up?</h1>
<p class="lead reveal">Paste a paper's DOI. ReplicAudit finds its data and code, re-runs the analysis, checks every reported number, and tests whether the headline finding survives reasonable alternatives. Any field, free, fully open.</p>
<div class="btns reveal"><a class="btn" href="submit.html">Audit a paper</a><a class="btn secondary" href="methods.html">Read the protocol</a></div>
</div></section>

{stats}<section class="sec"><div class="wrap wide">
<div class="head-row"><div><p class="eyebrow">Registry</p><h2 class="h2">Every audit, in the open.</h2></div>
<a class="link-arrow" href="methods.html#verdicts">How verdicts are defined</a></div>
<div class="search"><input class="field-in" id="q" type="search" placeholder="Search by title, author, journal or DOI" aria-label="Search the registry">
<select class="field-in" id="field" aria-label="Filter by field" style="max-width:280px"><option value="">All fields</option>{"".join(f"<option>{E(f)}</option>" for f in fields)}</select></div>
<div class="list">{listing}<div class="empty" id="nomatch" style="display:none">No audits match your search.</div></div>
</div></section>

<section class="sec alt"><div class="wrap wide">
<div class="center" style="margin-bottom:48px"><p class="eyebrow">How it works</p><h2 class="h1">From paper to verdict.<br>Nothing hidden.</h2></div>
<div class="grid g3">
<div class="card reveal">{icon("fetch")}<h3>Fetch and fingerprint.</h3><p>The replication package is downloaded from its repository, archives are unpacked, and every file gets a SHA-256 checksum, so anyone can confirm they are auditing the same files.</p></div>
<div class="card reveal">{icon("check")}<h3>Rebuild every number.</h3><p>The analysis is rebuilt from the authors' own code and each reported estimate is re-computed. It is compared with the paper at the precision the paper prints: coefficient, standard error and sample size.</p></div>
<div class="card reveal">{icon("stress")}<h3>Stress-test the headline.</h3><p>The main finding is re-estimated under alternative choices a careful referee would ask about: controls, samples, fixed effects, clustering and measurement.</p></div>
<div class="card reveal">{icon("review")}<h3>Reviewed by a person.</h3><p>No audit is published automatically. A named reviewer checks the claims, the scripts and the robustness variants, and writes an assessment.</p></div>
<div class="card reveal">{icon("open")}<h3>A full report.</h3><p>Every published audit comes with tables, charts and a typeset PDF report, including concrete suggestions for the authors and for readers.</p></div>
<div class="card reveal">{icon("lock")}<h3>Fully reproducible.</h3><p>Scripts, model prompts and answers, and checksums are public. Any audit can be replayed exactly, or re-run with a different model.</p></div>
</div></div></section>

<section class="sec center"><div class="wrap">
<h2 class="h1 reveal">Have a paper in mind?</h2>
<p class="lead reveal">Authors, referees, students and readers can all request an audit. Usually the DOI is all it takes.</p>
<div class="btns reveal"><a class="btn" href="submit.html">Audit a paper</a></div>
</div></section>"""
    return page("Registry", body, 0, "index.html")


def spec_chart(base, variants):
    ok = [v for v in variants if v.get("b") is not None and v.get("se")]
    if not ok or not base or base.get("b") is None:
        return ""
    rows = [("Original specification", base["b"], base["se"])] + [(v["name"], v["b"], v["se"]) for v in ok]
    lo = min(min(b - 1.96 * s for _, b, s in rows), 0)
    hi = max(max(b + 1.96 * s for _, b, s in rows), 0)
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad
    W, L, R, rh = 900, 300, 24, 32
    H = rh * len(rows) + 40
    x = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Estimates with 95% confidence intervals">',
         f'<line x1="{x(0):.1f}" y1="6" x2="{x(0):.1f}" y2="{H-28}" stroke="currentColor" opacity=".25" stroke-dasharray="3 4"/>']
    for i, (name, b, s) in enumerate(rows):
        y = 20 + i * rh
        sig = abs(b / s) > 1.96 and (b > 0) == (base["b"] > 0)
        col = "var(--ink)" if i == 0 else ("var(--blue)" if sig else "var(--red)")
        wt = "600" if i == 0 else "400"
        p.append(f'<text x="{L-16}" y="{y+5}" text-anchor="end" font-size="14" font-weight="{wt}">{E(str(name))[:42]}</text>')
        p.append(f'<line x1="{x(b-1.96*s):.1f}" y1="{y}" x2="{x(b+1.96*s):.1f}" y2="{y}" stroke="{col}" stroke-width="3" stroke-linecap="round" opacity=".85"/>')
        p.append(f'<circle cx="{x(b):.1f}" cy="{y}" r="6" fill="{col}" stroke="var(--card)" stroke-width="2"/>')
    for t in (lo, 0, hi):
        p.append(f'<text class="axis" x="{x(t):.1f}" y="{H-8}" text-anchor="middle" font-size="12">{t:.3f}</text>')
    p.append("</svg>")
    legend = ('<div class="legend"><span><i style="background:var(--ink)"></i>Original</span>'
              '<span><i style="background:var(--blue)"></i>Same sign, significant at 5%</span>'
              '<span><i style="background:var(--red)"></i>Sign changes or not significant</span><span>Lines: 95% intervals</span></div>')
    return '<div class="chart">' + legend + "".join(p) + "</div>"


def deviation_chart(claims):
    from .figures import deviation_rows
    rows = deviation_rows(claims)
    if not rows:
        return ""
    devs = [abs(d) for _, d, _ in rows if d is not None]
    lim = max(1.0, min(6.0, (max(devs) if devs else 1) * 1.25))
    W, L, R, rh = 900, 110, 30, 28
    H = rh * len(rows) + 56
    x = lambda v: L + (max(-lim, min(lim, v)) + lim) / (2 * lim) * (W - L - R)
    col = {"exact": "var(--green)", "close": "var(--green)", "same_sign": "var(--amber)", "different": "var(--red)"}
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Distance of each audited estimate from the published value">',
         f'<rect x="{x(-0.5):.1f}" y="6" width="{x(0.5) - x(-0.5):.1f}" height="{H - 46}" fill="var(--green)" opacity=".08"/>',
         f'<line x1="{x(0):.1f}" y1="6" x2="{x(0):.1f}" y2="{H - 40}" stroke="currentColor" opacity=".35"/>']
    for i, (lab, d, v) in enumerate(rows):
        y = 22 + i * rh
        p.append(f'<text x="{L - 14}" y="{y + 5}" text-anchor="end" font-size="13" font-family="var(--mono)">{E(lab)}</text>')
        if d is None:
            p.append(f'<text x="{L + 6}" y="{y + 5}" font-size="12" class="axis" font-style="italic">not found</text>')
        else:
            p.append(f'<circle cx="{x(d):.1f}" cy="{y}" r="6" fill="{col.get(v, "var(--ink-3)")}"/>')
    for t in (-lim, -0.5, 0, 0.5, lim):
        p.append(f'<text class="axis" x="{x(t):.1f}" y="{H - 22}" text-anchor="middle" font-size="12">{t:g}</text>')
    p.append(f'<text class="axis" x="{(L + W - R) / 2:.0f}" y="{H - 4}" text-anchor="middle" font-size="12">Audit minus paper, in the paper\'s standard errors (shaded: within rounding)</text></svg>')
    return '<div class="chart" style="margin-top:20px">' + "".join(p) + "</div>"


def audit_page(a):
    sub, au = a["sub"], a["audit"]
    s = summarize(a)
    claims = au.get("claims", [])
    rmeta, rbody = a["review"]
    pkg = sub.get("package") or {}
    env = au.get("environment") or {}
    doi = (sub.get("doi") or "").replace("https://doi.org/", "").replace("doi:", "")
    rs = s["rs"]
    c = s["counts"]
    st = sub.get("status", "")
    out = []

    out.append(f"""<section class="sec center" style="padding-bottom:64px"><div class="wrap">
<p class="eyebrow">{"Replication audit" if st == "published" else "Replication audit · Unreviewed"}</p>
<h1 class="h1">{E(sub.get("title") or a["slug"])}</h1>
<p class="lead" style="font-size:19px">{E(sub.get("authors") or "")} · <i>{E(sub.get("journal_year") or "")}</i><br>
<a href="https://doi.org/{E(doi)}">doi:{E(doi)}</a></p>
{('<div class="btns"><a class="btn" href="report.pdf">Download the report (PDF)</a></div>' if a.get("has_pdf") else "")}
{'' if st == "published" else '<div class="note amber" style="max-width:680px;margin:26px auto 0"><b>Automated result, not yet reviewed.</b> A person checks every audit before it is published with its full report. Please do not cite it yet.</div>'}
</div></section>""")

    head = s["head"]
    hb = (head or {}).get("rebuilt") or {}
    cards = [f'<div class="card stat"><div class="num green">{c["exact"]}<span style="font-size:28px">/{s["n"]}</span></div>'
             f'<div class="lbl">reported estimates reproduced exactly</div></div>']
    if head:
        cards.append(f'<div class="card stat"><div class="num">{_f(hb.get("b"))}</div><div class="lbl">headline estimate rebuilt '
                     f'(paper: {E(str(head["b"]))}, se {E(str(head.get("se") or "—"))})</div></div>')
    if rs.get("n"):
        cards.append(f'<div class="card stat"><div class="num {"red" if rs.get("fragile") else "green"}">{rs["share_same_sign_sig05"]:.0%}</div>'
                     f'<div class="lbl">of {rs["n"]} robustness checks keep the headline\'s sign and significance — '
                     f'{"fragile" if rs.get("fragile") else "holds"}</div></div>')
    out.append(f'<section class="sec alt tight"><div class="wrap wide"><div class="grid g{len(cards)}">{"".join(cards)}</div>')
    from .suggest import strip_suggestions
    if strip_suggestions(rbody).strip():
        out.append(f'<div class="card" style="margin-top:20px"><p class="eyebrow muted" style="font-size:14px">Reviewer’s assessment</p>'
                   f'<div class="article" style="margin:0;max-width:none">{md_to_html(strip_suggestions(rbody))}</div>'
                   f'<p class="small" style="margin-top:14px">{E(rmeta.get("reviewer", "—"))} · {E(rmeta.get("date", ""))}</p></div>')
    if au.get("note"):
        out.append(f'<div class="note blue" style="margin-top:20px">{E(au["note"])}</div>')
    out.append("</div></section>")

    # estimates
    rows = []
    for cl in claims:
        rb = cl.get("rebuilt") or {}
        cm = cl.get("compare") or {}
        pb = f"{E(str(cl['b']))}{cm.get('target_stars', '')}<div class='sub'>({E(str(cl['se']))})</div>" if cl.get("se") else E(str(cl["b"]))
        mine = f"{_f(rb.get('b'))}{stars(cm.get('p'))}<div class='sub'>({_f(rb.get('se'))})</div>" if rb else "—"
        nn = f"{E(str(cl.get('n') or '—'))}<div class='sub'>{E(str(rb.get('n') or '—'))}</div>"
        script = (f'<a href="{REPO}/blob/main/audits/{a["slug"]}/scripts/{E(cl["script"])}">Code</a>' if cl.get("script") else "")
        main = ' <span class="pill p-published" style="padding:2px 8px;font-size:11px">Headline</span>' if cl.get("main") else ""
        hits = (cl.get("authors_code") or {}).get("hits") or []
        if hits:
            script = (f'<details><summary class="small">Where</summary><div class="tiny mono" style="white-space:pre-wrap;max-width:420px">'
                      f'{E(hits[0]["file"])}, line {hits[0]["line"]}\n{E(hits[0]["snippet"][:400])}</div></details>')
        how = E(METHOD.get(cm.get("method"), "—"))
        rows.append(f"<tr><td class='mono'>{E(cl['id'])}</td><td class='desc'>{E(cl['description'])}{main}</td>"
                    f"<td class='n'>{pb}</td><td class='n'>{mine}</td><td class='n'>{nn}</td>"
                    f"<td>{pill(cm.get('verdict', 'pending'))}</td><td class='small'>{how}</td><td>{script}</td></tr>")
    out.append(f"""<section class="sec"><div class="wrap wide">
<div class="head-row"><div><p class="eyebrow">Reproduction</p><h2 class="h2">Every reported estimate, rebuilt.</h2></div>
<a class="link-arrow" href="../../methods.html#verdicts">Verdict definitions</a></div>
<div class="table"><table><thead><tr><th>ID</th><th>Estimate</th><th class="n">Paper</th><th class="n">Rebuilt</th>
<th class="n">N paper / rebuilt</th><th>Verdict</th><th>How</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
{deviation_chart(claims)}
<p class="small" style="margin-top:12px">Coefficient with standard error below. Stars: *** p&lt;0.01, ** p&lt;0.05, * p&lt;0.10. “Authors' own code” means the number appeared in the output of the authors' code run unchanged; “AI rebuild” means a model rewrote the analysis in Python.</p>
</div></section>""")

    ac = au.get("authors_code") or {}
    if ac:
        ran = "".join(f"<tr><td class='mono'>{E(r['script'])}</td><td class='n'>{E(str(r['exit']))}</td><td class='n'>{E(str(r['seconds']))} s</td>"
                      f"<td><a href=\"{REPO}/blob/main/audits/{a['slug']}/authors_run/{E(r['stdout'])}\">output</a> · "
                      f"<a href=\"{REPO}/blob/main/audits/{a['slug']}/authors_run/{E(r['stderr'])}\">messages</a></td></tr>" for r in ac.get("ran", []))
        status_txt = {"ran": "ran without errors", "ran with errors": "ran, with errors in some scripts",
                      "needs translation": "is Stata, which this server cannot run; the analysis was translated to Python by the AI stage",
                      "no code": "was not found in the package", "unsupported language": "is in a language not supported yet"}.get(ac.get("status"), ac.get("status", ""))
        out.append(f"""<section class="sec"><div class="wrap wide">
<p class="eyebrow">Step 1 · Authors' own code</p><h2 class="h2" style="margin-bottom:12px">Run exactly as published.</h2>
<p class="sub" style="max-width:760px;margin:0 0 22px">The authors' {E(ac.get("language") or "")} code {E(status_txt)}. {ac.get("found", 0)} of {len(claims)} reported estimates appeared in its output.
{("Hard-coded working-directory lines were disabled in: " + E(", ".join(ac["changed_files"])) + ".") if ac.get("changed_files") else ""}</p>
{('<div class="table"><table><thead><tr><th>Script</th><th class="n">Exit code</th><th class="n">Time</th><th></th></tr></thead><tbody>' + ran + "</tbody></table></div>") if ran else ""}
</div></section>""")

    # robustness
    for cl in claims:
        R = cl.get("robustness") or {}
        if not R.get("variants"):
            continue
        vr = "".join(
            f"<tr><td><b style='font-weight:600'>{E(str(v.get('name')))}</b><div class='sub'>{E(str(v.get('why') or ''))}</div></td>"
            f"<td class='n'>{_f(v.get('b'))}{stars(v.get('p'))}</td><td class='n'>{_f(v.get('se'))}</td>"
            f"<td class='n'>{E(str(v.get('n', '')))}</td></tr>" if v.get("b") is not None else
            f"<tr><td><b>{E(str(v.get('name')))}</b></td><td colspan=3 class='sub'>failed to run</td></tr>"
            for v in R["variants"])
        out.append(f"""<section class="sec alt"><div class="wrap wide">
<p class="eyebrow">Robustness</p><h2 class="h2" style="margin-bottom:10px">Does the headline survive?</h2>
<p class="sub" style="margin:0 0 28px;max-width:760px">{E(cl['id'])}: {E(cl['description'])}</p>
{spec_chart(cl.get("robust_base") or cl.get("rebuilt"), R["variants"])}
<div class="table"><table><thead><tr><th>Alternative specification</th><th class="n">b</th><th class="n">se</th><th class="n">N</th></tr></thead><tbody>{vr}</tbody></table></div>
</div></section>""")

    # provenance
    prov = [("Paper", f'<a href="https://doi.org/{E(doi)}">doi:{E(doi)}</a>'),
            ("Replication package", ("Uploaded file, kept private: " + E(pkg.get("file") or "")) if str(pkg.get("source", "")).startswith("upload://")
             else f'<a href="{E(pkg.get("resolved_url") or pkg.get("source") or "")}">{E(pkg.get("source") or "—")}</a>'),
            ("Version", f'<span class="mono">{E(str(pkg.get("version") or pkg.get("commit") or "—"))}</span>'),
            ("Files fingerprinted", f'{len(pkg.get("manifest", []))} files · SHA-256 of manifest <span class="mono">{E(pkg.get("package_sha256", "")[:20])}…</span>'),
            ("Supplementary files", E(", ".join((x.get("file") or x.get("source", "")) for x in sub.get("supplement") or [] if isinstance(x, dict)) or "—")
             if isinstance(sub.get("supplement"), list) else "—"),
            ("Archives unpacked", E(", ".join(pkg.get("unpacked") or []) or "—")),
            ("Estimates listed by", {"pdf_tables": "the PDF table reader (no AI)", "model": "the model, from the paper"}.get(
                (claims[0].get("source") if claims else None), "the submitter")),
            ("AI model", E(au.get("model") or ("none: authors' code and PDF tables only" if au.get("backend") in (None, "none") else au.get("backend")))),
            ("Software", E(f"ReplicAudit {env.get('replicaudit', '')} · Python {env.get('python', '')} · pandas {env.get('pandas', '')} · pyfixest {env.get('pyfixest', '')}")),
            ("Run", E(f"{au.get('started', '')} · {au.get('llm_calls', '—')} model calls")),
            ("Request", (f'<a href="{E(sub.get("issue_url") or "")}">#{sub["issue"]}</a> · ' if sub.get("issue") else "") + E(sub.get("relationship") or "")),
            ("Everything else", f'<a href="{REPO}/tree/main/audits/{a["slug"]}">Scripts, prompts and answers, data files</a>')]
    from .suggest import auto_suggestions, reviewer_suggestions
    auto = auto_suggestions(au, sub)
    mine = reviewer_suggestions(rbody)
    area_name = {"Estimates": "Reported estimates", "Robustness": "Robustness", "Package": "Replication package", "Readers": "For readers"}
    cards = []
    for area in ("Estimates", "Robustness", "Package", "Readers"):
        items = [x for x in auto if x["area"] == area]
        if items:
            cards.append(f'<div class="card"><p class="eyebrow muted" style="font-size:14px">{area_name[area]}</p><ul class="sugg">'
                         + "".join(f'<li>{E(x["text"])}<div class="small">{E(x["why"])}</div></li>' for x in items) + "</ul></div>")
    if mine:
        cards.append('<div class="card"><p class="eyebrow muted" style="font-size:14px">From the reviewer</p><ul class="sugg">'
                     + "".join(f"<li>{E(x)}</li>" for x in mine) + "</ul></div>")
    if cards:
        out.append(f"""<section class="sec alt"><div class="wrap wide">
<p class="eyebrow">Suggestions</p><h2 class="h2" style="margin-bottom:10px">What would make this result stronger.</h2>
<p class="sub" style="margin:0 0 28px;max-width:760px">Each suggestion states the finding it rests on. Automatic suggestions come from fixed rules; the reviewer's are listed separately.</p>
<div class="grid g2" style="align-items:start">{"".join(cards)}</div></div></section>""")
    pdf_btn = (f'<a class="btn" href="report.pdf">Download the report (PDF)</a>' if a.get("has_pdf") else
               '<p class="sub" style="margin:0">The PDF report is produced when the audit is published.</p>')
    out.append(f"""<section class="sec"><div class="wrap wide"><div class="grid g2" style="align-items:start">
<div><p class="eyebrow">Provenance</p><h2 class="h2" style="margin-bottom:24px">Exactly what was audited.</h2>
<dl class="kv">{"".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in prov)}</dl></div>
<div><p class="eyebrow">Report</p><h2 class="h2" style="margin-bottom:24px">The full report.</h2>
<div class="card">{pdf_btn}<p class="small" style="margin-top:14px">Downloads: <a href="results.csv">results.csv</a> · <a href="audit.json">audit.json</a> · <a href="report.html">machine report</a></p></div>
<p class="eyebrow" style="margin-top:44px">Cite</p><h2 class="h2" style="margin-bottom:24px">Cite this audit.</h2>
<div class="card" style="padding:20px"><button class="btn small secondary copy" data-copy="bib" type="button">Copy</button><pre id="bib">{E(bibtex(a))}</pre></div>
</div></div></div></section>""")
    return page(sub.get("title") or a["slug"], "\n".join(out), 2, desc=f"Replication audit of {sub.get('title')}")


def article_page(eyebrow, title, lead, toc, html_body, active):
    t = "".join(f'<a href="#{i}">{E(n)}</a>' for i, n in toc)
    body = (f'<section class="sec center" style="padding-bottom:40px"><div class="wrap"><p class="eyebrow">{E(eyebrow)}</p>'
            f'<h1 class="h1">{title}</h1><p class="lead">{lead}</p><div class="toc">{t}</div></div></section>'
            f'<section class="sec" style="padding-top:20px"><div class="wrap"><div class="article">{html_body}</div></div></section>')
    return page(re.sub("<.*?>", " ", title), body, 0, active)


METHODS_TOC = [("scope", "Scope"), ("provenance", "Provenance"), ("claims", "Claims"), ("rebuild", "Rebuilding"),
               ("verdicts", "Verdicts"), ("robustness", "Robustness"), ("review", "Publication"), ("suggestions", "Suggestions"),
               ("limits", "Limitations")]
METHODS = """
<h2 id="scope"><span class="num-h">1</span>Scope</h2>
<p>We audit quantitative empirical papers in any field whose data and code, the <i>replication package</i>, are available, either publicly or sent to us by the requester. Code in R and Python is run as published; Stata code is translated to Python; other languages are rebuilt from the paper and code by the AI stage. We do not collect new data, so an audit tests <b>computational reproducibility</b> (same data, same method, same numbers) and <b>robustness</b> (same data, reasonable alternative choices). It does not test replicability in new samples.</p>
<h2 id="provenance"><span class="num-h">2</span>Inputs and provenance</h2>
<p>For each paper we record the DOI, the exact source and version of the replication package, and a SHA-256 checksum of every file. Archives inside the package are unpacked and listed. Packages and papers are downloaded for the run and are never redistributed. The checksums let anyone confirm that they are auditing the same files.</p>
<h2 id="claims"><span class="num-h">3</span>Claims</h2>
<p>A <i>claim</i> is one reported estimate: a coefficient with its standard error and sample size, in a named table and column. Claims are listed by the submitter or extracted from the paper and supplementary materials by the model. The reviewer checks the list against the paper before publication. The paper's headline result is marked as the main claim.</p>
<h2 id="rebuild"><span class="num-h">4</span>Rebuilding the analysis</h2>
<p><b>Step 1: the authors' own code.</b> R and Python packages are run exactly as published, on a fresh server. The only change made is to disable hard-coded working-directory lines such as <code>setwd("C:/Users/…")</code>, and every such change is listed on the audit page. The packages the scripts load are installed automatically. Each reported estimate is then searched for in everything the code printed or wrote: the coefficient, followed closely by its standard error, both rounded to the decimals the paper prints. Matches are shown with the file and line they came from. This step uses no AI.</p>
<p><b>Step 2: the AI stage.</b> This server has no Stata licence, so Stata packages are translated: a language model writes Python that follows the authors' code, first to build the analysis dataset and then to re-estimate each claim. Errors and mismatches are returned to the model, up to four attempts per claim. The same stage re-estimates anything step 1 did not find, and writes the robustness variants. By default the model is a free open-source model running on the audit server itself. If the maintainer adds a Claude key, Claude is used instead. The model is named on every audit page.</p>
<p>Scripts are run without credentials and with time limits. Scripts that contain the paper's reported value as a literal are rejected automatically, so every number must be computed from the data.</p>
<h2 id="verdicts"><span class="num-h">5</span>Verdicts</h2>
<ul>
<li><b>Reproduced.</b> The coefficient and standard error equal the paper's after rounding to the decimals the paper prints, and the sample size matches where it is reported.</li>
<li><b>Close.</b> Same sign and within 5% of the reported coefficient, or an exact coefficient with a different sample size.</li>
<li><b>Size differs.</b> The direction holds but the magnitude does not.</li>
<li><b>Sign differs.</b> The sign is reversed.</li>
<li><b>Not rebuilt.</b> No working script within the attempt limit. This describes our pipeline, not the paper.</li>
<li><b>Not found.</b> The number did not appear in the output of the authors' code, and no AI rebuild was attempted or succeeded. It may be printed in a format we did not recognise, so this is not evidence of an error.</li>
</ul>
<h2 id="robustness"><span class="num-h">6</span>Robustness</h2>
<p>For the main claim, the model proposes up to eight alternative specifications a careful referee could reasonably ask for. These cover alternative controls, samples, fixed effects, clustering, outcome measures and outlier treatment, and checks of the measurement or observation process. Each variant is estimated and shown with its 95% interval.</p>
<p>A headline result is called <b>fragile</b> when fewer than 75% of variants keep its original sign and significance at the 5% level. These variants are a structured sensitivity analysis, not a pre-registered test. The reviewer removes any variant that is not a defensible alternative before publication.</p>
<h2 id="review"><span class="num-h">7</span>Review and publication</h2>
<p>Results are shown to the requester as soon as the audit finishes, clearly marked as unreviewed. An audit joins the registry only after a named reviewer has checked the estimates, read the code behind every estimate that was not reproduced, removed any robustness variant that is not a defensible alternative, and written an assessment with suggestions. Publication produces the audit page with its tables and charts, and a typeset PDF report.</p>
<p>Scripts, the full model prompts and answers, verdicts and provenance are published for every audit. A run can be replayed exactly or repeated independently.</p>
<h2 id="suggestions"><span class="num-h">·</span>Suggestions</h2>
<p>Each report ends with suggestions. Some are generated by fixed rules from what the audit found, for example estimates that could not be traced to any output, scripts that failed on a clean machine, hard-coded paths, missing package versions, or robustness checks under which the headline result changes. Each states the finding it rests on. The reviewer adds their own suggestions, and these are listed separately.</p>
<h2 id="limits"><span class="num-h">8</span>Limitations</h2>
<ul>
<li>Translating code between languages, for example Stata to Python, can cause small numerical differences such as different small-sample corrections or percentile rules. A “Close” verdict often reflects this.</li>
<li>A model can misread a specification. That is why every verdict links to its code and every estimate that did not reproduce is read by a person.</li>
<li>Robustness checks are chosen after seeing the data and cannot cover every defensible analysis. A fragile result is a reason for scrutiny, not proof of error.</li>
<li>Packages with restricted data, or that need a login, cannot be audited automatically.</li>
</ul>
<h2 id="related"><span class="num-h">·</span>Related work</h2>
<p>ReplicAudit builds on reproducibility benchmarks for AI agents (CORE-Bench, REPRO-Bench, ReplicatorBench, PaperBench, ReplicationBench) and on human efforts such as the Institute for Replication. It differs in auditing published literature rather than benchmarks, in being open to any field, and in reporting robustness alongside reproduction.</p>"""

POLICY_TOC = [("purpose", "Purpose"), ("language", "Language"), ("corrections", "Corrections"),
              ("ai", "Use of AI"), ("data", "Data"), ("contact", "Contact")]
POLICY = """
<h2 id="purpose">Purpose</h2>
<p>Audits exist to make published results easier to trust and to build on. They are not judgements of authors. Findings are reported in neutral terms, together with the exact code that produced them, and suggestions are written to be constructive and specific.</p>
<h2 id="language">Language</h2>
<p>We describe what our code found under a stated protocol, for example “not reproduced under protocol v1”. We never use words such as “wrong”, “error” or “misconduct”. When we cannot rebuild an estimate, we say so and attribute it to our pipeline unless the reviewer finds a specific cause.</p>
<h2 id="corrections">Corrections</h2>
<p>Anyone, including a paper's authors, can point out a mistake in an audit through the contact details below. Corrections are made in a new commit, the audit page says what changed, and earlier versions stay in the public history.</p>
<h2 id="ai">Use of AI</h2>
<p>Where the authors' own code can be run, no AI is involved in reproducing their numbers. Where it cannot (for example Stata), or for robustness checks, the analysis code is written by a language model named on the audit page, and all its prompts and answers are published. Results are shown to the requester straight away, marked as unreviewed. A person reviews every audit before it joins the registry and is accountable for it.</p>
<h2 id="data">Data, licences and conflicts of interest</h2>
<p>We never redistribute authors' data or papers. Files sent through the website are kept in a private store and used only for the audit. We publish checksums, our own code and our results. Code is released under the MIT licence and audit reports under CC BY 4.0. Reviewers declare any relationship with the authors, and requests from authors of competing work are labelled as such.</p>
<h2 id="contact">Contact</h2>
<p>Maintainer: Sahil, Johns Hopkins University · <a href="mailto:sfnu1@jh.edu">sfnu1@jh.edu</a> · <a href="{repo}/issues">GitHub issues</a></p>"""


def submit_page():
    body = """
<section class="sec center" style="padding:96px 0 36px"><div class="wrap">
<p class="eyebrow">Audit a paper</p>
<h1 class="display" style="font-size:clamp(40px,6vw,64px)">Paste a DOI.<br>We'll find the rest.</h1>
<p class="lead">Any quantitative paper, any field. The paper, its open-access PDF and its replication package are looked up automatically. Add files only if something can't be found.</p>
<div class="note amber" id="down" hidden style="max-width:640px;margin:24px auto 0;text-align:left"><b>Submissions are paused.</b> The submission service isn't reachable right now, so a request can't be sent. Please try again later.</div>
<div class="qbox"><input id="q" class="field-in q" placeholder="10.1126/science.abc1234 or a link to the paper" autocapitalize="off" spellcheck="false" autocomplete="off" autofocus aria-label="DOI or link to the paper">
<button class="btn" id="find" type="button">Find</button></div>
<div class="detect" id="q-msg" style="margin-top:10px"></div>
</div></section>

<section class="sec alt" id="found" hidden style="padding-top:48px"><div class="wrap" style="max-width:820px">
<div class="card" style="padding:32px">
<p class="eyebrow muted" style="font-size:14px;margin-bottom:6px">The paper</p>
<h2 class="h3" id="paper-title" style="font-size:26px;line-height:1.2"></h2>
<p class="sub" id="paper-meta" style="margin:6px 0 0"></p>
<button type="button" class="linkbtn" id="edit">Edit details</button>
<div id="edit-box" hidden class="frow" style="margin-top:14px">
<div class="f full"><label for="title">Title</label><input class="field-in" id="title"></div>
<div class="f"><label for="authors">Authors</label><input class="field-in" id="authors"></div>
<div class="f"><label for="journal">Journal and year</label><input class="field-in" id="journal"></div></div>

<p class="eyebrow muted" style="font-size:14px;margin:30px 0 10px">What we found</p>
<div class="mlist"><div id="m-data"></div><div id="m-paper"></div><div id="m-supp"></div></div>

<div class="f" style="margin-top:18px"><label for="link">Data and code link <span class="opt">— if it wasn't found, or a different one</span></label>
<input class="field-in" id="link" placeholder="https://doi.org/10.5281/zenodo… · Dataverse · OSF · GitHub · Dryad · openICPSR" autocapitalize="off" spellcheck="false"></div>

<div id="drop" class="drop big" style="margin-top:18px">
<div class="drop-t">Drop files or a whole folder here</div>
<div class="drop-s">The paper PDF, the supplement, and the data and code. Loose files and folders are zipped for you. Kept private, up to 100 MB.</div>
<div style="display:flex;gap:10px;justify-content:center;margin-top:12px;flex-wrap:wrap">
<label class="btn small secondary" style="cursor:pointer">Choose files<input type="file" id="pick-files" multiple hidden></label>
<label class="btn small secondary" style="cursor:pointer">Choose a folder<input type="file" id="pick-folder" webkitdirectory directory multiple hidden></label></div></div>
<div id="chips" class="items" style="margin-top:12px"></div>

<details class="more"><summary>Choose which estimates to check <span class="opt">— optional</span></summary>
<p class="small" style="margin:10px 0">Leave this alone and the estimates are read from the paper's tables during the audit. If you add the paper PDF above, its tables are listed here so you can pick the ones that matter.</p>
<div class="small" id="sugg-status"></div><div id="sugg" style="margin-top:8px"></div>
<label class="small" for="paste" style="display:block;margin-top:14px;font-weight:600">Or paste rows from a spreadsheet: ID, description, coefficient, standard error, N, headline (yes/no)</label>
<textarea class="field-in" id="paste" style="min-height:90px;font-family:var(--mono);font-size:13px;margin-top:6px" placeholder="T1c3, Table 1 col 3: outcome on treatment, -.042, .011, 1200, yes"></textarea>
</details>
<details class="more"><summary>Notes for the auditor <span class="opt">— optional</span></summary>
<textarea class="field-in" id="notes" style="margin-top:10px;min-height:80px" placeholder="For example: which script makes which table, or data that are restricted."></textarea>
</details>
<input type="text" id="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px">

<label class="check" style="margin-top:18px"><input type="checkbox" id="mine"><span>I'm one of the paper's authors</span></label>
<ul id="why" class="small" style="color:var(--red);margin:10px 0 0;padding-left:20px"></ul>
<div class="btns" style="margin-top:18px"><button class="btn" type="button" id="go" style="font-size:19px;padding:14px 30px">Start the audit</button></div>
<div id="send-box" hidden style="margin-top:18px"><div style="height:6px;background:var(--gray-soft);border-radius:99px;overflow:hidden"><div id="send-bar" style="height:100%;width:0;background:var(--blue);transition:width .3s"></div></div>
<div class="small" id="send-label" style="margin-top:8px"></div></div>
<p class="small" id="send-error" style="color:var(--red)"></p>
<p class="tiny" style="margin-top:14px">No account needed. Files are kept private and used only for this audit; results are shown publicly on this website. You'll get a page to follow the audit, which takes about 20 to 90 minutes.</p>
</div></div></section>

<section class="sec"><div class="wrap wide">
<div class="grid g3">
<div class="card">{i1}<h3>Found for you.</h3><p>The paper's details come from Crossref, an open-access PDF from Unpaywall, and the replication package from the data repositories that link to the paper.</p></div>
<div class="card">{i2}<h3>Run as published.</h3><p>R and Python code runs exactly as the authors shipped it. Stata code is translated. Every reported number is then looked for in the output.</p></div>
<div class="card">{i3}<h3>Reviewed, then published.</h3><p>Results appear on your page straight away. After review they're published with tables, charts, suggestions and a PDF report.</p></div>
</div></div></section>""".format(i1=icon("fetch"), i2=icon("check"), i3=icon("review"))
    return page("Audit a paper", body, 0, "submit.html",
                extra_js=('<script src="vendor/pdfjs/pdf.min.js" defer></script><script src="vendor/jszip/jszip.min.js" defer></script>'
                          '<script src="estimates.js" defer></script><script src="submit.js" defer></script>'),
                body_attrs=f' data-api="{API}"')


def status_page():
    body = """
<section class="sec center" style="padding-bottom:40px"><div class="wrap">
<p class="eyebrow">Track a request</p><h1 class="h1" id="t-title">Your audit</h1><p class="lead" id="t-meta" style="font-size:17px"></p>
<p class="small" id="t-err" style="color:var(--red)"></p></div></section>
<section class="sec alt" style="padding-top:48px"><div class="wrap">
<div id="ask" hidden class="card" style="max-width:520px;margin:0 auto"><h3 class="h3" style="margin-bottom:12px">Enter your request number</h3>
<div style="display:flex;gap:10px"><input class="field-in" id="rnum" placeholder="Request number or code"><button class="btn" id="go-track" type="button">Track</button></div></div>
<div id="track" hidden>
<div class="grid g3 steps3">
<div class="card st" id="s1"><div class="st-n">1</div><h3>Received</h3><p class="st-s"></p></div>
<div class="card st" id="s2"><div class="st-n">2</div><h3>Running</h3><p class="st-s"></p></div>
<div class="card st" id="s3"><div class="st-n">3</div><h3>Results</h3><p class="st-s">Will appear here when the audit finishes. You can close this page and come back later.</p></div>
</div>
<div id="results" style="margin-top:28px"></div>
<p class="tiny" style="margin-top:20px">Bookmark this page to come back. It refreshes itself while the audit runs.</p>
</div></div></section>"""
    return page("Track a request", body, 0, "status.html", extra_js='<script src="status.js" defer></script>')


def build_site(audits_dir="audits", out="_site", include_drafts=False, static_dir=None, pdf=True):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    static = Path(static_dir) if static_dir else Path(__file__).resolve().parent.parent / "site_src"
    for f in ("style.css", "site.js", "submit.js", "estimates.js", "status.js"):
        shutil.copy(static / f, out / f)
    shutil.copytree(static / "vendor", out / "vendor")
    audits = load_audits(audits_dir, include_drafts)
    (out / "submit.html").write_text(submit_page(), encoding="utf-8")
    (out / "status.html").write_text(status_page(), encoding="utf-8")
    (out / "methods.html").write_text(article_page(
        f"Protocol v1 · ReplicAudit {__version__}", "Methods",
        "One fixed, published procedure, applied the same way to every paper. Any change to it gets a new version number, and every audit records the version it used.",
        METHODS_TOC, METHODS, "methods.html"), encoding="utf-8")
    (out / "policy.html").write_text(article_page(
        "Policy", "Fair to authors.<br>Open to everyone.",
        "How audits are written, corrected and disclosed.", POLICY_TOC, POLICY.format(repo=REPO), "policy.html"), encoding="utf-8")
    for a in audits:
        d = out / "audits" / a["slug"]
        d.mkdir(parents=True)
        if a["sub"].get("status") == "published" and pdf:
            try:
                from .latex import build_tex, compile_pdf
                import tempfile
                tmpd = Path(tempfile.mkdtemp(prefix="report_"))
                got = compile_pdf(build_tex(a["dir"], tmpd))
                if got:
                    shutil.copy(got, d / "report.pdf")
                    shutil.copy(tmpd / "report.tex", d / "report.tex")
                    a["has_pdf"] = True
                else:
                    print(f"LaTeX failed for {a['slug']}; see {tmpd / 'report.log'}")
            except Exception as e:
                print(f"report for {a['slug']} not built: {e}")
        (d / "index.html").write_text(audit_page(a), encoding="utf-8")
        for f in ("results.csv", "audit.json", "report.html"):
            if (a["dir"] / f).exists():
                shutil.copy(a["dir"] / f, d / f)
    (out / "index.html").write_text(index_page(audits), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return out
