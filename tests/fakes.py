from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.errors import ProviderError
from transcribe.providers.base import DiscoveryResult, ModelInfo, ProviderResult


@dataclass
class FakeVisionOCRProvider:
    provider_id: str = "fake"
    text_by_call: list[str] = field(default_factory=list)
    default_text: str = "hello notebook"
    digest: str | None = "digest-aaa"
    verified: bool = True
    fail_times: int = 0
    calls: int = 0
    last_options: dict[str, Any] = field(default_factory=dict)
    last_prompt: str = ""
    fail_codes: list[str] = field(default_factory=list)
    probe_fail_code: str | None = None
    models: list[ModelInfo] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.models:
            self.models = [
                ModelInfo(
                    name="fake-vision",
                    digest=self.digest,
                    capabilities=["vision", "completion"],
                    capability_known=True,
                )
            ]

    def healthcheck(self) -> None:
        return None

    def list_vision_models(self, *, refresh: bool = False) -> DiscoveryResult:
        return DiscoveryResult(models=[m for m in self.models if "vision" in m.capabilities])

    def list_models(self, *, refresh: bool = False) -> DiscoveryResult:
        return DiscoveryResult(models=list(self.models))

    def resolve_model_identity(self, model_name: str) -> tuple[str | None, bool]:
        for m in self.models:
            if m.name == model_name:
                if m.digest and self.verified:
                    return m.digest, True
                return m.digest, False
        if self.digest and self.verified:
            return self.digest, True
        return self.digest, False

    def probe_vision_model_load(self, *, model: str) -> None:
        if self.probe_fail_code:
            self._raise_fail(self.probe_fail_code)

    def _raise_fail(self, code: str) -> None:
        message = code
        if code == "model_load":
            message = (
                "Ollama cannot load this vision model (architecture unsupported). "
                "Try another vision model."
            )
        raise ProviderError(
            message,
            retriable=code not in {"timeout", "model_missing", "model_load"},
            code=code,
        )

    def transcribe_image(
        self,
        *,
        model: str,
        prompt: str,
        image_bytes: bytes,
        options: dict[str, Any],
    ) -> ProviderResult:
        self.calls += 1
        self.last_options = dict(options or {})
        self.last_prompt = prompt
        if self.fail_codes:
            code = self.fail_codes.pop(0)
            if code:
                self._raise_fail(code)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ProviderError("transient", retriable=True, code="timeout")
        text = (
            self.text_by_call.pop(0)
            if self.text_by_call
            else f"{self.default_text}:{len(image_bytes)}"
        )
        return ProviderResult(
            text=text,
            model=model,
            model_digest=self.digest,
            model_identity_verified=self.verified,
            provider_metadata={"retry_count": 0, "total_duration": 12},
        )
