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
    "deepseek-ocr",
)
# Tags that often burn num_predict in hidden "thinking" and return empty OCR text.
_THINKING_OCR_RISK_TOKENS = (
    "gemma4",
    "gpt-oss",
    "deepseek-r1",
    "qwen3-vl",
    "qwen3.6",
)
# Vision tags that probe well on handwriting in local tests (not OCR-specialized).
_RECOMMENDED_VLM_TOKENS = (
    "granite3.2-vision",
    "qwen2.5vl",
    "minicpm-v",
)


@dataclass(frozen=True)
class ModelAdvice:
    kind: str  # general_vlm | ocr_oriented | text | unknown
    title: str
    warnings: tuple[str, ...]
    use_case: str = ""  # first_ocr | quality | text | ""


def is_general_vlm_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _GENERAL_VLM_TOKENS)


def is_ocr_oriented_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _OCR_TOKENS)


def is_thinking_ocr_risk_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _THINKING_OCR_RISK_TOKENS)


def is_recommended_vlm_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(token in lower for token in _RECOMMENDED_VLM_TOKENS)


def advise_model(name: str, *, role: str = "vision") -> ModelAdvice:
    """Return user-facing caveats for a selected model name."""
    from transcribe.services.ocr_model_recipes import recipe_for_model

    if role == "text":
        return ModelAdvice(
            kind="text",
            title="Text model",
            use_case="text",
            warnings=(
                "Needs a text model for Analyse LLM modules, rank/composite, and optional OCR cleanup.",
                "Cleanup adds a second Ollama call per succeeded page.",
            ),
        )
    if is_thinking_ocr_risk_name(name):
        return ModelAdvice(
            kind="thinking_risk",
            title="Thinking vision model (high empty-OCR risk)",
            use_case="quality",
            warnings=(
                "Thinking models often burn the full num_predict budget internally "
                "and return empty text — Transcribe marks that as failed (empty_output).",
                "Do not use for first OCR on a notebook. Prefer glm-ocr, deepseek-ocr, "
                "granite3.2-vision, or qwen2.5vl.",
            ),
        )
    recipe = recipe_for_model(name)
    if recipe is not None:
        return ModelAdvice(
            kind="ocr_oriented",
            title=f"OCR-oriented vision model · {recipe.title} recipe",
            use_case="first_ocr",
            warnings=recipe.warnings,
        )
    if is_ocr_oriented_name(name):
        return ModelAdvice(
            kind="ocr_oriented",
            title="OCR-oriented vision model",
            use_case="first_ocr",
            warnings=(
                "Good first OCR choice for handwriting and dense scans.",
                "Looping or very long output is capped by num_predict; dense pages can still take minutes.",
            ),
        )
    if is_recommended_vlm_name(name):
        return ModelAdvice(
            kind="recommended_vlm",
            title="Recommended general vision model for OCR",
            use_case="first_ocr",
            warnings=(
                "Probed reliably on handwriting fixtures; still slower than tiny OCR tags.",
                "Good first compare model when glm-ocr / deepseek-ocr are unavailable.",
            ),
        )
    if is_general_vlm_name(name):
        warnings: list[str] = [
            "Vision-capable does not mean good handwriting OCR.",
            "Better as a later compare/quality pass than a first OCR model.",
            "General VLMs can hang or time out on dense notebook scans.",
        ]
        lower = (name or "").lower()
        if "llama3.2-vision" in lower:
            warnings.insert(
                0,
                "Llama 3.2 Vision is broken on Ollama 0.30+ (mllama unsupported). "
                "Prefer granite3.2-vision, minicpm-v, or qwen2.5vl for first OCR.",
            )
        return ModelAdvice(
            kind="general_vlm",
            title="General vision-language model",
            use_case="quality",
            warnings=tuple(warnings),
        )
    return ModelAdvice(
        kind="unknown",
        title="Vision model",
        use_case="quality",
        warnings=(
            "A listed vision capability does not guarantee OCR quality on handwriting.",
            "Prefer an OCR-oriented tag for a first transcription run when available.",
        ),
    )


def use_case_label(advice: ModelAdvice) -> str | None:
    """Short product framing for first OCR vs quality vs text needs."""
    if advice.use_case == "first_ocr":
        return "Suggested for first OCR"
    if advice.use_case == "quality":
        return "Better as a quality / compare pass"
    if advice.use_case == "text":
        return "Needs a text model for Analyse LLM modules"
    return None
