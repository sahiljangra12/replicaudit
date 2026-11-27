"""Find each reported estimate in the text the authors' code produced.

A claim counts as found when a number that rounds (to the decimals the paper prints) to the coefficient is
followed within a short distance by a number that rounds to the standard error. Matches are reported with
the file and a snippet, so a reviewer can see exactly where the number came from.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .compare import decimals_of

NUM_RE = re.compile(r"(?<![\w.])[-−]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
WINDOW = 260  # characters after the coefficient in which the standard error must appear


def _round(x: float, d: int) -> Decimal:
    return Decimal(repr(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)


def _target(s: str):
    d = decimals_of(s)
    return Decimal(str(s).replace("−", "-").strip()).quantize(Decimal(1).scaleb(-d)), d


def numbers(text: str):
    for m in NUM_RE.finditer(text):
        try:
            yield m.start(), float(m.group().replace("−", "-")), m.group()
        except ValueError:
            continue


def find_claim(claim: dict, texts: dict[str, str], max_hits: int = 3) -> list[dict]:
    try:
        tb, db = _target(claim["b"])
    except Exception:
        return []
    se = claim.get("se")
    tse, dse = _target(se) if se not in (None, "") else (None, None)
    hits = []
    for fname, text in texts.items():
        nums = list(numbers(text))
        for i, (pos, val, raw) in enumerate(nums):
            if "." not in raw and "e" not in raw.lower():
                continue
            if _round(val, db) != tb:
                continue
            if tse is None:
                hits.append(_hit(fname, text, pos, raw, None))
            else:
                for pos2, val2, raw2 in nums[i + 1:i + 12]:
                    if pos2 - pos > WINDOW:
                        break
                    if _round(abs(val2), dse) == abs(tse):
                        hits.append(_hit(fname, text, pos, raw, raw2))
                        break
            if len(hits) >= max_hits:
                return hits
    return hits


def _hit(fname, text, pos, raw, raw_se):
    a = text.rfind("\n", 0, max(0, pos - 1))
    a = text.rfind("\n", 0, max(0, a - 1)) if a > 0 else 0
    b = text.find("\n", pos + 120)
    snippet = text[max(0, a):b if b > 0 else pos + 200].strip("\n")
    line = text.count("\n", 0, pos) + 1
    return {"file": fname, "line": line, "coef_text": raw, "se_text": raw_se, "snippet": snippet[:600]}


def load_texts(run_dir: Path) -> dict[str, str]:
    run_dir = Path(run_dir)
    out = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".txt", ".log", ".csv", ".tsv", ".tex", ".md", ".html", ".out", ".smcl", ".json", ".rout"}:
            if p.name == "run_log.txt" or p.name.endswith(".stderr.txt") and p.stat().st_size == 0:
                continue
            try:
                out[str(p.relative_to(run_dir))] = p.read_text(errors="replace")[:5_000_000]
            except Exception:
                pass
    return out


def match_claims(claims: list[dict], run_dir: Path) -> None:
    texts = load_texts(run_dir)
    for c in claims:
        hits = find_claim(c, texts)
        c["authors_code"] = {"found": bool(hits), "hits": hits}
