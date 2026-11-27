"""Figures for the PDF report (matplotlib) — the website draws the same charts as SVG (site.py)."""
from __future__ import annotations

from pathlib import Path

JHU = "#002D72"
GREEN, AMBER, RED, GRAY = "#1d8a3a", "#b25000", "#d70015", "#8e8e93"
VCOL = {"exact": GREEN, "close": GREEN, "same_sign": AMBER, "different": RED, "failed": GRAY, "not_found": GRAY}


def deviation_rows(claims):
    """(label, deviation in paper standard errors or None, verdict)."""
    rows = []
    for c in claims:
        rb = c.get("rebuilt") or {}
        v = (c.get("compare") or {}).get("verdict", "not_found")
        try:
            b, se = float(c["b"]), float(c["se"]) if c.get("se") else None
        except (TypeError, ValueError):
            b, se = None, None
        dev = None
        if rb.get("b") is not None and b is not None and se:
            dev = (rb["b"] - b) / se
        rows.append((c["id"], dev, v))
    return rows


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8)


def fig_deviation(claims, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = deviation_rows(claims)
    devs = [abs(d) for _, d, _ in rows if d is not None]
    lim = max(1.0, min(6.0, (max(devs) if devs else 1) * 1.25))
    fig, ax = plt.subplots(figsize=(6.2, 0.32 * len(rows) + 1.1))
    ax.axvspan(-0.5, 0.5, color=GREEN, alpha=0.08, lw=0)
    ax.axvline(0, color="#444", lw=0.6)
    for i, (lab, d, v) in enumerate(rows):
        y = len(rows) - 1 - i
        if d is None:
            ax.text(-lim * 0.97, y, "not found", va="center", fontsize=7.5, color=GRAY, style="italic")
        else:
            ax.plot([max(-lim, min(lim, d))], [y], "o", ms=5.5, color=VCOL.get(v, GRAY))
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=7.5, family="monospace")
    ax.set_xlim(-lim, lim)
    ax.set_xlabel("Reproduced minus reported, in units of the paper's standard error", fontsize=8)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_robustness(base, variants, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [v for v in variants if v.get("b") is not None and v.get("se")]
    rows = [("Original specification", base["b"], base["se"])] + [(v["name"], v["b"], v["se"]) for v in ok]
    fig, ax = plt.subplots(figsize=(6.2, 0.34 * len(rows) + 1.0))
    ax.axvline(0, color="#444", lw=0.6, ls=(0, (3, 3)))
    for i, (name, b, s) in enumerate(rows):
        y = len(rows) - 1 - i
        sig = abs(b / s) > 1.96 and (b > 0) == (base["b"] > 0)
        col = "#1d1d1f" if i == 0 else (JHU if sig else RED)
        ax.plot([b - 1.96 * s, b + 1.96 * s], [y, y], color=col, lw=1.6, solid_capstyle="round")
        ax.plot([b], [y], "o", color=col, ms=5)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0][:46] for r in reversed(rows)], fontsize=7.5)
    ax.set_xlabel("Estimate with 95% confidence interval", fontsize=8)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
