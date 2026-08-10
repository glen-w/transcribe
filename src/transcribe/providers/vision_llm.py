"""Vision LLM context for detection (non-OCR inference)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcribe.errors import ProviderError
from transcribe.providers.base import ModelInfo
from transcribe.providers.ollama import (
    DEFAULT_MAX_RETRIES,
    OllamaVisionProvider,
    call_with_retries,
    normalize_base_url,
)
from transcribe.runtime_paths import default_ollama_base_url


def is_suitable_vision_model_info(model: ModelInfo) -> bool:
    if model.capability_known and "vision" in {c.lower() for c in model.capabilities}:
        return True
    family = (model.family or "").lower()
    return "vision" in family or "llava" in model.name.lower()


@dataclass(frozen=True)
class VisionLLMContext:
    client: Any
    model_name: str
    resolved_model_digest: str
    base_url: str | None = None


class OllamaVisionLLMClient:
    """Vision generate client for detection prompts."""

    def __init__(
        self,
        *,
        base_url: str = "",
        timeout_s: float = 180.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        raw = (base_url or "").strip() or default_ollama_base_url()
        self.base_url = normalize_base_url(raw)
        self.timeout_s = timeout_s
        self.max_retries = max_retries
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

    def resolve_configured_model(self, configured: str) -> str | None:
        name = (configured or "").strip()
        if not name:
            return None
        result = self._provider.list_vision_models()
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

    def analyze_images(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        image_bytes_list: list[bytes],
        options: dict[str, Any] | None = None,
    ) -> str:
        if not image_bytes_list:
            raise ProviderError("no images provided", code="invalid_input")
        # Ollama accepts one image per call; for multi-page windows use first page in v1
        # or concatenate via multiple calls — use first image for v1 simplicity
        result = self._provider.transcribe_image(
            model=model,
            image_bytes=image_bytes_list[0],
            prompt=prompt if system is None else f"{system}\n\n{prompt}",
            options=options or {"temperature": 0.0, "num_predict": 1024},
        )
        return result.text


@dataclass
class RecordedVisionDoubleClient:
    responses: dict[str, str]
    model_name: str = "recorded-vision-double:v1"
    healthy: bool = True
    digest: str | None = "recorded-vision-digest"

    def healthcheck(self) -> bool:
        return self.healthy

    def resolve_configured_model(self, configured: str) -> str | None:
        if not self.healthy:
            return None
        return (configured or "").strip() or self.model_name

    def model_digest(self, model: str) -> str | None:
        return self.digest

    def analyze_images(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        image_bytes_list: list[bytes] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        _ = model, system, image_bytes_list, options
        key = prompt[:120]
        if key in self.responses:
            return self.responses[key]
        for k, v in self.responses.items():
            if k in prompt:
                return v
        return self.responses.get("*", "{}")


def bind_vision_llm_context(
    *,
    model_name: str,
    base_url: str | None = None,
    client: Any | None = None,
) -> VisionLLMContext | None:
    if client is not None:
        digest = getattr(client, "digest", None) or client.model_digest(model_name)
        return VisionLLMContext(
            client=client,
            model_name=model_name,
            resolved_model_digest=digest or "unverified",
            base_url=base_url,
        )
    ollama = OllamaVisionLLMClient(base_url=base_url or "")
    if not ollama.healthcheck():
        return None
    resolved = ollama.resolve_configured_model(model_name)
    if not resolved:
        return None
    digest = ollama.model_digest(resolved)
    if not digest:
        return None
    return VisionLLMContext(
        client=ollama,
        model_name=resolved,
        resolved_model_digest=digest,
        base_url=ollama.base_url,
    )
