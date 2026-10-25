"""Per-model OCR recipes: name match → frozen prompt and/or generation options.

Generic ``faithful_*`` instructions are the notebook default. Some OCR-oriented
tags (DeepSeek-OCR) ignore long instructions and emit empty text; a recipe
selects a short prompt at JobPlan freeze. Options-only lanes (glm, granite)
overlay sampler keys without replacing the notebook prompt. Custom notebook
prompts always win prompt text.

Workspace overlays live in ``data/config/ocr-model-recipes.json`` — see
``ocr_model_recipe_store`` and ``docs/runtime/ocr_model_recipes.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from transcribe.prompts import REGISTRY as OCR_REGISTRY

MATCH_MODES = frozenset({"any", "all"})
ADVICE_KINDS = frozenset({"ocr_oriented", "recommended_vlm", "general_vlm"})
RECIPE_SOURCES = frozenset({"builtin", "override", "custom"})
ALLOWED_GENERATION_OPTION_KEYS = frozenset(
    {"repeat_penalty", "stop", "temperature", "num_predict"}
)


@dataclass(frozen=True)
class OcrModelRecipe:
    recipe_id: str
    title: str
    match_tokens: tuple[str, ...]
    prompt_id: str
    warnings: tuple[str, ...]
    generation_options: dict[str, Any] = field(default_factory=dict)
    match_mode: str = "any"
    exclude_tokens: tuple[str, ...] = ()
    freeze_prompt: bool = True
    advice_kind: str = "ocr_oriented"
    enabled: bool = True
    source: str = "builtin"

    def matches(self, model_name: str) -> bool:
        lower = (model_name or "").lower()
        tokens = tuple(str(t).lower() for t in self.match_tokens if str(t).strip())
        if not tokens:
            return False
        excludes = tuple(str(t).lower() for t in self.exclude_tokens if str(t).strip())
        if any(token in lower for token in excludes):
            return False
        mode = self.match_mode if self.match_mode in MATCH_MODES else "any"
        if mode == "all":
            return all(token in lower for token in tokens)
        return any(token in lower for token in tokens)

    def as_overlay_dict(self) -> dict[str, Any]:
        """Serialize fields that belong in a workspace overlay row."""
        return {
            "recipe_id": self.recipe_id,
            "title": self.title,
            "match_tokens": list(self.match_tokens),
            "match_mode": self.match_mode,
            "exclude_tokens": list(self.exclude_tokens),
            "prompt_id": self.prompt_id,
            "freeze_prompt": self.freeze_prompt,
            "generation_options": dict(self.generation_options),
            "warnings": list(self.warnings),
            "advice_kind": self.advice_kind,
            "enabled": self.enabled,
        }


DEEPSEEK_OCR_RECIPE = OcrModelRecipe(
    recipe_id="deepseek_ocr",
    title="DeepSeek OCR",
    match_tokens=("deepseek", "ocr"),
    match_mode="all",
    exclude_tokens=("deepseek-r1",),
    prompt_id="free_ocr",
    freeze_prompt=True,
    advice_kind="ocr_oriented",
    warnings=(
        (
            "Uses a short OCR prompt (Free OCR.); long faithful instructions often "
            "return empty text (eval_count=1)."
        ),
        "A custom prompt override still wins over this recipe.",
    ),
)

# Options-only. repeat_penalty=1.2 cut overnight token-repeat aborts from
# ~58% to ~12% on black. free_ocr was tried and made fence-loops worse
# (near-100% fail). Hard pages that still echo the prompt or long-cycle
# loop are failed by truncated+rep / prompt-echo guards.
# Stop is consecutive fences, not a lone ``` — glm often opens with
# ```markdown then the page text; a single-fence stop yields eval_count=1
# empty_output.
_FENCE_LOOP_STOP = ["```\n```"]

GLM_OCR_RECIPE = OcrModelRecipe(
    recipe_id="glm_ocr",
    title="GLM OCR",
    match_tokens=("glm-ocr",),
    prompt_id="faithful_markdown",
    freeze_prompt=False,
    advice_kind="ocr_oriented",
    warnings=(
        (
            "Sends repeat_penalty=1.2 so looping generates abort less often. "
            "A few dense pages may still echo instructions — those fail as "
            "token_repeat rather than sticky successes."
        ),
        (
            "A custom prompt override still wins over this recipe; generation "
            "options from the recipe still apply. The notebook prompt is not "
            "replaced (options-only lane)."
        ),
    ),
    generation_options={"repeat_penalty": 1.2, "stop": list(_FENCE_LOOP_STOP)},
)

# Options-only: granite often hits num_predict with sticky looping prose
# ("I'm talking lily…") that used to skip as succeeded. repeat_penalty cuts
# loops earlier; truncated+repetition still fails (no sticky skip).
GRANITE_VISION_RECIPE = OcrModelRecipe(
    recipe_id="granite_vision",
    title="Granite vision",
    match_tokens=("granite3.2-vision",),
    prompt_id="faithful_markdown",
    freeze_prompt=False,
    advice_kind="recommended_vlm",
    warnings=(
        (
            "Sends repeat_penalty=1.2 so truncated looping drafts are less "
            "common. The notebook prompt is not replaced."
        ),
        (
            "A custom prompt override still wins over this recipe; generation "
            "options from the recipe still apply."
        ),
    ),
    generation_options={"repeat_penalty": 1.2, "stop": list(_FENCE_LOOP_STOP)},
)

RECIPES: tuple[OcrModelRecipe, ...] = (
    DEEPSEEK_OCR_RECIPE,
    GLM_OCR_RECIPE,
    GRANITE_VISION_RECIPE,
)


def recipe_for_model(
    model_name: str,
    *,
    runtime: Any | None = None,
    recipes: Sequence[OcrModelRecipe] | None = None,
) -> OcrModelRecipe | None:
    """Return the first enabled matching recipe, or None.

    ``recipes`` injects a pre-merged list (tests). Otherwise the workspace
    overlay is merged over builtins via ``ocr_model_recipe_store``.
    """
    if recipes is None:
        from transcribe.services.ocr_model_recipe_store import load_effective_recipes

        recipes = load_effective_recipes(runtime)
    for recipe in recipes:
        if recipe.enabled and recipe.matches(model_name):
            return recipe
    return None


def recipe_prompt(recipe: OcrModelRecipe) -> tuple[str, str, str]:
    """Return ``(prompt_id, version, text)`` from the builtin OCR registry."""
    tmpl = OCR_REGISTRY.get(recipe.prompt_id)
    if tmpl is None:
        return recipe.prompt_id, "1", "Free OCR."
    return tmpl.prompt_id, tmpl.version, tmpl.body
