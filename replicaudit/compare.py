"""Compare a rebuilt estimate with the number printed in the paper."""
from __future__ import annotations

import math
import re

VERDICTS = {
    "exact": "Reproduced (matches to the reported precision)",
    "close": "Close (same sign, within 5%)",
    "same_sign": "Same sign, different size",
    "different": "Different (sign flipped or not comparable)",
    "failed": "Could not rebuild",
    "not_found": "Not found in the authors' outputs",
}


def decimals_of(s) -> int:
    s = str(s).strip()
    m = re.search(r"\.(\d+)", s)
    return len(m.group(1)) if m else 0


def pvalue(b, se):
    if b is None or not se:
        return None
    z = abs(b / se)
    return math.erfc(z / math.sqrt(2))


def stars(p):
    if p is None:
        return ""
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


def verdict(target_b, target_se, b, se, target_n=None, n=None) -> dict:
    if b is None:
        return {"verdict": "failed"}
    tb = float(target_b)
    dec = decimals_of(target_b)
    tol = 0.5 * 10 ** (-dec) + 1e-12 if dec else abs(tb) * 0.005
    out = {"diff_b": b - tb, "rel_diff": (b - tb) / tb if tb else None,
           "p": pvalue(b, se), "stars": stars(pvalue(b, se))}
    b_ok = abs(b - tb) <= tol
    se_ok = True
    if target_se not in (None, "") and se is not None:
        tse = float(target_se)
        se_tol = 0.5 * 10 ** (-decimals_of(target_se)) + 1e-12
        se_ok = abs(se - tse) <= se_tol
        out["diff_se"] = se - tse
        out["target_stars"] = stars(pvalue(tb, tse))
    n_ok = True
    if target_n not in (None, "") and n not in (None, ""):
        n_ok = int(float(target_n)) == int(float(n))
        out["n_matches"] = n_ok
    same_sign = (b > 0) == (tb > 0)
    if b_ok and se_ok and n_ok:
        v = "exact"
    elif same_sign and tb and abs(b - tb) / abs(tb) <= 0.05:
        v = "close"
    elif same_sign:
        v = "same_sign"
    else:
        v = "different"
    out["verdict"] = v
    return out


def target_literals(target_b) -> list[str]:
    """Spellings of the target number that must not be hard-coded in a script."""
    s = str(target_b).strip().lstrip("+")
    neg = s.startswith("-")
    core = s.lstrip("-")
    if core.startswith("."):
        core = "0" + core
    forms = {core, core.lstrip("0") if core.startswith("0.") else core}
    out = []
    for f in forms:
        if len(f.replace(".", "").strip("0")) >= 2:  # skip trivial numbers like 0.1
            out.append(("-" if neg else "") + f)
    return out


def robustness_summary(base_b, variants: list[dict]) -> dict:
    ok = [v for v in variants if v.get("b") is not None]
    if not ok:
        return {"n": 0}
    same = [v for v in ok if (v["b"] > 0) == (base_b > 0)]
    sig = [v for v in same if (v.get("p") or 1) < 0.05]
    return {
        "n": len(ok), "n_failed": len(variants) - len(ok),
        "share_same_sign": len(same) / len(ok),
        "share_same_sign_sig05": len(sig) / len(ok),
        "min_b": min(v["b"] for v in ok), "max_b": max(v["b"] for v in ok),
        "fragile": len(sig) / len(ok) < 0.75,
    }
