"""Turn audit.json into a self-contained HTML report."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .compare import VERDICTS, stars

COLORS = {"exact": "#1a7f37", "close": "#4d8f2f", "same_sign": "#b26b00",
          "different": "#c62828", "failed": "#6b7280", "pending": "#6b7280"}

CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#1f2328;max-width:1060px;margin:32px auto;padding:0 20px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:36px 0 10px;border-bottom:1px solid #d8dee4;padding-bottom:6px}
h3{font-size:16px;margin:24px 0 6px}.muted{color:#59636e}.tiles{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}
.tile{border:1px solid #d8dee4;border-radius:10px;padding:12px 16px;min-width:120px}.tile b{display:block;font-size:24px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:6px 8px;border-bottom:1px solid #eaeef2;text-align:left;vertical-align:top}
th{background:#f6f8fa}td.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.badge{display:inline-block;border-radius:999px;padding:1px 9px;color:#fff;font-size:12px;white-space:nowrap}
details{margin:6px 0}pre{background:#f6f8fa;padding:10px;border-radius:8px;overflow:auto;font-size:12px;max-height:420px}
.warn{background:#fff8e6;border:1px solid #f0d58c;border-radius:8px;padding:10px 14px}
"""


def _f(x, d=4):
    return "" if x is None else f"{x:.{d}f}"


def _badge(v):
    return f'<span class="badge" style="background:{COLORS.get(v, "#6b7280")}">{html.escape(VERDICTS.get(v, v))}</span>'


def _spec_chart(base, variants):
    ok = [v for v in variants if v.get("b") is not None and v.get("se")]
    if not ok:
        return ""
    rows = [("Rebuilt original", base["b"], base["se"])] + [(v["name"], v["b"], v["se"]) for v in ok]
    lo = min(min(b - 1.96 * s for _, b, s in rows), 0)
    hi = max(max(b + 1.96 * s for _, b, s in rows), 0)
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad
    W, L, R, rh = 860, 300, 30, 24
    H = rh * len(rows) + 40
    x = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="estimates with 95% intervals">',
             f'<line x1="{x(0):.1f}" y1="8" x2="{x(0):.1f}" y2="{H-28}" stroke="#8c959f" stroke-dasharray="4 3"/>']
    for i, (name, b, s) in enumerate(rows):
        y = 20 + i * rh
        sig = abs(b / s) > 1.96
        col = "#1f2328" if i == 0 else ("#0969da" if sig else "#c62828")
        parts.append(f'<text x="{L-10}" y="{y+4}" text-anchor="end" font-size="12" fill="#1f2328">{html.escape(str(name))[:44]}</text>')
        parts.append(f'<line x1="{x(b-1.96*s):.1f}" y1="{y}" x2="{x(b+1.96*s):.1f}" y2="{y}" stroke="{col}" stroke-width="2"/>')
        parts.append(f'<circle cx="{x(b):.1f}" cy="{y}" r="4.5" fill="{col}"/>')
    for t in (lo, 0, hi):
        parts.append(f'<text x="{x(t):.1f}" y="{H-10}" text-anchor="middle" font-size="11" fill="#59636e">{t:.4f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def build_report(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    st = json.loads((run_dir / "audit.json").read_text())
    claims = st["claims"]
    counts = {}
    for c in claims:
        v = (c.get("compare") or {}).get("verdict", "pending")
        counts[v] = counts.get(v, 0) + 1
    title = st.get("title") or Path(st["package"]).name
    h = [f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>Replication audit — {html.escape(title)}</title>",
         f"<meta name='viewport' content='width=device-width,initial-scale=1'><style>{CSS}</style></head><body>",
         f"<h1>Replication audit</h1><div class='muted'>{html.escape(title)} · model backend: {html.escape(st['backend'])}"
         f" · run {html.escape(st.get('started', ''))}</div>"]
    if st.get("note"):
        h.append(f"<p class='warn'>{html.escape(st['note'])}</p>")
    h.append("<div class='tiles'>")
    h.append(f"<div class='tile'><b>{len(claims)}</b>claims checked</div>")
    for v in ("exact", "close", "same_sign", "different", "failed"):
        if counts.get(v):
            h.append(f"<div class='tile'><b style='color:{COLORS[v]}'>{counts[v]}</b>{VERDICTS[v]}</div>")
    h.append("</div>")

    prep = st.get("prep") or {}
    h.append(f"<p><b>Data preparation:</b> {'built' if prep.get('ok') else 'failed'} "
             f"after {len(prep.get('attempts', []))} attempt(s)"
             + (f" — {prep['result'].get('rows')} rows" if prep.get("result") else "") + ".</p>")

    h.append("<h2>Claims</h2><table><tr><th>ID</th><th>Claim</th><th>Paper b (se)</th><th>Rebuilt b (se)</th><th>N</th><th>Verdict</th><th>Tries</th></tr>")
    for c in claims:
        rb = c.get("rebuilt") or {}
        cmp_ = c.get("compare") or {}
        pb = f"{c['b']}{cmp_.get('target_stars', '')}" + (f" ({c['se']})" if c.get("se") else "")
        mine = (f"{_f(rb.get('b'))}{stars(cmp_.get('p'))} ({_f(rb.get('se'))})" if rb else "—")
        h.append(f"<tr><td>{html.escape(c['id'])}</td><td>{html.escape(c['description'])}</td>"
                 f"<td class='num'>{pb}</td><td class='num'>{mine}</td><td class='num'>{rb.get('n', '') if rb else ''}</td>"
                 f"<td>{_badge(cmp_.get('verdict', 'pending'))}</td><td class='num'>{len(c.get('attempts', []))}</td></tr>")
    h.append("</table>")

    rob = [c for c in claims if (c.get("robustness") or {}).get("variants")]
    if rob:
        h.append("<h2>Robustness checks</h2><p class='muted'>Blue: same sign and significant at 5%. Red: not. Lines are 95% intervals.</p>")
    for c in rob:
        R = c["robustness"]
        s = R["summary"]
        h.append(f"<h3>{html.escape(c['id'])}: {html.escape(c['description'])}</h3>")
        if s.get("n"):
            h.append(f"<p>{s['n']} variants ran ({s.get('n_failed', 0)} failed). "
                     f"Same sign in <b>{s['share_same_sign']:.0%}</b>; same sign and significant at 5% in "
                     f"<b>{s['share_same_sign_sig05']:.0%}</b>. Estimates range {s['min_b']:.4f} to {s['max_b']:.4f}."
                     + (" <b style='color:#c62828'>Fragile result.</b>" if s.get("fragile") else "") + "</p>")
        h.append(_spec_chart(c["rebuilt"], R["variants"]))
        h.append("<table><tr><th>Variant</th><th>Why</th><th>b</th><th>se</th><th>N</th></tr>")
        for v in R["variants"]:
            h.append(f"<tr><td>{html.escape(str(v.get('name')))}</td><td>{html.escape(str(v.get('why') or ''))}</td>"
                     f"<td class='num'>{_f(v.get('b'))}{stars(v.get('p'))}</td><td class='num'>{_f(v.get('se'))}</td>"
                     f"<td class='num'>{v.get('n', '') if 'b' in v else html.escape(str(v.get('error', ''))[:120])}</td></tr>")
        h.append("</table>")

    h.append("<h2>Scripts</h2><p class='muted'>Every number above comes from these scripts, saved in <code>scripts/</code>. Model prompts and answers are in <code>llm_log/</code>, so the run can be replayed exactly.</p>")
    for c in claims:
        if c.get("code"):
            h.append(f"<details><summary>{html.escape(c['id'])} — {html.escape(c['script'])}</summary><pre>{html.escape(c['code'])}</pre></details>")
    h.append("</body></html>")
    out = run_dir / "report.html"
    out.write_text("\n".join(h), encoding="utf-8")
    return out
