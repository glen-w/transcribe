Type: GUIDE
Authority: how to add a per-model OCR prompt/options lane — does not redefine page-result or prompt-definition contracts

# OCR model recipes

Some Ollama vision tags do not follow generic VLM “extract all text…” instructions. Transcribe keeps a small **recipe registry** so those tags get a frozen prompt (and optional generation-option patches) at job start, without a different HTTP template.

**Code:** [`src/transcribe/services/ocr_model_recipes.py`](../../src/transcribe/services/ocr_model_recipes.py)  
**Advice UI:** [`src/transcribe/services/model_advice.py`](../../src/transcribe/services/model_advice.py) (same name-match; recipes show as OCR-oriented)  
**Applied in:** `JobCoordinator._build_plan` (single-model, Review re-run, and each multipass vision phase)

## Precedence

1. Non-empty notebook **custom prompt** always wins
2. Else if a recipe matches the resolved model name → recipe `prompt_id` (builtin or workspace override of that id)
3. Else notebook `prompt_id` (`faithful_markdown` / `faithful_text`)

Recipe choice is frozen into `JobPlan.prompt_text` / `prompt_sha256` (fingerprint skip uses that hash). Mid-job settings changes still apply to the **next** job only.

## Shipped lane: DeepSeek-OCR

| | |
|--|--|
| Match | `deepseek-ocr` in the tag, or both `deepseek` and `ocr` |
| Prompt | `free_ocr` — body `Free OCR.` |
| Why | Long `faithful_*` instructions often return **empty text** with `eval_count=1`; the job used to mark that as succeeded and overwrite a good prior reading. Empty output is now **failed** (`empty_output`). |

Re-run DeepSeek after this change so fingerprints (new prompt) do not skip the old empty attempts.

## How to add a lane

1. Add a builtin prompt in [`src/transcribe/prompts/__init__.py`](../../src/transcribe/prompts/__init__.py) if the body is not already in the OCR catalogue (Prompt Hub OCR family picks it up via `OCR_REGISTRY`).
2. Append an `OcrModelRecipe` in `ocr_model_recipes.py`: `recipe_id`, `match_tokens`, `prompt_id`, `warnings`, optional `generation_options`.
3. Unit-test `recipe_for_model("your-tag:latest")` and `_build_plan` prompt freeze; add advice coverage if the tag should show as OCR-oriented.
4. One-line note here and in [known_limitations.md](../known_limitations.md) if the tag has a known failure mode.

Do **not** special-case Ollama `/api/generate` (prompt + `images` + `options` stays the same). Do **not** put recipes only in the HTTP client — fingerprint and provenance need plan-owned prompt text.
