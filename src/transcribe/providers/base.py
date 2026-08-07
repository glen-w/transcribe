"""Vision OCR provider protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ModelInfo:
    name: str
    digest: str | None
    size: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    capabilities: list[str] = field(default_factory=list)
    capability_known: bool = False


@dataclass
class ProviderResult:
    text: str
    model: str
    model_digest: str | None
    model_identity_verified: bool
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    models: list[ModelInfo]
    error: str | None = None


class VisionOCRProvider(Protocol):
    provider_id: str

    def healthcheck(self) -> None: ...

    def list_vision_models(self, *, refresh: bool = False) -> DiscoveryResult: ...

    def list_models(self, *, refresh: bool = False) -> DiscoveryResult: ...

    def transcribe_image(
        self,
        *,
        model: str,
        prompt: str,
        image_bytes: bytes,
        options: dict[str, Any],
    ) -> ProviderResult: ...
