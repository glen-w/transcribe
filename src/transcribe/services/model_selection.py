"""Filter Ollama discovery for Transcribe model pickers.

Vision/OCR selectors list OCR-appropriate VLMs only. Text selectors use
:class:`transcribe.analysis.llm_runtime` (completion LLMs, not vision/embed).
"""

from __future__ import annotations

from collections.abc import Sequence

from transcribe.providers.base import ModelInfo
from transcribe.providers.ollama import is_mllama_vision_model
from transcribe.services.model_advice import (
    is_general_vlm_name,
    is_ocr_oriented_name,
    is_recommended_vlm_name,
    is_thinking_ocr_risk_name,
)

_VISION_CAPS = frozenset({"vision", "image"})


def _ocr_vision_sort_key(model: ModelInfo) -> tuple[int, str]:
    name = model.name
    if is_ocr_oriented_name(name):
        tier = 0
    elif is_recommended_vlm_name(name):
        tier = 1
    elif is_general_vlm_name(name):
        tier = 2
    else:
        tier = 3
    return (tier, name.lower())


def is_suitable_ocr_vision_model_info(model: ModelInfo) -> bool:
    """True when a tag belongs in OCR / vision pickers (not text-only or thinking)."""
    name = model.name
    if is_thinking_ocr_risk_name(name) or is_mllama_vision_model(name):
        return False
    if is_ocr_oriented_name(name):
        return True
    if model.capability_known:
        caps = {c.lower() for c in model.capabilities}
        return bool(caps.intersection(_VISION_CAPS))
    lower = name.lower()
    return any(
        token in lower
        for token in ("vision", "llava", "vl", "ocr", "minicpm-v", "moondream")
    )


def is_unsuitable_ocr_vision_model_name(name: str) -> bool:
    """Name-only guard when discovery metadata is unavailable."""
    text = (name or "").strip()
    if not text:
        return True
    if is_thinking_ocr_risk_name(text) or is_mllama_vision_model(text):
        return True
    if is_ocr_oriented_name(text):
        return False
    lower = text.lower()
    if any(token in lower for token in ("vision", "llava", "vl", "ocr", "minicpm-v", "moondream")):
        return False
    return True


def suitable_ocr_vision_models(models: Sequence[ModelInfo]) -> list[ModelInfo]:
    """OCR-appropriate vision models, OCR-oriented tags first."""
    return sorted(
        (m for m in models if is_suitable_ocr_vision_model_info(m)),
        key=_ocr_vision_sort_key,
    )


def suitable_ocr_vision_model_names(models: Sequence[ModelInfo]) -> list[str]:
    return [m.name for m in suitable_ocr_vision_models(models)]


def validate_ocr_vision_model(provider: object, model_name: str) -> None:
    """Reject OCR runs with text-only, thinking, or known-broken vision tags."""
    from transcribe.errors import ProviderError

    text = (model_name or "").strip()
    if not text:
        raise ProviderError("No model selected", code="model_missing")
    list_models = getattr(provider, "list_models", None)
    if callable(list_models):
        result = list_models()
        by_name = {m.name: m for m in result.models}
        info = by_name.get(text)
        if info is not None:
            if not is_suitable_ocr_vision_model_info(info):
                raise ProviderError(
                    f"`{text}` is not suitable for OCR vision transcription. "
                    "Choose an OCR-oriented or recommended vision model "
                    "(for example glm-ocr, deepseek-ocr, granite3.2-vision, qwen2.5vl).",
                    code="model_unsuitable",
                )
            return
    if is_thinking_ocr_risk_name(text) or is_mllama_vision_model(text):
        raise ProviderError(
            f"`{text}` is not suitable for OCR vision transcription. "
            "Choose an OCR-oriented or recommended vision model.",
            code="model_unsuitable",
        )
