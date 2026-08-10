"""Model routing for detection runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcribe.detection.definition import DetectorDefinition, ModelMode
from transcribe.prompt_engine.definition import InputMode, PromptDefinition


@dataclass(frozen=True)
class ResolvedModelRoute:
    input_mode: InputMode
    model_name: str
    model_digest: str | None
    text_available: bool
    vision_available: bool


def resolve_model_route(
    detector: DetectorDefinition,
    prompt: PromptDefinition,
    *,
    text_ctx: Any | None,
    vision_ctx: Any | None,
    page_has_text: bool,
) -> ResolvedModelRoute | None:
    mode = detector.input_mode
    text_ok = text_ctx is not None
    vision_ok = vision_ctx is not None

    if mode == ModelMode.TEXT:
        if not text_ok:
            return None
        digest = getattr(text_ctx, "resolved_model_digest", None)
        return ResolvedModelRoute(
            input_mode=InputMode.TEXT,
            model_name=text_ctx.model_name,
            model_digest=digest,
            text_available=True,
            vision_available=vision_ok,
        )

    if mode == ModelMode.VISION:
        if not vision_ok:
            return None
        digest = getattr(vision_ctx, "resolved_model_digest", None)
        return ResolvedModelRoute(
            input_mode=InputMode.VISION,
            model_name=vision_ctx.model_name,
            model_digest=digest,
            text_available=text_ok,
            vision_available=True,
        )

    # AUTO: prefer text when OCR available and prompt allows
    if page_has_text and text_ok and prompt.input_mode in (InputMode.TEXT, InputMode.HYBRID):
        digest = getattr(text_ctx, "resolved_model_digest", None)
        return ResolvedModelRoute(
            input_mode=InputMode.TEXT,
            model_name=text_ctx.model_name,
            model_digest=digest,
            text_available=True,
            vision_available=vision_ok,
        )
    if vision_ok and prompt.input_mode in (InputMode.VISION, InputMode.HYBRID):
        digest = getattr(vision_ctx, "resolved_model_digest", None)
        return ResolvedModelRoute(
            input_mode=InputMode.VISION,
            model_name=vision_ctx.model_name,
            model_digest=digest,
            text_available=text_ok,
            vision_available=True,
        )
    return None
