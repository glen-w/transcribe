from __future__ import annotations

from .base import DiscoveryResult, ModelInfo, ProviderResult, VisionOCRProvider
from .ollama import (
    DEFAULT_MAX_RETRIES,
    OllamaVisionProvider,
    call_with_retries,
    invalidate_discovery_cache,
    is_local_machine_host,
    is_loopback_host,
    normalize_base_url,
)

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DiscoveryResult",
    "ModelInfo",
    "OllamaVisionProvider",
    "ProviderResult",
    "VisionOCRProvider",
    "call_with_retries",
    "invalidate_discovery_cache",
    "is_local_machine_host",
    "is_loopback_host",
    "normalize_base_url",
]
