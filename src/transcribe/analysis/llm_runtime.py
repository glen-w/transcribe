"""Text LLM runtime for analysis modules (local Ollama + recorded doubles)."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class TextLLMClient(Protocol):
    def healthcheck(self) -> bool: ...

    def resolve_model(self, preferred: str | None = None) -> str | None: ...

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str: ...

    def model_digest(self, model: str) -> str: ...


@dataclass
class OllamaTextClient:
    """Minimal text generate client against Ollama HTTP API."""

    base_url: str = "http://localhost:11434"
    timeout_s: float = 120.0

    def _root(self) -> str:
        return self.base_url.rstrip("/")

    def healthcheck(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._root()}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=min(5.0, self.timeout_s)) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(f"{self._root()}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=min(10.0, self.timeout_s)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []
        names: list[str] = []
        for row in data.get("models") or []:
            name = row.get("name") or row.get("model")
            if name:
                names.append(str(name))
        return names

    def resolve_model(self, preferred: str | None = None) -> str | None:
        names = self.list_models()
        if preferred and preferred in names:
            return preferred
        # Prefer common small instruct models when present.
        for cand in (
            preferred,
            "llama3.2:latest",
            "llama3.2",
            "mistral:latest",
            "qwen2.5:latest",
        ):
            if cand and cand in names:
                return cand
        return names[0] if names else None

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt if system is None else f"{system}\n\n{prompt}",
            "stream": False,
            "options": options or {"temperature": 0.0, "num_predict": 1024},
        }
        raw = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self._root()}/api/generate",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload.get("response") or "")

    def model_digest(self, model: str) -> str:
        return hashlib.sha256(f"ollama:{model}".encode("utf-8")).hexdigest()


@dataclass
class RecordedDoubleClient:
    """Deterministic double — same validation path as live; no network."""

    responses: dict[str, str]
    model_name: str = "recorded-double:v1"
    healthy: bool = True

    def healthcheck(self) -> bool:
        return self.healthy

    def resolve_model(self, preferred: str | None = None) -> str | None:
        if not self.healthy:
            return None
        return preferred or self.model_name

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        key = hashlib.sha256(
            f"{system or ''}\n{prompt}".encode("utf-8")
        ).hexdigest()[:16]
        if key in self.responses:
            return self.responses[key]
        # Fallback: match by substring markers in prompt.
        for marker, text in self.responses.items():
            if marker.startswith("contains:") and marker[9:] in prompt:
                return text
        if "default" in self.responses:
            return self.responses["default"]
        raise RuntimeError(f"no recorded response for prompt key {key}")

    def model_digest(self, model: str) -> str:
        return hashlib.sha256(f"recorded:{model}".encode("utf-8")).hexdigest()


_DEFAULT_CLIENT: TextLLMClient | None = None


def get_text_llm_client() -> TextLLMClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = OllamaTextClient()
    return _DEFAULT_CLIENT


def set_text_llm_client(client: TextLLMClient | None) -> None:
    """Test hook to inject recorded doubles."""
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = client


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extract of a JSON object from model text."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
