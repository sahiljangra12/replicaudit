"""The audit pipeline: inspect -> claims -> prepare -> rebuild -> compare -> robustness -> report."""
from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

from . import prompts
from .backends import Backend, LoggingBackend, MissingFixture
from .compare import pvalue, robustness_summary, target_literals, verdict
from .inspect_pkg import describe_frame, profile_package, profile_to_markdown
from .sandbox import extract_code, run_script

JSON_RE = re.compile(r"```json\s*\n(.*?)```", re.S)


def _log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def read_paper(path: str | Path | None) -> str:
    if not path:
        return ""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def load_claims(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text())
    else:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    for r in rows:
        r["main"] = str(r.get("main", "")).strip().lower() in {"1", "true", "yes"}
        for k in ("se", "n"):
            if r.get(k) in ("", "null", "None"):
                r[k] = None
    return rows


def _parse_json_block(answer: str):
    m = JSON_RE.findall(answer)
    return json.loads(m[-1] if m else answer)


class Audit:
    def __init__(self, backend: Backend | None, package_dir, out_dir, paper=None, claims=None,
                 max_attempts=4, robustness="main", n_robust=8, timeout=900, pdfs=None, run_code=True):
        self.out = Path(out_dir).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.work = self.out / "work"
        self.work.mkdir(exist_ok=True)
        self.scripts = self.out / "scripts"
        self.scripts.mkdir(exist_ok=True)
        self.backend = LoggingBackend(backend, self.out / "llm_log") if backend else None
        self.pdfs = [Path(p) for p in (pdfs or [])]
        self.run_code = run_code
        self.package_dir = Path(package_dir).resolve()
        self.paper, self.claims_path = paper, claims
        self.max_attempts, self.robustness, self.n_robust = max_attempts, robustness, n_robust
        self.timeout = timeout
        self.env = {"PACKAGE_DIR": self.package_dir, "WORK_DIR": self.work}
        self.state = {"package": str(self.package_dir), "paper": str(paper) if paper else None,
                      "backend": backend.name if backend else "none", "model": getattr(backend, "model", None),
                      "started": time.strftime("%Y-%m-%d %H:%M"), "environment": _environment(),
                      "settings": {"max_attempts": max_attempts, "robustness": robustness,
                                   "n_robust": n_robust, "timeout_s": timeout},
                      "claims": [], "prep": None}

    # ---------------------------------------------------------------- helpers
    def _ask_and_run(self, key_prefix, build_prompt, target_b=None, check=None):
        """Ask for a script, run it, feed errors back; returns (RunResult|None, attempts list)."""
        attempts, feedback = [], ""
        for i in range(1, self.max_attempts + 1):
            key = f"{key_prefix}/attempt{i}"
            try:
                answer = self.backend.complete(key, prompts.SYSTEM, build_prompt(feedback))
            except MissingFixture:
                attempts.append({"attempt": i, "error": "no saved answer for " + key})
                break
            code = extract_code(answer)
            if not code:
                problem = "Your reply had no ```python code block."
                attempts.append({"attempt": i, "error": problem})
                feedback = prompts.FEEDBACK.format(attempt=i, problem=problem, script="(none)")
                continue
            script = self.scripts / (key.replace("/", "__") + ".py")
            script.write_text(code, encoding="utf-8")
            if target_b is not None and any(lit in code for lit in target_literals(target_b)):
                problem = ("The script contains the paper's reported value as a literal. "
                           "Compute it from the data instead.")
                attempts.append({"attempt": i, "script": script.name, "error": problem})
                feedback = prompts.FEEDBACK.format(attempt=i, problem=problem, script=code)
                continue
            r = run_script(script, self.work, self.env, self.timeout)
            att = {"attempt": i, "script": script.name, "seconds": round(r.seconds, 1)}
            if not r.ok:
                att["error"] = r.error[-3000:]
                attempts.append(att)
                feedback = prompts.FEEDBACK.format(attempt=i, problem=r.error[-3000:], script=code)
                continue
            att["result"] = r.result
            problem = check(r.result) if check else None
            attempts.append(att)
            if problem and i < self.max_attempts:
                att["note"] = problem
                feedback = prompts.FEEDBACK.format(attempt=i, problem=problem, script=code)
                continue
            return r, attempts, code
        return None, attempts, None

    # ----------------------------------------------------------------- stages
    def run(self):
        _log(f"inspecting package {self.package_dir}")
        profile = profile_package(self.package_dir)
        self.profile_md = profile_to_markdown(profile)
        (self.out / "package_profile.md").write_text(self.profile_md, encoding="utf-8")
        self.code_text = profile["code_text"]

        self.claims = self.get_claims()
        self.state["claims"] = self.claims
        _log(f"{len(self.claims)} claims to check")
        if not self.claims:
            self.state["finished"] = time.strftime("%Y-%m-%d %H:%M")
            self.state["problem"] = "No estimates to check: none were listed and none could be found in the PDF."
            self.save()
            return self.state

        # Stage A — run the authors' own code (no AI) and look for every reported number in its output
        if self.run_code:
            self.run_authors_code()
        for c in self.claims:
            ac = c.get("authors_code") or {}
            if ac.get("found"):
                h = ac["hits"][0]
                c["rebuilt"] = {"b": _num(h["coef_text"].replace("\u2212", "-")), "se": _num(h["se_text"]), "n": None}
                c["compare"] = {**verdict(c["b"], c.get("se"), c["rebuilt"]["b"], c["rebuilt"]["se"]),
                                "verdict": "exact", "method": "authors_code"}
        self.save()

        # Stage B — AI rebuild (Stata translation, anything not found) and robustness, if a model is available
        if self.backend:
            todo = [c for c in self.claims if not (c.get("authors_code") or {}).get("found")]
            todo += [c for c in self.claims if c.get("main") and c not in todo and self.robustness != "none"]
            if todo and self.prepare():
                for c in todo:
                    keep = c.get("compare") if (c.get("authors_code") or {}).get("found") else None
                    keep_rb = c.get("rebuilt") if keep else None
                    self.rebuild(c)
                    if keep:  # the authors' own code already reproduced it; the AI script is kept for robustness
                        c["ai_compare"], c["compare"] = c.get("compare"), keep
                        c["ai_rebuilt"], c["rebuilt"] = c.get("rebuilt"), keep_rb
                        if c.get("ai_rebuilt"):
                            c["robust_base"] = c["ai_rebuilt"]
                    self.save()
                for c in self.claims:
                    if c.get("code") and (self.robustness == "all" or (self.robustness == "main" and c["main"])):
                        self.robust(c)
                        self.save()
        for c in self.claims:
            if not c.get("compare") or c["compare"].get("verdict") == "failed" and not self.backend:
                c["compare"] = {"verdict": "not_found"}
            c["compare"].setdefault("method", "ai_rebuild" if c.get("code") else None)
        self.state["finished"] = time.strftime("%Y-%m-%d %H:%M")
        self.state["llm_calls"] = self.backend.calls if self.backend else 0
        self.save()
        return self.state

    def run_authors_code(self):
        import shutil
        import tempfile

        from .match import match_claims
        from .runcode import run_package

        tmp = Path(tempfile.mkdtemp(prefix="authors_"))
        try:
            shutil.copytree(self.package_dir, tmp / "pkg")
            run_dir = self.out / "authors_run"
            res = run_package(tmp / "pkg", run_dir, timeout=int(os.environ.get("AUTHORS_CODE_TIMEOUT", 4 * 3600)))
            match_claims(self.claims, run_dir)
            # keep logs and small outputs only (derived data files are not committed)
            pruned = []
            for f in (run_dir / "files").rglob("*") if (run_dir / "files").exists() else []:
                if f.is_file() and (f.stat().st_size > 300_000 or (f.suffix.lower() in (".csv", ".tsv") and f.stat().st_size > 50_000)):
                    pruned.append(str(f.relative_to(run_dir)))
                    f.unlink()
            res["pruned_large_outputs"] = pruned
            res["found"] = sum(1 for c in self.claims if (c.get("authors_code") or {}).get("found"))
            self.state["authors_code"] = res
            _log(f"authors' code: {res.get('status')}; {res['found']} of {len(self.claims)} estimates found in its output")
        except Exception as e:
            self.state["authors_code"] = {"status": "error", "error": str(e)[:500]}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def get_claims(self):
        if self.claims_path:
            return load_claims(self.claims_path)
        claims = self.claims_from_pdfs()
        if claims:
            return claims
        text = read_paper(self.paper)
        if not text or not self.backend:
            return []
        answer = self.backend.complete("claims/extract", prompts.SYSTEM,
                                       prompts.CLAIMS.format(max_claims=15, paper=text[:150000]))
        try:
            claims = _parse_json_block(answer)
        except Exception:
            return []
        for c in claims:
            c["main"] = bool(c.get("main"))
            c["b"] = str(c["b"])
            c["se"] = None if c.get("se") in (None, "") else str(c["se"])
            c["source"] = "model"
        with open(self.out / "claims_extracted.json", "w") as fh:
            json.dump(claims, fh, indent=2, ensure_ascii=False)
        return claims

    def claims_from_pdfs(self, limit=20):
        """Same table reader as the website, run with Node. No AI involved."""
        import subprocess

        pdfs = [p for p in self.pdfs if p.exists() and p.suffix.lower() == ".pdf"]
        tool = Path(__file__).resolve().parent.parent / "tools" / "extract_estimates.js"
        if not pdfs or not tool.exists():
            return []
        try:
            r = subprocess.run(["node", str(tool), *map(str, pdfs)], capture_output=True, text=True, timeout=600)
            found = json.loads(r.stdout or "[]")
        except Exception as e:
            _log(f"PDF table reader failed: {e}")
            return []
        main_tables = [s for s in found if s.get("table") and not str(s["table"]).startswith("S")]
        pick = (main_tables or found)[:limit]
        claims = [{"id": s["id"], "description": s["description"], "b": s["b"], "se": s["se"],
                   "n": s.get("n") or None, "main": bool(s.get("suggestedMain")), "source": "pdf_tables"} for s in pick]
        with open(self.out / "claims_extracted.json", "w") as fh:
            json.dump(claims, fh, indent=2, ensure_ascii=False)
        _log(f"{len(found)} estimates found in the PDF tables; checking {len(claims)}")
        return claims

    def _claims_text(self):
        return "\n".join(f"- {c['id']}: {c['description']} (b={c['b']}, se={c.get('se')}, N={c.get('n')})"
                         for c in self.claims)

    def prepare(self):
        _log("preparing analysis dataset")
        target = self.work / "analysis.parquet"

        def prompt(feedback):
            return prompts.PREP.format(claims=self._claims_text(), profile=self.profile_md,
                                       feedback=feedback)

        def check(res):
            return None if target.exists() else "analysis.parquet was not written to WORK_DIR."

        r, attempts, code = self._ask_and_run("prep", prompt, check=check)
        ok = r is not None and target.exists()
        self.state["prep"] = {"ok": ok, "attempts": attempts, "result": r.result if r else None}
        if ok:
            self.frame_md = describe_frame(target)
            (self.out / "analysis_dataset.md").write_text(self.frame_md, encoding="utf-8")
        _log(f"prep {'ok' if ok else 'FAILED'} after {len(attempts)} attempt(s)")
        return ok

    def rebuild(self, c):
        cid = c["id"]

        def prompt(feedback):
            return prompts.REBUILD.format(cid=cid, description=c["description"], b=c["b"],
                                          se=c.get("se"), n=c.get("n"), frame=self.frame_md,
                                          code=self.code_text[:60000], feedback=feedback)

        def check(res):
            v = verdict(c["b"], c.get("se"), _num(res.get("b")), _num(res.get("se")), c.get("n"), res.get("n"))
            if v["verdict"] in ("exact",):
                return None
            return (f"Your estimate b={res.get('b')}, se={res.get('se')}, n={res.get('n')} does not match "
                    f"the paper (b={c['b']}, se={c.get('se')}, N={c.get('n')}). Re-check the specification, "
                    "sample and variable construction against the authors' code. Do not force the number.")

        r, attempts, code = self._ask_and_run(f"rebuild/{cid}", prompt, target_b=c["b"], check=check)
        c["attempts"] = attempts
        if r is None:  # keep the last successful result even if every attempt mismatched
            last = next((a for a in reversed(attempts) if "result" in a), None)
            res = last["result"] if last else None
        else:
            res = r.result
        if res:
            c["rebuilt"] = {"b": _num(res.get("b")), "se": _num(res.get("se")), "n": res.get("n")}
            c["compare"] = verdict(c["b"], c.get("se"), c["rebuilt"]["b"], c["rebuilt"]["se"], c.get("n"), c["rebuilt"]["n"])
            good = [a for a in attempts if "result" in a]
            c["script"] = good[-1]["script"]
            c["code"] = (self.scripts / c["script"]).read_text()
        else:
            c["rebuilt"] = None
            c["compare"] = {"verdict": "failed"}
        _log(f"{cid}: {c['compare']['verdict']} ({len(attempts)} attempt(s))")

    def robust(self, c):
        cid = c["id"]
        key = f"robust/{cid}"
        try:
            answer = self.backend.complete(key, prompts.SYSTEM, prompts.ROBUST.format(
                cid=cid, description=c["description"], script=c["code"], k=self.n_robust,
                frame=self.frame_md))
            variants = _parse_json_block(answer)
        except MissingFixture:
            return
        except Exception as e:
            c["robustness"] = {"error": f"could not parse variants: {e}"}
            return
        out = []
        for j, v in enumerate(variants, 1):
            script = self.scripts / f"robust__{cid}__{j:02d}.py"
            script.write_text(v["code"], encoding="utf-8")
            r = run_script(script, self.work, self.env, self.timeout)
            row = {"name": v.get("name"), "why": v.get("why"), "script": script.name}
            if r.ok:
                b, se = _num(r.result.get("b")), _num(r.result.get("se"))
                row.update(b=b, se=se, n=r.result.get("n"), p=pvalue(b, se))
            else:
                row["error"] = r.error[-1500:]
            out.append(row)
            _log(f"  {cid} robustness {j}/{len(variants)} {row.get('name')}: "
                 f"{row.get('b', 'error')}")
        base = (c.get("robust_base") or c["rebuilt"])["b"]
        c["robustness"] = {"variants": out, "summary": robustness_summary(base, out)}

    def save(self):
        with open(self.out / "audit.json", "w") as fh:
            json.dump(self.state, fh, indent=2, ensure_ascii=False, default=str)
        rows = []
        for c in self.state["claims"]:
            rb = c.get("rebuilt") or {}
            cmp_ = c.get("compare") or {}
            rs = (c.get("robustness") or {}).get("summary") or {}
            rows.append({"id": c["id"], "description": c["description"], "paper_b": c["b"],
                         "paper_se": c.get("se"), "rebuilt_b": rb.get("b"), "rebuilt_se": rb.get("se"),
                         "rebuilt_n": rb.get("n"), "verdict": cmp_.get("verdict", "pending"),
                         "attempts": len(c.get("attempts", [])),
                         "robust_checks": rs.get("n"), "share_robust_sig05": rs.get("share_same_sign_sig05")})
        with open(self.out / "results.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["id"])
            w.writeheader()
            w.writerows(rows)


def _environment():
    import platform
    import sys

    from . import __version__
    env = {"replicaudit": __version__, "python": sys.version.split()[0], "platform": platform.platform()}
    for mod in ("pandas", "numpy", "pyfixest", "statsmodels"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:
            pass
    return env


def _num(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None
