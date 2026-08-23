"""Text LLM runtime for analysis modules (shared Ollama transport + recorded doubles)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any, Protocol

from transcribe.errors import ProviderError
from transcribe.providers.base import ModelInfo
from transcribe.providers.ollama import (
    DEFAULT_MAX_RETRIES,
    OllamaVisionProvider,
    call_with_retries,
    normalize_base_url,
)
from transcribe.runtime_paths import default_ollama_base_url

from transcribe.services.model_advice import is_ocr_oriented_name

_UNSUITABLE_NAME = re.compile(
    r"(vision|embed|embedding|mllama|llava|minicpm-v|moondream|clip)",
    re.IGNORECASE,
)
_UNSUITABLE_CAPS = frozenset({"vision", "embedding", "embed"})
_TEXT_CAPS = frozenset({"completion", "chat", "tools"})


class TextLLMClient(Protocol):
    def healthcheck(self) -> bool: ...

    def resolve_configured_model(self, configured: str) -> str | None: ...

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str: ...

    def model_digest(self, model: str) -> str | None: ...

    def is_unsuitable_model(self, model: str) -> bool: ...


@dataclass(frozen=True)
class TextLLMContext:
    """Bound once per analysis run — shared by identity and module execution."""

    client: Any
    model_name: str
    resolved_model_digest: str
    base_url: str | None = None


def is_unsuitable_text_model_name(name: str) -> bool:
    return bool(_UNSUITABLE_NAME.search(name or ""))


def is_unsuitable_text_model_info(model: ModelInfo) -> bool:
    """Reject vision/embedding/OCR models for text LLM dropdowns and binding."""
    if is_ocr_oriented_name(model.name):
        return True
    if is_unsuitable_text_model_name(model.name):
        return True
    if model.capability_known:
        caps = {c.lower() for c in model.capabilities}
        if _UNSUITABLE_CAPS.intersection(caps):
            return True
        if not caps.intersection(_TEXT_CAPS):
            return True
    family = (model.family or "").lower()
    if family in {"clip", "bert"} or "vision" in family or "embed" in family:
        return True
    return False


def suitable_text_model_names(models: Sequence[ModelInfo]) -> list[str]:
    """Names safe for text-model selectboxes (excludes vision/embedding)."""
    return [m.name for m in models if not is_unsuitable_text_model_info(m)]


@dataclass
class OllamaTextClient:
    """Text generate client reusing OCR's hardened Ollama transport."""

    base_url: str = ""
    timeout_s: float = 120.0
    max_retries: int = DEFAULT_MAX_RETRIES

    def __post_init__(self) -> None:
        raw = (self.base_url or "").strip() or default_ollama_base_url()
        self.base_url = normalize_base_url(raw)
        self._provider = OllamaVisionProvider(
            self.base_url,
            request_timeout=self.timeout_s,
            max_retries=self.max_retries,
        )

    def healthcheck(self) -> bool:
        try:
            self._provider.healthcheck()
            return True
        except ProviderError:
            return False

    def is_unsuitable_model(self, model: str) -> bool:
        if is_unsuitable_text_model_name(model):
            return True
        result = self._provider.list_models()
        for row in result.models:
            if row.name != model:
                continue
            return is_unsuitable_text_model_info(row)
        return False

    def resolve_configured_model(self, configured: str) -> str | None:
        name = (configured or "").strip()
        if not name:
            return None
        if self.is_unsuitable_model(name):
            return None
        result = self._provider.list_models()
        names = {m.name for m in result.models}
        if name in names:
            return name
        if ":" not in name:
            tagged = [n for n in names if n == name or n.startswith(name + ":")]
            if len(tagged) == 1:
                return tagged[0]
        return None

    def model_digest(self, model: str) -> str | None:
        digest, verified = self._provider.resolve_model_identity(model)
        return digest if verified and digest else None

    def generate_with_meta(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt if system is None else f"{system}\n\n{prompt}",
            "stream": False,
            "options": options or {"temperature": 0.0, "num_predict": 1024},
        }

        def once() -> dict[str, Any]:
            payload = self._provider._http_post(  # noqa: SLF001 — shared transport
                "/api/generate", body, timeout=self.timeout_s
            )
            if not isinstance(payload, dict):
                raise ProviderError(
                    "Ollama returned a non-object JSON response", code="bad_response"
                )
            return payload

        payload, attempt = call_with_retries(once, max_retries=self.max_retries)
        meta: dict[str, Any] = {"retry_count": attempt}
        for key in (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "eval_count",
            "prompt_eval_duration",
            "eval_duration",
        ):
            if key in payload and isinstance(payload[key], (int, float)):
                meta[key] = payload[key]
        return str(payload.get("response") or ""), meta

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        text, _meta = self.generate_with_meta(
            model=model, prompt=prompt, system=system, options=options
        )
        return text


@dataclass
class RecordedDoubleClient:
    """Deterministic double — same validation path as live; no network."""

    responses: dict[str, str]
    model_name: str = "recorded-double:v1"
    healthy: bool = True
    digest: str | None = None

    def healthcheck(self) -> bool:
        return self.healthy

    def is_unsuitable_model(self, model: str) -> bool:
        return is_unsuitable_text_model_name(model)

    def resolve_configured_model(self, configured: str) -> str | None:
        if not self.healthy:
            return None
        name = (configured or "").strip() or self.model_name
        if self.is_unsuitable_model(name):
            return None
        return name

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        text, _meta = self.generate_with_meta(
            model=model, prompt=prompt, system=system, options=options
        )
        return text

    def generate_with_meta(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        _ = model
        key = hashlib.sha256(f"{system or ''}\n{prompt}".encode("utf-8")).hexdigest()[:16]
        meta: dict[str, Any] = {}
        if options and isinstance(options.get("eval_count"), (int, float)):
            meta["eval_count"] = options["eval_count"]
        if key in self.responses:
            return self.responses[key], meta
        for marker, text in self.responses.items():
            if marker.startswith("contains:") and marker[9:] in prompt:
                return text, meta
        if "default" in self.responses:
            return self.responses["default"], meta
        raise RuntimeError(f"no recorded response for prompt key {key}")

    def model_digest(self, model: str) -> str | None:
        if self.digest:
            return self.digest
        return hashlib.sha256(f"recorded:{model}".encode("utf-8")).hexdigest()


_DEFAULT_CLIENT: TextLLMClient | None = None


def get_text_llm_client(*, base_url: str | None = None) -> TextLLMClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is not None:
        return _DEFAULT_CLIENT
    return OllamaTextClient(base_url=base_url or default_ollama_base_url())


def set_text_llm_client(client: TextLLMClient | None) -> None:
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = client


def ollama_base_url_for_binding(project_base_url: str | None) -> str:
    """Reachability-aware Ollama URL for LLM bind (project setting → workspace → default)."""
    from transcribe.config.facade import get_config
    from transcribe.providers.ollama import resolve_reachable_ollama_base_url

    cfg = get_config()
    return resolve_reachable_ollama_base_url(
        project_base_url,
        fallback=cfg.ocr.base_url or None,
    )


def resolve_text_model_name(
    project_text_model_name: str | None = None,
    *,
    override: str | None = None,
) -> str:
    """Resolve text model: batch/UI override → notebook → workspace OCR → LLM preference."""
    for candidate in (
        (override or "").strip(),
        (project_text_model_name or "").strip(),
    ):
        if candidate:
            return candidate
    from transcribe.config.facade import get_config

    cfg = get_config()
    for candidate in (
        (getattr(cfg.ocr, "text_model_name", None) or "").strip(),
        (getattr(cfg.llm, "text_model_preference", None) or "").strip(),
    ):
        if candidate:
            return candidate
    return ""


def bind_text_llm_context(
    *,
    text_model_name: str | None,
    base_url: str | None = None,
    client: TextLLMClient | None = None,
) -> TextLLMContext | None:
    """Resolve client/model/digest once. None → unavailable_model."""
    cli = client if client is not None else get_text_llm_client(base_url=base_url)
    if not cli.healthcheck():
        return None
    configured = (text_model_name or "").strip()
    if not configured:
        if isinstance(cli, RecordedDoubleClient):
            configured = cli.model_name
        else:
            return None
    if cli.is_unsuitable_model(configured):
        return None
    model = cli.resolve_configured_model(configured)
    if not model:
        return None
    digest = cli.model_digest(model)
    if not digest:
        return None
    return TextLLMContext(
        client=cli,
        model_name=model,
        resolved_model_digest=digest,
        base_url=getattr(cli, "base_url", base_url),
    )


def parse_json_object(text: str) -> dict[str, Any] | None:
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


def unavailable_model_result(*, message: str = "text LLM runtime unavailable") -> dict[str, Any]:
    return {
        "outcome": "skipped_not_applicable",
        "payload": {},
        "capability_reason": "unavailable_model",
        "warnings": [{"code": "unavailable_model", "message": message}],
    }
