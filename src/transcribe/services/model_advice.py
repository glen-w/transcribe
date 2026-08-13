"""Advisory copy for Ollama models shown in Transcribe pickers.

Heuristics on name/family only — never a hard block. Vision capability does
not mean a model is suitable for handwriting OCR.
"""

from __future__ import annotations

from dataclasses import dataclass

_GENERAL_VLM_TOKENS = (
    "llava",
    "bakllava",
    "moondream",
    "minicpm-v",
    "llama3.2-vision",
)
_OCR_TOKENS = (
    "glm-ocr",
    "got-ocr",
    "gotocr",
    "paddleocr",
    "nougat",
    "olmocr",
)


@dataclass(frozen=True)
class ModelAdvice:
    kind: str  # general_vlm | ocr_oriented | text | unknown
    title: str
    warnings: tuple[str, ...]


def is_general_vlm_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _GENERAL_VLM_TOKENS)


def is_ocr_oriented_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _OCR_TOKENS)


def advise_model(name: str, *, role: str = "vision") -> ModelAdvice:
    """Return user-facing caveats for a selected model name."""
    if role == "text":
        return ModelAdvice(
            kind="text",
            title="Text model",
            warnings=(
                "Used for analysis, rank/composite, and optional OCR cleanup.",
                "Cleanup adds a second Ollama call per succeeded page.",
            ),
        )
    if is_ocr_oriented_name(name):
        return ModelAdvice(
            kind="ocr_oriented",
            title="OCR-oriented vision model",
            warnings=(
                "Better fit for page transcription than a general vision-language model.",
                "Looping or very long output is capped by num_predict; dense pages can still take minutes.",
            ),
        )
    if is_general_vlm_name(name):
        return ModelAdvice(
            kind="general_vlm",
            title="General vision-language model",
            warnings=(
                "Vision-capable does not mean good handwriting OCR.",
                "General VLMs can hang or time out on dense notebook scans.",
                "Do not put this model first when comparing — prefer an OCR-oriented model.",
            ),
        )
    return ModelAdvice(
        kind="unknown",
        title="Vision model",
        warnings=(
            "A listed vision capability does not guarantee OCR quality on handwriting.",
        ),
    )
