from __future__ import annotations

from .base import DiscoveryResult, ModelInfo, ProviderResult, VisionOCRProvider
from .ollama import (
    OllamaVisionProvider,
    invalidate_discovery_cache,
    is_local_machine_host,
    is_loopback_host,
    normalize_base_url,
)

__all__ = [
    "DiscoveryResult",
    "ModelInfo",
    "OllamaVisionProvider",
    "ProviderResult",
    "VisionOCRProvider",
    "invalidate_discovery_cache",
    "is_local_machine_host",
    "is_loopback_host",
    "normalize_base_url",
]
