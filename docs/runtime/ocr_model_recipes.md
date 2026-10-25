# OCR model recipes

Everyday users: pick a tag from the [model matrix](ocr_model_matrix.md). This page is the recipe registry for tags that ignore a generic “extract all text” prompt.

Some Ollama vision tags do not follow generic VLM “extract all text…” instructions — or they loop unless generation options are patched. Transcribe keeps a small **recipe registry** so those tags get a frozen prompt and/or generation-option overlay at job start, without a different HTTP template.

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

## Shipped lane: GLM-OCR

| | |
|--|--|
| Match | `glm-ocr` in the tag |
| Prompt | `faithful_markdown` (unchanged from the notebook default) |
| Options | `repeat_penalty=1.2` overlaid on notebook generation options |
| Why | Host Modelfile only sets `temperature 0`. llama.cpp then aborts many dense pages with `prediction aborted, token repeat limit reached`. Transcribe classified that as retriable `http_error` and retried the same payload three times. Evidence: [ocr_generate_failures.md](../reviews/ocr_generate_failures.md). |

A custom notebook prompt still wins. Recipe `generation_options` still apply. Adding `repeat_penalty` changes the glm skip fingerprint so existing glm successes re-run once, then skip if model identity is verified (`glm-ocr` matches `glm-ocr:latest`).

Do **not** set `repeat_penalty` on other vision tags — that would bust qwen/granite skip hashes.

## How to add a lane

1. Add a builtin prompt in [`src/transcribe/prompts/__init__.py`](../../src/transcribe/prompts/__init__.py) if the body is not already in the OCR catalogue (Prompt Hub OCR family picks it up via `OCR_REGISTRY`).
2. Append an `OcrModelRecipe` in `ocr_model_recipes.py`: `recipe_id`, `match_tokens`, `prompt_id`, `warnings`, optional `generation_options`.
3. Unit-test `recipe_for_model("your-tag:latest")` and `_build_plan` prompt freeze; add advice coverage if the tag should show as OCR-oriented.
4. One-line note here and in [known_limitations.md](../known_limitations.md) if the tag has a known failure mode.

Do **not** special-case Ollama `/api/generate` (prompt + `images` + `options` stays the same). Do **not** put recipes only in the HTTP client — fingerprint and provenance need plan-owned prompt text.
