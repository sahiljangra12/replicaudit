"""Run the authors' own code as shipped (no AI), and collect what it prints and writes.

R and Python run directly. Stata runs only if a licensed `stata`/`stata-mp`/`stata-se` binary is on PATH;
otherwise the package is marked for translation by the AI stage. Every change made to the authors' files
(only: disabling hard-coded working-directory lines) is recorded in the log.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

LANG_EXT = {"R": (".r", ".rmd"), "Python": (".py", ".ipynb"), "Stata": (".do",), "Julia": (".jl",), "MATLAB": (".m",)}
ENTRY_RE = re.compile(r"(^|[_\-\s])(master|main|run_?all|runall|make|replicate|replication|run)([_\-\s.]|$)", re.I)
TEXT_OUT = {".txt", ".log", ".csv", ".tsv", ".tex", ".md", ".html", ".out", ".smcl", ".json", ".rout"}
PY_MAP = {"sklearn": "scikit-learn", "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "bs4": "beautifulsoup4",
          "skimage": "scikit-image", "Bio": "biopython", "dateutil": "python-dateutil", "pyfixest": "pyfixest",
          "linearmodels": "linearmodels", "geopandas": "geopandas", "docx": "python-docx", "fitz": "pymupdf"}


def _scripts(root: Path, exts) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts
                  and not any(part.startswith((".", "_")) or part == "__MACOSX" for part in p.relative_to(root).parts[:-1]))


def detect(root: Path) -> dict:
    counts = {lang: _scripts(root, ext) for lang, ext in LANG_EXT.items()}
    counts = {k: v for k, v in counts.items() if v}
    if not counts:
        return {"language": None, "scripts": [], "all": {}}
    lang = max(counts, key=lambda k: (len(counts[k]), k == "R"))
    scripts = counts[lang]
    entries = [s for s in scripts if ENTRY_RE.search(s.stem)]
    order = entries[:1] if entries else _natural_order(scripts)
    return {"language": lang, "scripts": order, "all": {k: [str(p.relative_to(root)) for p in v] for k, v in counts.items()}}


def _natural_order(scripts: list[Path]) -> list[Path]:
    def key(p):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]
    return sorted(scripts, key=key)


# ------------------------------------------------------------------ dependencies
def r_packages(scripts: list[Path], root: Path) -> list[str]:
    pk = set()
    for f in _scripts(root, LANG_EXT["R"]):
        t = f.read_text(errors="replace")
        pk |= set(re.findall(r"(?:library|require|requireNamespace)\(\s*['\"]?([A-Za-z][\w.]*)", t))
        pk |= set(re.findall(r"\b([A-Za-z][\w.]*)::", t))
        for m in re.findall(r"p_load\(([^)]*)\)", t):
            pk |= set(re.findall(r"[A-Za-z][\w.]*", m))
    base = {"base", "stats", "utils", "methods", "graphics", "grDevices", "datasets", "tools", "parallel", "grid",
            "splines", "stats4", "tcltk", "compiler", "character.only", "TRUE", "FALSE", "T", "F"}
    return sorted(pk - base)


def py_packages(root: Path) -> list[str]:
    mods = set()
    local = {p.stem for p in root.rglob("*.py")} | {p.name for p in root.rglob("*") if p.is_dir()}
    for f in _scripts(root, LANG_EXT["Python"]):
        t = f.read_text(errors="replace")
        if f.suffix == ".ipynb":
            try:
                t = "\n".join("".join(c.get("source", [])) for c in json.loads(t).get("cells", []) if c.get("cell_type") == "code")
            except Exception:
                pass
        mods |= set(re.findall(r"^\s*import\s+([A-Za-z_][\w]*)", t, re.M))
        mods |= set(re.findall(r"^\s*from\s+([A-Za-z_][\w]*)", t, re.M))
    std = set(getattr(sys, "stdlib_module_names", ()))
    return sorted(PY_MAP.get(m, m) for m in mods if m not in std and m not in local and m != "__future__")


def install(lang: str, root: Path, scripts, log) -> None:
    if lang == "R":
        pk = r_packages(scripts, root)
        if not pk:
            return
        log(f"installing R packages: {', '.join(pk)}")
        repo = os.environ.get("R_REPO", "https://packagemanager.posit.co/cran/__linux__/noble/latest")
        code = (f"options(repos=c(CRAN='{repo}'), HTTPUserAgent=sprintf('R/%s R (%s)', getRversion(), "
                f"paste(getRversion(), R.version$platform, R.version$arch, R.version$os)));"
                f"pk <- c({','.join(repr(p) for p in pk)}); need <- pk[!pk %in% rownames(installed.packages())];"
                f"if (length(need)) install.packages(need, Ncpus=4, quiet=TRUE)")
        try:
            r = subprocess.run(["Rscript", "-e", code], capture_output=True, text=True, timeout=_install_limit())
            log(f"R install exit {r.returncode}" + (": " + r.stderr[-600:] if r.returncode else ""))
        except subprocess.TimeoutExpired:
            log("R package installation stopped at the time limit")
    elif lang == "Python":
        pk = py_packages(root)
        req = next(iter(root.rglob("requirements*.txt")), None)
        try:
            if req:
                log(f"installing {req.relative_to(root)}")
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], capture_output=True, timeout=_install_limit())
            stop = time.time() + _install_limit()
            for p in pk:  # one at a time, so one unknown name doesn't block the rest
                left = int(stop - time.time())
                if left < 5:
                    break
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", p], capture_output=True, timeout=left)
        except subprocess.TimeoutExpired:
            log("Python package installation stopped at the time limit")
        if pk:
            log(f"installed Python packages: {', '.join(pk)}")


def _install_limit() -> int:
    return int(os.environ.get("INSTALL_TIMEOUT", 1800))


# ------------------------------------------------------------------ path fixes
PATH_FIXES = {
    "R": [(re.compile(r"^(\s*)(setwd\s*\()", re.M), r"\1# [ReplicAudit disabled] \2")],
    "Python": [(re.compile(r"^(\s*)(os\.chdir\s*\()", re.M), r"\1pass  # [ReplicAudit disabled] \2")],
    "Stata": [(re.compile(r"^(\s*)(cd\s+[\"'`]?[A-Za-z]:|cd\s+[\"']?/(Users|home)/)", re.M | re.I), r"\1* [ReplicAudit disabled] \2")],
}


def neutralise_paths(lang: str, root: Path, log) -> list[str]:
    changed = []
    for f in _scripts(root, LANG_EXT.get(lang, ())):
        if f.suffix == ".ipynb":
            continue
        t = f.read_text(errors="replace")
        new = t
        for rx, rep in PATH_FIXES.get(lang, []):
            new = rx.sub(rep, new)
        if new != t:
            f.write_text(new)
            changed.append(str(f.relative_to(root)))
    if changed:
        log(f"disabled hard-coded working-directory lines in: {', '.join(changed)}")
    return changed


# ------------------------------------------------------------------ run
def _cmd(lang, script: Path):
    if lang == "R":
        if script.suffix.lower() == ".rmd":
            return ["Rscript", "-e", f"rmarkdown::render('{script.name}')"]
        return ["Rscript", script.name]
    if lang == "Python":
        if script.suffix == ".ipynb":
            return [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
                    "--ExecutePreprocessor.timeout=3600", script.name]
        return [sys.executable, script.name]
    if lang == "Stata":
        exe = next((shutil.which(x) for x in ("stata-mp", "stata-se", "stata") if shutil.which(x)), None)
        return [exe, "-b", "do", script.name] if exe else None
    return None


def snapshot(root: Path) -> dict:
    return {str(p): p.stat().st_mtime for p in root.rglob("*") if p.is_file()}


def run_package(root: Path, out_dir: Path, timeout: int = 3 * 3600) -> dict:
    root, out_dir = Path(root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []

    def log(m):
        lines.append(time.strftime("%H:%M:%S ") + m)
        print("[authors-code]", m, flush=True)

    info = detect(root)
    res = {"language": info["language"], "scripts_found": info["all"], "ran": [], "changed_files": [], "outputs": []}
    lang = info["language"]
    if not lang:
        log("no R, Python or Stata scripts found")
        res["status"] = "no code"
        (out_dir / "run_log.txt").write_text("\n".join(lines))
        return res
    log(f"language: {lang}; running: {', '.join(str(s.relative_to(root)) for s in info['scripts'])}")
    if lang == "Stata" and not _cmd("Stata", info["scripts"][0]):
        log("Stata is not installed on this server; the analysis will be translated to Python by the AI stage")
        res["status"] = "needs translation"
        (out_dir / "run_log.txt").write_text("\n".join(lines))
        return res
    if lang in ("Julia", "MATLAB"):
        res["status"] = "unsupported language"
        log(f"{lang} is not supported yet")
        (out_dir / "run_log.txt").write_text("\n".join(lines))
        return res

    res["changed_files"] = neutralise_paths(lang, root, log)
    t_end = time.time() + timeout  # one budget for installing packages and running every script
    install(lang, root, info["scripts"], log)
    before = snapshot(root)
    ok_all = True
    for s in info["scripts"]:
        cmd = _cmd(lang, s)
        left = int(t_end - time.time())
        if left < 10:
            res["ran"].append({"script": str(s.relative_to(root)), "exit": "skipped (time limit)", "seconds": 0})
            res["time_limit_reached"] = True
            ok_all = False
            log(f"{s.relative_to(root)}: skipped, the time limit was reached")
            continue
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=s.parent, capture_output=True, text=True, timeout=left,
                               env={k: v for k, v in os.environ.items() if not k.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))})
            code, so, se = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            res["time_limit_reached"] = True
            code, so, se = "timeout", e.stdout or "", e.stderr or ""
            so = so.decode() if isinstance(so, bytes) else so
            se = se.decode() if isinstance(se, bytes) else se
        rel = str(s.relative_to(root))
        name = re.sub(r"[^\w.-]+", "_", rel)
        (out_dir / f"{name}.stdout.txt").write_text(so or "")
        (out_dir / f"{name}.stderr.txt").write_text(se or "")
        res["ran"].append({"script": rel, "exit": code, "seconds": round(time.time() - t0, 1),
                           "stdout": f"{name}.stdout.txt", "stderr": f"{name}.stderr.txt"})
        log(f"{rel}: exit {code} after {time.time() - t0:.0f}s")
        if code != 0:
            ok_all = False
            log("error tail: " + (se or "")[-800:].replace("\n", " | "))
    after = snapshot(root)
    for f, m in after.items():
        p = Path(f)
        if (f not in before or before[f] != m) and p.suffix.lower() in TEXT_OUT and p.stat().st_size < 5_000_000:
            rel = str(p.relative_to(root))
            dest = out_dir / "files" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, dest)
            res["outputs"].append(rel)
    log(f"{len(res['outputs'])} text output files written by the code")
    res["status"] = "ran" if ok_all else "ran with errors"
    (out_dir / "run_log.txt").write_text("\n".join(lines))
    return res
