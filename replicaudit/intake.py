"""Turn a submission (GitHub issue form) into an audit folder under audits/<slug>/.

Only metadata, checksums, scripts and results are kept in the repository. The authors' data and
the paper PDF are downloaded to a temporary folder and never committed (licences vary).
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import unicodedata
from pathlib import Path

from .fetch import FetchError, fetch_file, fetch_package, sha256_file

FIELDS = {
    "Paper title": "title",
    "Authors": "authors",
    "Journal and year": "journal_year",
    "Paper DOI": "doi",
    "Paper PDF (open-access link or attachment)": "paper",
    "Replication package": "package",
    "Supplementary materials": "supplement",
    "Claims to check (optional)": "claims_csv",
    "Field": "field",
    "Your relationship to the paper": "relationship",
    "Notes for the auditors": "notes",
}
URL_RE = re.compile(r"(?:https?|upload)://[^\s)<>\]]+")


def parse_issue_form(body: str) -> dict:
    out, cur, buf = {}, None, []

    def flush():
        if cur:
            val = "\n".join(buf).strip()
            out[FIELDS.get(cur, cur)] = None if val in ("", "_No response_", "None") else val

    for line in body.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^###\s+(.*?)\s*$", line)
        if m:
            flush()
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    flush()
    return out


def first_link(text: str | None) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip(".,;")
    t = text.strip()
    return t if re.match(r"^(doi:)?10\.\d{4,9}/", t, re.I) else None


def all_links(text: str | None) -> list[str]:
    if not text:
        return []
    out = [m.rstrip(".,;") for m in URL_RE.findall(text)]
    out += [t.strip() for t in text.splitlines() if re.match(r"^(doi:)?10\.\d{4,9}/\S+$", t.strip(), re.I)]
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def slugify(sub: dict) -> str:
    first = (sub.get("authors") or "anon").split(",")[0].split(" and ")[0].strip().split()
    surname = first[-1] if first else "anon"
    year = re.search(r"(19|20)\d{2}", sub.get("journal_year") or "")
    words = [w for w in re.findall(r"[A-Za-z]+", sub.get("title") or "") if len(w) > 3][:3]
    raw = "-".join([surname, year.group(0) if year else "nd"] + words).lower()
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")[:60]


def claims_from_csv_text(text: str, dest: Path) -> Path | None:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```\w*\n|```$", "", t).strip()
    if not t.lower().startswith("id,"):
        t = "id,description,b,se,n,main\n" + t
    dest.write_text(t + "\n", encoding="utf-8")
    return dest


DATA_EXT = (".csv", ".tsv", ".dta", ".rds", ".rdata", ".rda", ".xlsx", ".xls", ".sav", ".por", ".parquet",
            ".feather", ".sas7bdat", ".xpt", ".json", ".dat", ".txt", ".shp", ".gpkg", ".nc", ".h5", ".hdf5",
            ".mat", ".db", ".sqlite")
CODE_EXT = (".r", ".rmd", ".qmd", ".py", ".ipynb", ".do", ".ado", ".jl", ".m", ".sas", ".sps")
IGNORE = ("readme", "license", "licence", "citation", "requirements", "codebook")


class NotEnoughMaterial(FetchError):
    pass


def check_material(files: list[str], has_paper: bool, has_claims: bool) -> tuple[list[str], list[str]]:
    """Is there enough to run an audit? Returns (problems that stop it, notes)."""
    names = [f for f in files if not any(Path(f).name.lower().startswith(w) for w in IGNORE)
             and "__MACOSX" not in f and not Path(f).name.startswith(".")]
    low = [f.lower() for f in names]
    data = [f for f in low if f.endswith(DATA_EXT)]
    code = [f for f in low if f.endswith(CODE_EXT)]
    problems, notes = [], []
    if not files:
        problems.append("The replication package was empty: no files could be downloaded from the link or upload.")
    elif not data and not code:
        if len(files) <= 6:
            found = "it contained only " + ", ".join(Path(f).name for f in files)
        else:
            kinds = sorted({Path(f).suffix.lower() or "files without an extension" for f in files})[:8]
            found = f"it contained {len(files)} files, all of type " + ", ".join(kinds)
        problems.append("No data or analysis code was found in the replication package (" + found + "). "
                        "Please send the package with the data files (.csv, .dta, .rds, .xlsx, ...) and the scripts.")
    elif not data:
        problems.append("The replication package has code but no data files, so nothing can be recomputed. "
                        "If the data are held elsewhere (for example a restricted archive), they cannot be audited here.")
    elif not code:
        notes.append("No analysis scripts were found, only data. The estimates are rebuilt from the data; "
                     "the authors' own code could not be checked.")
    if not has_paper and not has_claims:
        problems.append("Neither the paper nor a list of estimates was provided, so there is nothing to compare "
                        "against. Add the paper PDF or type the estimates to check.")
    return problems, notes


def fetch_materials(body: str, root: Path, materials: Path, issue: int | None = None,
                    issue_url: str | None = None) -> Path:
    """Step 1 (has access to the private uploads): parse the request, download everything into
    `materials`, and write audits/<slug>/submission.json. Runs no untrusted code."""
    from .pipeline import read_paper

    sub = parse_issue_form(body)
    for need in ("title", "doi", "package"):
        if not sub.get(need):
            raise SystemExit(f"Submission is missing: {need}")
    slug = slugify(sub)
    adir = Path(root) / slug
    if adir.exists():
        slug = f"{slug}-{time.strftime('%Y%m%d%H%M')}"
        adir = Path(root) / slug
    adir.mkdir(parents=True)
    tmp = Path(materials)
    tmp.mkdir(parents=True, exist_ok=True)
    record = {"slug": slug, "issue": issue, "issue_url": issue_url,
              "submitted": time.strftime("%Y-%m-%d"), "status": "unreviewed",
              **{k: sub.get(k) for k in ("title", "authors", "journal_year", "doi", "field",
                                         "relationship", "notes")}}
    state = {"slug": slug, "adir": str(adir), "title": sub["title"], "pdfs": [], "paper_txt": None, "claims": None}
    try:
        pkg_src = first_link(sub["package"])
        if not pkg_src:
            raise FetchError("No link or uploaded file was found for the replication package.")
        record["package"] = fetch_package(pkg_src, tmp / "package")

        texts = []
        link = first_link(sub.get("paper"))
        if link:
            try:
                f = fetch_file(link, tmp / "paper")
                record["paper"] = {"source": link, "sha256": sha256_file(f), "bytes": f.stat().st_size}
                texts.append("===== PAPER =====\n" + read_paper(f))
                state["pdfs"].append(str(f))
            except Exception as e:
                record["paper"] = {"source": link, "error": str(e)[:300]}
        # every supplementary file: PDFs are read for estimates, anything else joins the package
        record["supplement"] = []
        for i, link in enumerate(all_links(sub.get("supplement")), 1):
            try:
                f = fetch_file(link, tmp / f"supplement_{i}")
                entry = {"source": link, "file": f.name, "sha256": sha256_file(f), "bytes": f.stat().st_size}
                if f.suffix.lower() == ".pdf":
                    texts.append(f"===== SUPPLEMENT {i}: {f.name} =====\n" + read_paper(f))
                    state["pdfs"].append(str(f))
                else:
                    dest = tmp / "package" / "_supplementary"
                    dest.mkdir(parents=True, exist_ok=True)
                    shutil.copy(f, dest / f.name)
                    entry["added_to_package"] = True
                record["supplement"].append(entry)
            except Exception as e:
                record["supplement"].append({"source": link, "error": str(e)[:300]})
        if any(e.get("added_to_package") for e in record["supplement"]):
            from .fetch import manifest, unpack_archives
            record["package"]["unpacked"] += unpack_archives(tmp / "package" / "_supplementary")
            record["package"]["manifest"] = manifest(tmp / "package")
        if texts:
            pt = tmp / "paper_and_supplement.txt"
            pt.write_text("\n\n".join(texts), encoding="utf-8")
            state["paper_txt"] = str(pt)
        claims = claims_from_csv_text(sub.get("claims_csv"), adir / "claims_submitted.csv")
        state["claims"] = str(claims) if claims else None
        problems, notes = check_material([m["path"] for m in record["package"].get("manifest", [])],
                                         bool(state["pdfs"]) or bool(texts), bool(claims))
        if notes:
            record["notes_material"] = notes
        if problems:
            raise NotEnoughMaterial(" ".join(problems))
        state["ok"] = True
    except Exception as e:  # any download problem becomes a clear message on the request page
        record["status"] = "not enough material" if isinstance(e, NotEnoughMaterial) else "could not fetch"
        record["error"] = str(e) if isinstance(e, FetchError) else f"The materials could not be downloaded ({type(e).__name__}: {str(e)[:200]})."
        state["ok"] = False
    # Uploaded files are now on the runner: delete them from the intake store.
    from .fetch import UPLOAD_RE, delete_uploads
    removed = sum(delete_uploads(rid) for rid in sorted({m.group(1) for m in UPLOAD_RE.finditer(body)}))
    if removed:
        record["uploads_removed"] = removed
    (adir / "submission.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    (tmp / "state.json").write_text(json.dumps(state))
    return adir


def audit_materials(materials: Path, backend, **audit_opts) -> Path:
    """Step 2 (no access to the private uploads): run the audit on what step 1 downloaded."""
    from .pipeline import Audit
    from .report import build_report

    materials = Path(materials)
    state = json.loads((materials / "state.json").read_text())
    adir = Path(state["adir"])
    if not state.get("ok"):
        return adir
    try:
        audit = Audit(backend, materials / "package", adir, paper=state.get("paper_txt"), claims=state.get("claims"),
                      pdfs=state.get("pdfs"), **audit_opts)
        audit.state["title"] = state["title"]
        st = audit.run()
        build_report(adir)
        sj = adir / "submission.json"
        rec = json.loads(sj.read_text())
        if st.get("problem"):
            rec["status"], rec["error"] = "needs estimates", st["problem"]
        sj.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(adir / "work", ignore_errors=True)  # derived data never committed
    return adir


def run_intake(body: str, root: Path, backend, issue: int | None = None, issue_url: str | None = None,
               **audit_opts) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="replicaudit_"))
    try:
        fetch_materials(body, root, tmp, issue, issue_url)
        return audit_materials(tmp, backend, **audit_opts)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
