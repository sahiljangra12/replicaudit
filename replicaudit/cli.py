"""Command line:  python -m replicaudit run|batch|report ..."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .backends import make_backend
from .pipeline import Audit
from .report import build_report


def _common(p):
    p.add_argument("--backend", default="auto", choices=["auto", "anthropic", "openai", "replay", "none"],
                   help="auto: Claude if ANTHROPIC_API_KEY is set, else a local Ollama model if running, else no AI")
    p.add_argument("--model", help="model name (anthropic default: claude-sonnet-5-5)")
    p.add_argument("--base-url", help="for --backend openai, e.g. http://localhost:11434/v1 (Ollama)")
    p.add_argument("--fixtures", help="for --backend replay: folder of saved answers (a run's llm_log/)")
    p.add_argument("--max-attempts", type=int, default=4)
    p.add_argument("--robustness", default="main", choices=["main", "all", "none"])
    p.add_argument("--n-robust", type=int, default=8)
    p.add_argument("--timeout", type=int, default=900, help="seconds per script")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="replicaudit", description="Automated replication audits of empirical papers.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="audit one paper")
    r.add_argument("--package", required=True, help="folder with the authors' data and code")
    r.add_argument("--paper", help="paper PDF/TeX/text (used to extract claims if --claims is not given)")
    r.add_argument("--claims", help="CSV/JSON of claims: id,description,b,se,n,main")
    r.add_argument("--out", required=True)
    r.add_argument("--title")
    r.add_argument("--note", help="note printed at the top of the report")
    _common(r)

    b = sub.add_parser("batch", help="audit many papers listed in a CSV (columns: name,package,paper,claims)")
    b.add_argument("list_csv")
    b.add_argument("--out", required=True)
    _common(b)

    rp = sub.add_parser("report", help="rebuild report.html for a run folder")
    rp.add_argument("run_dir")

    it = sub.add_parser("intake", help="run an audit from a submission form (GitHub issue body)")
    it.add_argument("--issue-body", help="file holding the issue body (markdown)")
    it.add_argument("--issue", type=int)
    it.add_argument("--issue-url")
    it.add_argument("--audits", default="audits")
    it.add_argument("--materials", help="two-step mode: folder for downloaded materials")
    it.add_argument("--step", choices=["all", "fetch", "audit"], default="all",
                    help="fetch: download only (may use private-upload credentials); audit: run on downloaded materials")
    _common(it)

    st = sub.add_parser("site", help="build the static website from audits/")
    st.add_argument("--audits", default="audits")
    st.add_argument("--out", default="_site")
    st.add_argument("--include-drafts", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(build_report(a.run_dir))
        return
    if a.cmd == "site":
        from .site import build_site
        print(build_site(a.audits, a.out, a.include_drafts))
        return

    opts = dict(max_attempts=a.max_attempts, robustness=a.robustness, n_robust=a.n_robust, timeout=a.timeout)

    if a.cmd == "intake" and a.step == "fetch":
        from .intake import fetch_materials
        adir = fetch_materials(Path(a.issue_body).read_text(encoding="utf-8"), Path(a.audits), Path(a.materials),
                               a.issue, a.issue_url)
        print(f"AUDIT_DIR={adir}")
        return

    backend = make_backend(a.backend, a.model, a.fixtures, a.base_url)
    print(f"model backend: {backend.name if backend else 'none (authors code and PDF tables only)'}")

    if a.cmd == "intake":
        from .intake import audit_materials, run_intake
        if a.step == "audit":
            adir = audit_materials(Path(a.materials), backend, **opts)
        else:
            adir = run_intake(Path(a.issue_body).read_text(encoding="utf-8"), Path(a.audits), backend,
                              a.issue, a.issue_url, **opts)
        print(f"AUDIT_DIR={adir}")
        return

    if a.cmd == "run":
        pdfs = [a.paper] if a.paper and a.paper.lower().endswith(".pdf") else []
        audit = Audit(backend, a.package, a.out, paper=a.paper, claims=a.claims, pdfs=pdfs, **opts)
        audit.state["title"] = a.title
        audit.state["note"] = a.note
        audit.run()
        print("report:", build_report(a.out))
        return

    # batch
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    with open(a.list_csv, newline="", encoding="utf-8") as fh:
        papers = list(csv.DictReader(fh))
    for row in papers:
        name = row["name"]
        run_dir = out / name
        if a.backend == "replay":
            backend = make_backend("replay", fixtures=str(Path(a.fixtures) / name))
        try:
            audit = Audit(backend, row["package"], run_dir, paper=row.get("paper") or None,
                          claims=row.get("claims") or None, **opts)
            audit.state["title"] = name
            st = audit.run()
            build_report(run_dir)
            verdicts = [(c.get("compare") or {}).get("verdict", "failed") for c in st["claims"]]
            fragile = [c["id"] for c in st["claims"]
                       if ((c.get("robustness") or {}).get("summary") or {}).get("fragile")]
            summary.append({"paper": name, "claims": len(verdicts),
                            **{v: verdicts.count(v) for v in ("exact", "close", "same_sign", "different", "failed")},
                            "fragile_claims": " ".join(fragile)})
        except Exception as e:  # one broken paper must not stop the batch
            summary.append({"paper": name, "claims": 0, "failed": 0, "error": str(e)[:300]})
        with open(out / "batch_summary.json", "w") as fh:
            json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
