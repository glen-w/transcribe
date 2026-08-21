"""Per-model OCR recipes: name match → frozen prompt (and optional options).

Generic ``faithful_*`` instructions are the notebook default. Some OCR-oriented
tags (DeepSeek-OCR) ignore long instructions and emit empty text; a recipe
selects a short prompt at JobPlan freeze. Custom notebook prompts always win.

How to add a lane: append an ``OcrModelRecipe`` (tokens, prompt_id, warnings),
cover it in tests, and document it in ``docs/runtime/ocr_model_recipes.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from transcribe.prompts import REGISTRY as OCR_REGISTRY


@dataclass(frozen=True)
class OcrModelRecipe:
    recipe_id: str
    title: str
    match_tokens: tuple[str, ...]
    prompt_id: str
    warnings: tuple[str, ...]
    generation_options: dict[str, Any] = field(default_factory=dict)

    def matches(self, model_name: str) -> bool:
        lower = (model_name or "").lower()
        return any(token in lower for token in self.match_tokens)


DEEPSEEK_OCR_RECIPE = OcrModelRecipe(
    recipe_id="deepseek_ocr",
    title="DeepSeek OCR",
    match_tokens=("deepseek-ocr",),
    prompt_id="free_ocr",
    warnings=(
        "Uses a short OCR prompt (Free OCR.); long faithful instructions often "
        "return empty text (eval_count=1).",
        "A custom prompt override still wins over this recipe.",
    ),
)

RECIPES: tuple[OcrModelRecipe, ...] = (DEEPSEEK_OCR_RECIPE,)


def recipe_for_model(model_name: str) -> OcrModelRecipe | None:
    """Return the first matching recipe, or None."""
    lower = (model_name or "").lower()
    for recipe in RECIPES:
        if recipe.matches(model_name):
            return recipe
    if "deepseek" in lower and "ocr" in lower:
        return DEEPSEEK_OCR_RECIPE
    return None


def recipe_prompt(recipe: OcrModelRecipe) -> tuple[str, str, str]:
    """Return ``(prompt_id, version, text)`` from the builtin OCR registry."""
    tmpl = OCR_REGISTRY.get(recipe.prompt_id)
    if tmpl is None:
        return recipe.prompt_id, "1", "Free OCR."
    return tmpl.prompt_id, tmpl.version, tmpl.body
