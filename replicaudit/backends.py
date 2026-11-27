"""Model backends.

Every call has a stable *key* (e.g. "rebuild/T1c3/attempt1").  Live backends
ignore the key; the LoggingBackend wrapper saves each answer under that key so
any run can later be replayed exactly with ReplayBackend.
"""
from __future__ import annotations

import os
from pathlib import Path


class Backend:
    name = "base"

    def complete(self, key: str, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError


class AnthropicBackend(Backend):
    """Claude through the Anthropic API (needs ANTHROPIC_API_KEY)."""

    name = "anthropic"

    def __init__(self, model: str | None = None, max_tokens: int = 8000):
        import anthropic  # imported lazily so other backends work without it

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("REPLICAUDIT_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens

    def complete(self, key, system, user):
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class OpenAICompatBackend(Backend):
    """Any OpenAI-compatible server, e.g. a free local model in Ollama:
    base_url=http://localhost:11434/v1, model=qwen2.5-coder:32b
    """

    name = "openai"

    def __init__(self, model: str, base_url: str | None = None, api_key: str | None = None):
        from openai import OpenAI

        self.client = OpenAI(
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            api_key=api_key or os.environ.get("OPENAI_API_KEY", "ollama"),
        )
        self.model = model

    def complete(self, key, system, user):
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        return r.choices[0].message.content or ""


class MissingFixture(KeyError):
    pass


def key_to_filename(key: str) -> str:
    return key.replace("/", "__") + ".txt"


class ReplayBackend(Backend):
    """Answers from saved files: <dir>/<key with / -> __>.txt"""

    name = "replay"

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def complete(self, key, system, user):
        f = self.dir / key_to_filename(key)
        if not f.exists():
            raise MissingFixture(key)
        return f.read_text(encoding="utf-8")


class LoggingBackend(Backend):
    """Wraps a backend and saves every prompt and answer to the run folder."""

    def __init__(self, inner: Backend, log_dir: str | Path):
        self.inner = inner
        self.name = inner.name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0

    def complete(self, key, system, user):
        self.calls += 1
        (self.log_dir / ("PROMPT__" + key_to_filename(key))).write_text(
            "### SYSTEM\n" + system + "\n\n### USER\n" + user, encoding="utf-8"
        )
        out = self.inner.complete(key, system, user)
        (self.log_dir / key_to_filename(key)).write_text(out, encoding="utf-8")
        return out


def make_backend(kind: str, model: str | None = None, fixtures: str | None = None,
                 base_url: str | None = None) -> Backend:
    if kind == "anthropic":
        return AnthropicBackend(model)
    if kind == "openai":
        if not model:
            raise SystemExit("--model is required for the openai backend (e.g. qwen2.5-coder:32b)")
        return OpenAICompatBackend(model, base_url)
    if kind == "replay":
        if not fixtures:
            raise SystemExit("--fixtures is required for the replay backend")
        return ReplayBackend(fixtures)
    raise SystemExit(f"unknown backend {kind!r}")
