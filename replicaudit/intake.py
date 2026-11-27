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
URL_RE = re.compile(r"https?://[^\s)<>\]]+")


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


def run_intake(body: str, root: Path, backend, issue: int | None = None, issue_url: str | None = None,
               **audit_opts) -> Path:
    from .pipeline import Audit, read_paper
    from .report import build_report

    sub = parse_issue_form(body)
    for need in ("title", "doi", "package"):
        if not sub.get(need):
            raise SystemExit(f"Submission is missing: {need}")
    slug = slugify(sub)
    adir = Path(root) / slug
    if adir.exists():
        slug = f"{slug}-{time.strftime('%Y%m%d')}"
        adir = Path(root) / slug
    adir.mkdir(parents=True)

    tmp = Path(tempfile.mkdtemp(prefix="replicaudit_"))
    record = {"slug": slug, "issue": issue, "issue_url": issue_url,
              "submitted": time.strftime("%Y-%m-%d"), "status": "under review",
              **{k: sub.get(k) for k in ("title", "authors", "journal_year", "doi", "field",
                                         "relationship", "notes")}}
    try:
        pkg_src = first_link(sub["package"])
        if not pkg_src:
            raise FetchError("No link or attachment found for the replication package.")
        record["package"] = fetch_package(pkg_src, tmp / "package")

        texts = []
        for key in ("paper", "supplement"):
            link = first_link(sub.get(key))
            if not link:
                continue
            try:
                f = fetch_file(link, tmp / key)
                record[key] = {"source": link, "sha256": sha256_file(f), "bytes": f.stat().st_size}
                texts.append(f"===== {key.upper()} =====\n" + read_paper(f))
            except Exception as e:
                record[key] = {"source": link, "error": str(e)[:300]}
        paper_txt = None
        if texts:
            paper_txt = tmp / "paper_and_supplement.txt"
            paper_txt.write_text("\n\n".join(texts), encoding="utf-8")
        claims = claims_from_csv_text(sub.get("claims_csv"), adir / "claims_submitted.csv")
        if not claims and not paper_txt:
            raise SystemExit("Need either a readable paper PDF or a claims table.")

        (adir / "submission.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
        audit = Audit(backend, tmp / "package", adir, paper=paper_txt, claims=claims, **audit_opts)
        audit.state["title"] = sub["title"]
        audit.run()
        build_report(adir)
    except FetchError as e:
        record["status"] = "could not fetch"
        record["error"] = str(e)
        (adir / "submission.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(adir / "work", ignore_errors=True)  # derived data never committed
    return adir
