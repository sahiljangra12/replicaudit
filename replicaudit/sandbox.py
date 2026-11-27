"""Run model-written scripts in a separate process and read their result.

This is process isolation with a timeout, not a security sandbox.  Run large
batches inside Docker (see README) because model-written code is untrusted.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

RESULT_RE = re.compile(r"^RESULT_JSON:\s*(\{.*\})\s*$", re.M)
CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


@dataclass
class RunResult:
    ok: bool
    result: dict | None
    stdout: str
    stderr: str
    seconds: float
    error: str = ""
    extra: dict = field(default_factory=dict)


def extract_code(answer: str) -> str | None:
    blocks = CODE_RE.findall(answer)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    if "RESULT_JSON" in answer and "import" in answer:  # bare script
        return answer.strip() + "\n"
    return None


def run_script(script: Path, workdir: Path, env_extra: dict, timeout: int = 900) -> RunResult:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))}  # never pass credentials
    env.update({k: str(v) for k, v in env_extra.items()})
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-I", str(script)], cwd=workdir, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return RunResult(False, None, e.stdout or "", e.stderr or "", time.time() - t0,
                         error=f"timed out after {timeout}s")
    secs = time.time() - t0
    m = RESULT_RE.findall(p.stdout)
    if p.returncode != 0:
        tail = p.stderr.strip().splitlines()[-25:]
        return RunResult(False, None, p.stdout, p.stderr, secs,
                         error="script failed:\n" + "\n".join(tail))
    if not m:
        return RunResult(False, None, p.stdout, p.stderr, secs,
                         error="script ran but printed no RESULT_JSON line")
    try:
        res = json.loads(m[-1])
    except json.JSONDecodeError as e:
        return RunResult(False, None, p.stdout, p.stderr, secs, error=f"bad RESULT_JSON: {e}")
    return RunResult(True, res, p.stdout, p.stderr, secs)
