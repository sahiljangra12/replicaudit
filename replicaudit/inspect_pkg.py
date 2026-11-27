"""Profile a replication package without any model: data files, columns, code."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_EXT = {".dta", ".csv", ".parquet", ".xlsx", ".xls", ".tsv", ".rds", ".sav"}
CODE_EXT = {".do", ".r", ".R", ".py", ".m", ".jl", ".sas", ".ado", ".ipynb", ".md", ".txt"}


def _read_head(path: Path, nrows: int = 5):
    ext = path.suffix.lower()
    if ext == ".dta":
        it = pd.read_stata(path, iterator=True)
        df = it.read(nrows)
        try:
            n = it.nobs
        except Exception:  # pragma: no cover
            n = None
        return df, n
    if ext in {".csv", ".tsv"}:
        df = pd.read_csv(path, nrows=nrows, sep="\t" if ext == ".tsv" else ",")
        with open(path, "rb") as fh:
            n = sum(1 for _ in fh) - 1
        return df, n
    if ext == ".parquet":
        df = pd.read_parquet(path)
        return df.head(nrows), len(df)
    if ext in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
        return df.head(nrows), len(df)
    if ext == ".sav":
        df = pd.read_spss(path)
        return df.head(nrows), len(df)
    return None, None


def profile_package(package_dir: str | Path, max_code_chars: int = 60000) -> dict:
    package_dir = Path(package_dir)
    data, code = [], []
    for p in sorted(package_dir.rglob("*")):
        if not p.is_file() or any(part.startswith(".") for part in p.parts):
            continue
        rel = p.relative_to(package_dir).as_posix()
        if p.suffix.lower() in DATA_EXT:
            entry = {"path": rel, "bytes": p.stat().st_size}
            try:
                df, n = _read_head(p)
                if df is not None:
                    entry["rows"] = n
                    entry["columns"] = {c: str(t) for c, t in df.dtypes.items()}
            except Exception as e:  # unreadable files are reported, not fatal
                entry["error"] = f"{type(e).__name__}: {e}"[:200]
            data.append(entry)
        elif p.suffix in CODE_EXT:
            code.append({"path": rel, "bytes": p.stat().st_size})
    # concatenate code text (largest analysis scripts first), capped
    code_text, used = [], 0
    for c in sorted(code, key=lambda c: -c["bytes"]):
        if c["path"].lower().endswith((".md", ".txt")) and c["bytes"] > 20000:
            continue
        txt = (package_dir / c["path"]).read_text(encoding="utf-8", errors="replace")
        room = max_code_chars - used
        if room <= 0:
            break
        code_text.append(f"===== {c['path']} =====\n{txt[:room]}")
        used += min(len(txt), room)
    return {"package_dir": str(package_dir), "data_files": data, "code_files": code,
            "code_text": "\n\n".join(code_text)}


def profile_to_markdown(profile: dict, include_code: bool = True) -> str:
    lines = ["## Data files"]
    for d in profile["data_files"]:
        if "error" in d:
            lines.append(f"- {d['path']}  (could not read: {d['error']})")
            continue
        cols = ", ".join(f"{c}:{t}" for c, t in d.get("columns", {}).items())
        lines.append(f"- {d['path']}  rows={d.get('rows')}  columns: {cols}")
    lines.append("\n## Code files")
    lines += [f"- {c['path']} ({c['bytes']} bytes)" for c in profile["code_files"]]
    if include_code and profile["code_text"]:
        lines.append("\n## Code contents\n" + profile["code_text"])
    return "\n".join(lines)


def describe_frame(path: str | Path, max_cols: int = 200) -> str:
    """Short text description of the prepared analysis dataset."""
    df = pd.read_parquet(path)
    out = [f"rows={len(df)} columns={df.shape[1]}"]
    for c in list(df.columns)[:max_cols]:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            out.append(f"- {c} ({s.dtype}): missing={int(s.isna().sum())} mean={s.mean():.4g}")
        else:
            out.append(f"- {c} ({s.dtype}): missing={int(s.isna().sum())} unique={s.nunique()}")
    return "\n".join(out)
