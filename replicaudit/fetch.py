"""Download a replication package, paper or supplement from a DOI or URL and record checksums.

Supported: Zenodo records, Harvard (and other) Dataverse datasets, OSF projects, GitHub repositories,
GitHub issue attachments, and any direct link to a .zip/.pdf/data file. Sources behind a login
(e.g. openICPSR) cannot be fetched automatically: the submitter must attach a zip instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

UA = {"User-Agent": "ReplicAudit/0.2 (+https://github.com/sahiljangra12/replicaudit)"}
MAX_BYTES = 2 * 1024**3  # 2 GB per package


class FetchError(RuntimeError):
    pass


def _get(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def _json(url: str):
    with _get(url) as r:
        return json.loads(r.read().decode())


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with _get(url, timeout=600) as r, open(dest, "wb") as fh:
        while chunk := r.read(1 << 20):
            total += len(chunk)
            if total > MAX_BYTES:
                raise FetchError(f"{url} is larger than {MAX_BYTES // 1024**3} GB")
            fh.write(chunk)
    return dest


UPLOAD_RE = re.compile(r"upload://([A-Za-z0-9_-]+)/([^\s)]+)")


def fetch_upload(ref: str, dest_dir: Path) -> Path:
    """Files sent through the website are stored (in parts of up to 4 MB) in a private repository.
    ref looks like upload://<request id>/<file name>. Needs UPLOADS_REPO and UPLOADS_TOKEN."""
    m = UPLOAD_RE.search(ref)
    if not m:
        raise FetchError(f"bad upload reference: {ref}")
    rid, name = m.group(1), urllib.parse.unquote(m.group(2))
    repo, token = os.environ.get("UPLOADS_REPO"), os.environ.get("UPLOADS_TOKEN")
    if not repo or not token:
        raise FetchError("UPLOADS_REPO / UPLOADS_TOKEN are not configured, so uploaded files cannot be read")
    api = f"https://api.github.com/repos/{repo}/contents/{rid}"
    hdr = {**UA, "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    with urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60) as r:
        listing = json.loads(r.read().decode())
    parts = sorted((e for e in listing if e["name"].startswith(name + ".part")), key=lambda e: e["name"])
    if not parts:
        raise FetchError(f"uploaded file {name} not found")
    dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = {**hdr, "Accept": "application/vnd.github.raw"}
    with open(dest, "wb") as fh:
        for e in parts:
            with urllib.request.urlopen(urllib.request.Request(e["url"], headers=raw), timeout=300) as r:
                fh.write(r.read())
    return dest


def resolve_doi(s: str) -> str:
    """Turn 'doi:10.x/..', '10.x/..' or a doi.org link into the landing-page URL."""
    s = s.strip()
    m = re.search(r"(10\.\d{4,9}/\S+)", s)
    if not m or ("doi" not in s.lower() and not s.startswith("10.")):
        return s
    doi = m.group(1).rstrip(".")
    req = urllib.request.Request("https://doi.org/" + doi, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.geturl()
    except Exception:
        return "https://doi.org/" + doi


def _safe_extract(zip_path: Path, out: Path):
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (out / info.filename).resolve()
            if not str(target).startswith(str(out.resolve())):
                raise FetchError(f"unsafe path in zip: {info.filename}")
        z.extractall(out)


def _flatten_single_root(out: Path):
    """GitHub/OSF zips wrap everything in one folder; lift its contents up."""
    kids = [p for p in out.iterdir() if not p.name.startswith(".")]
    if len(kids) == 1 and kids[0].is_dir():
        inner = kids[0]
        for p in inner.iterdir():
            shutil.move(str(p), out / p.name)
        inner.rmdir()


def fetch_package(source: str, out: Path) -> dict:
    """Download `source` into folder `out`; returns provenance info."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if source.startswith("upload://"):
        f = fetch_upload(source, out)
        info = {"source": source, "kind": "upload", "file": f.name}
        info["unpacked"] = unpack_archives(out)
        info["manifest"] = manifest(out)
        info["package_sha256"] = hashlib.sha256(
            "\n".join(f"{m['sha256']}  {m['path']}" for m in info["manifest"]).encode()).hexdigest()
        return info
    url = resolve_doi(source)
    host = urllib.parse.urlparse(url).netloc.lower()
    info = {"source": source, "resolved_url": url}

    if "zenodo.org" in host:
        rid = re.search(r"/records?/(\d+)", url).group(1)
        rec = _json(f"https://zenodo.org/api/records/{rid}")
        info.update(kind="zenodo", title=rec.get("metadata", {}).get("title"), version=rec.get("metadata", {}).get("version"))
        for f in rec.get("files", []):
            name = f.get("key") or f.get("filename")
            _download(f["links"]["self"], out / name)
    elif "/dataset.xhtml" in url or "dataverse" in host:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        pid = q.get("persistentId", [None])[0]
        if not pid:
            raise FetchError("Dataverse link must contain ?persistentId=doi:...")
        base = f"https://{host}"
        meta = _json(f"{base}/api/datasets/:persistentId/?persistentId={urllib.parse.quote(pid)}")
        v = meta["data"]["latestVersion"]
        info.update(kind="dataverse", persistent_id=pid,
                    version=f"{v.get('versionNumber')}.{v.get('versionMinorNumber')}")
        for f in v["files"]:
            df = f["dataFile"]
            rel = Path(f.get("directoryLabel") or "") / (df.get("originalFileName") or df["filename"])
            _download(f"{base}/api/access/datafile/{df['id']}?format=original", out / rel)
    elif "osf.io" in host:
        node = urllib.parse.urlparse(url).path.strip("/").split("/")[0]
        info.update(kind="osf", node=node)
        z = _download(f"https://files.osf.io/v1/resources/{node}/providers/osfstorage/?zip=", out / "_osf.zip")
        _safe_extract(z, out)
        z.unlink()
    elif host == "github.com" and "/user-attachments/" not in url and "/files/" not in url:
        parts = urllib.parse.urlparse(url).path.strip("/").split("/")
        owner, repo = parts[0], parts[1].removesuffix(".git")
        ref = parts[3] if len(parts) > 3 and parts[2] == "tree" else None
        cmd = ["git", "clone", "--depth", "1", f"https://github.com/{owner}/{repo}.git", str(out / "_gh")]
        if ref:
            cmd[3:3] = ["--branch", ref]
        subprocess.run(cmd, check=True, capture_output=True)
        commit = subprocess.run(["git", "-C", str(out / "_gh"), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        shutil.rmtree(out / "_gh" / ".git")
        for p in (out / "_gh").iterdir():
            shutil.move(str(p), out / p.name)
        (out / "_gh").rmdir()
        info.update(kind="github", repo=f"{owner}/{repo}", ref=ref or "default", commit=commit)
    elif "openicpsr" in host or "icpsr.umich.edu" in host:
        raise FetchError("openICPSR needs a login and cannot be downloaded automatically. "
                         "Please attach the package as a .zip to the request instead.")
    else:
        name = Path(urllib.parse.urlparse(url).path).name or "download"
        f = _download(url, out / name)
        info["kind"] = "url"
        if zipfile.is_zipfile(f):
            _safe_extract(f, out)
            f.unlink()
            _flatten_single_root(out)

    info["unpacked"] = unpack_archives(out)
    info["manifest"] = manifest(out)
    info["package_sha256"] = hashlib.sha256(
        "\n".join(f"{m['sha256']}  {m['path']}" for m in info["manifest"]).encode()).hexdigest()
    return info


def fetch_file(source: str, dest_dir: Path) -> Path:
    """Download a single document (paper or supplement); returns its path."""
    if source.startswith("upload://"):
        return fetch_upload(source, Path(dest_dir))
    url = resolve_doi(source)
    name = Path(urllib.parse.urlparse(url).path).name or "document"
    if not Path(name).suffix:
        name += ".pdf"
    return _download(url, Path(dest_dir) / name)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def manifest(folder: Path) -> list[dict]:
    folder = Path(folder)
    return [{"path": p.relative_to(folder).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
            for p in sorted(folder.rglob("*")) if p.is_file()]


ARCHIVES = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz", ".tar.bz2")


def unpack_archives(folder: Path, depth: int = 2) -> list[str]:
    """Unpack archives found inside the package (authors often ship DATA.rar etc.).
    The original archive is kept and listed in the manifest; contents go next to it."""
    done, seen = [], set()
    for _ in range(depth):
        found = [p for p in Path(folder).rglob("*")
                 if p.is_file() and p.name.lower().endswith(ARCHIVES) and p.as_posix() not in seen]
        if not found:
            break
        for a in found:
            seen.add(a.as_posix())
            dest = a.parent
            name = a.name.lower()
            try:
                if name.endswith(".zip"):
                    _safe_extract(a, dest)
                elif name.endswith(".rar"):
                    from unrar.cffi import rarfile  # pip install unrar-cffi
                    r = rarfile.RarFile(str(a))
                    for n in r.namelist():
                        t = (dest / n).resolve()
                        if not str(t).startswith(str(dest.resolve())) or n.endswith("/") or t.is_dir():
                            continue
                        if any(x.startswith(n + "/") for x in r.namelist()):
                            t.mkdir(parents=True, exist_ok=True)  # directory entry without slash
                            continue
                        t.parent.mkdir(parents=True, exist_ok=True)
                        t.write_bytes(r.read(n))
                elif name.endswith(".7z"):
                    import py7zr  # pip install py7zr
                    with py7zr.SevenZipFile(a) as z:
                        z.extractall(dest)
                else:
                    with tarfile.open(a) as t:
                        t.extractall(dest, filter="data")
                done.append(a.name)
            except Exception as e:  # keep going; the report lists what could not be opened
                done.append(f"{a.name} (could not unpack: {type(e).__name__}: {e})")
    for junk in Path(folder).rglob(".DS_Store"):
        junk.unlink()
    for junk in Path(folder).rglob("__MACOSX"):
        shutil.rmtree(junk, ignore_errors=True)
    return done
