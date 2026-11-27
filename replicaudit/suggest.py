"""Suggestions for the authors and readers, derived from what the audit found.

Rule-based (no AI), so every suggestion can be traced to a specific finding. The reviewer can add their
own under a "## Suggestions" heading in review.md; those are listed after these.
"""
from __future__ import annotations

import re
from pathlib import Path


def _fmt(x):
    return "—" if x is None else f"{x:.4f}"


def auto_suggestions(audit: dict, submission: dict) -> list[dict]:
    out = []
    claims = audit.get("claims", [])
    ac = audit.get("authors_code") or {}
    manifest = [m.get("path", "") for m in (submission.get("package") or {}).get("manifest", [])]
    lower = [p.lower() for p in manifest]

    def add(area, text, why):
        out.append({"area": area, "text": text, "why": why})

    # --- reproducibility of the package itself
    if ac.get("status") == "needs translation":
        add("Package", "Include the Stata log file (.log or .smcl) for every table and figure.",
            "Stata is licensed software, so readers without a licence can only check the numbers against saved logs.")
    if ac.get("status") == "ran with errors":
        bad = [r["script"] for r in ac.get("ran", []) if r.get("exit") != 0]
        add("Package", f"Fix or document the scripts that stopped with an error: {', '.join(bad)}.",
            "These scripts failed when run unchanged on a clean machine; see their messages on the audit page.")
    if ac.get("changed_files"):
        add("Package", "Replace hard-coded working directories (setwd, cd, os.chdir) with paths relative to the project folder.",
            f"Absolute paths had to be disabled in {', '.join(ac['changed_files'])} before the code would run.")
    scripts = ac.get("ran", [])
    if len(scripts) > 1 and not any(re.search(r"master|main|run_?all|make", s["script"], re.I) for s in scripts):
        add("Package", "Add one master script that runs every step in order.",
            "The run order had to be inferred from file names.")
    if manifest and not any(Path(p).name.startswith(("readme", "read_me", "read me")) for p in lower):
        add("Package", "Add a README listing the data sources, software and package versions, and which script produces which table.",
            "No README was found in the replication package.")
    if ac.get("language") == "R" and not any(p.endswith(("renv.lock", "description")) for p in lower):
        add("Package", "Record R package versions (for example with renv), so results don't change as packages update.",
            "No renv.lock or DESCRIPTION file was found.")
    if ac.get("language") == "Python" and not any(Path(p).name.startswith(("requirements", "environment", "pyproject")) for p in lower):
        add("Package", "Add a requirements.txt (or environment.yml) with pinned versions.",
            "Python dependencies had to be guessed from import statements.")

    # --- reported estimates
    nf = [c for c in claims if (c.get("compare") or {}).get("verdict") in ("not_found", "failed")]
    if nf:
        ids = ", ".join(c["id"] for c in nf[:8]) + (" and others" if len(nf) > 8 else "")
        add("Estimates", "Have the code write each published table to a file (for example with esttab, modelsummary or stargazer).",
            f"These estimates could not be found in the code's output: {ids}.")
    for c in claims:
        v = (c.get("compare") or {}).get("verdict")
        rb = c.get("rebuilt") or {}
        if v in ("close", "same_sign"):
            add("Estimates", f"Check estimate {c['id']} ({c['description']}): the paper reports {c['b']}, the audit found {_fmt(rb.get('b'))}.",
                "The difference is larger than rounding; a different sample, version or option may have been used.")
        if v == "different":
            add("Estimates", f"Estimate {c['id']} has the opposite sign in the audit ({_fmt(rb.get('b'))}) to the paper ({c['b']}). This needs checking first.",
                "A sign change is the largest possible discrepancy.")
        if c.get("n") and rb.get("n") and str(c["n"]).replace(",", "") != str(rb["n"]).replace(",", ""):
            add("Estimates", f"Report how the sample for {c['id']} is formed: the paper reports N = {c['n']}, the audit used {rb['n']}.",
                "Sample sizes differ, often because of dropped singletons or missing values.")

    # --- robustness of the headline
    for c in claims:
        R = c.get("robustness") or {}
        s = R.get("summary") or {}
        if not s.get("n"):
            continue
        base = (c.get("robust_base") or c.get("rebuilt") or {}).get("b")
        flips = [v for v in R.get("variants", []) if v.get("b") is not None and base is not None
                 and ((v["b"] > 0) != (base > 0) or (v.get("p") or 1) >= 0.05)]
        if s.get("fragile"):
            names = "; ".join(v["name"] for v in flips[:4])
            add("Robustness", f"Report and discuss the checks under which the headline result ({c['id']}) loses its sign or significance: {names}.",
                f"Only {s['share_same_sign_sig05']:.0%} of {s['n']} alternative specifications keep the original sign and 5% significance.")
        elif flips:
            add("Robustness", f"Mention that the headline result ({c['id']}) is not significant under: {'; '.join(v['name'] for v in flips[:3])}.",
                f"It holds in {s['share_same_sign_sig05']:.0%} of {s['n']} alternative specifications.")
        else:
            add("Readers", f"The headline result ({c['id']}) kept its sign and 5% significance in all {s['n']} alternative specifications tried.",
                "No robustness concern was found by this audit.")

    if claims and all((c.get("compare") or {}).get("verdict") == "exact" for c in claims) and ac.get("status") == "ran":
        add("Readers", "Every checked estimate was reproduced by running the authors' own code unchanged.",
            "This is the strongest level of computational reproducibility this audit can confirm.")
    return out


def reviewer_suggestions(review_md: str) -> list[str]:
    """Bullet points under a '## Suggestions' heading in review.md."""
    m = re.search(r"^#+\s*Suggestions\s*$(.*?)(?=^#+\s|\Z)", review_md or "", re.M | re.S | re.I)
    if not m:
        return []
    return [re.sub(r"^\s*[-*]\s+", "", l).strip() for l in m.group(1).splitlines() if re.match(r"^\s*[-*]\s+", l)]


def strip_suggestions(review_md: str) -> str:
    return re.sub(r"^#+\s*Suggestions\s*$.*?(?=^#+\s|\Z)", "", review_md or "", flags=re.M | re.S | re.I).strip()
