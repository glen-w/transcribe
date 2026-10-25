# OCR model recipes

Everyday users: pick a tag from the [model matrix](ocr_model_matrix.md). This
page is the recipe registry — shipped lanes plus how to overlay your own.

Some Ollama vision tags do not follow generic VLM “extract all text…”
instructions, or they loop unless generation options are patched. Transcribe
keeps a small **recipe registry** so those tags get a frozen prompt and/or a
generation-option overlay at job start, without a different HTTP template.

**Settings:** **Settings → Models → OCR model recipes** (enable, disable, add,
edit). Stored at `data/config/ocr-model-recipes.json` — not notebook settings.
**Contract:** [ocr-model-recipes.md](../contracts/ocr-model-recipes.md)  
**Advice UI:** [`model_advice.py`](../../src/transcribe/services/model_advice.py)  
**Applied in:** `JobCoordinator._build_plan` (single-model, Review re-run, and
each multipass vision phase)

## Precedence

1. Non-empty notebook **custom prompt** always wins prompt text
2. Else if an enabled recipe matches and `freeze_prompt` is on → recipe
   `prompt_id` (builtin or Prompt Hub override of that id)
3. Else notebook `prompt_id` (`faithful_markdown` / `faithful_text`)

Recipe **generation options** still overlay whenever a recipe matches
(including after a custom prompt). Choice is frozen into `JobPlan` (prompt
text / SHA / options). Mid-job Settings changes apply to the **next** job only.

Changing `repeat_penalty`, `stop`, `num_predict`, or a frozen prompt changes
the skip fingerprint, so succeeded pages for that model re-run once.

## Shipped lane: DeepSeek-OCR

| | |
|--|--|
| Match | `deepseek` **and** `ocr` in the tag; exclude `deepseek-r1` |
| Prompt | Frozen `free_ocr` — body `Free OCR.` |
| Why | Long `faithful_*` instructions often return **empty text** with `eval_count=1`; empty output is **failed** (`empty_output`). |

Re-run DeepSeek after the prompt freeze so fingerprints do not skip the old
empty attempts.

## Shipped lane: GLM-OCR

| | |
|--|--|
| Match | `glm-ocr` in the tag |
| Prompt | **Not frozen** — notebook `faithful_markdown` / `faithful_text` stays |
| Options | `repeat_penalty=1.2`, `stop=["```\\n```"]` (consecutive fences; a lone ` ``` ` would empty pages that open with ` ```markdown `) |
| Why | Host Modelfile only sets `temperature 0`. llama.cpp aborts many dense pages with `token repeat limit reached`. Options-only dropped fail rate ~58% → ~12% on `black`. Evidence: [ocr_generate_failures.md](../reviews/ocr_generate_failures.md). |

A custom notebook prompt still wins. Recipe options still apply.

## Shipped lane: Granite vision

| | |
|--|--|
| Match | `granite3.2-vision` in the tag (not a bare `granite3.2` text tag) |
| Prompt | **Not frozen** |
| Options | `repeat_penalty=1.2`, `stop=["```\\n```"]` |
| Advice | Recommended VLM (not OCR-oriented) |
| Why | Dense pages often hit `num_predict` with looping prose that used to store as `succeeded` and skip forever. Live jobs fail truncated+repetition; the recipe reduces how often the loop starts. |

Do **not** set `repeat_penalty` on qwen tags — that would bust their skip
hashes without evidence they need it.

## What recipes cannot fix

| Failure | Why a recipe does not help |
|---------|----------------------------|
| **Thinking** tags (`gemma4`, `qwen3-vl`, `gpt-oss`, `deepseek-r1`) empty OCR | Hidden reasoning burns `num_predict`; picker exclusion + advice, not a prompt patch |
| **llama3.2-vision** `mllama` load fail | Architecture; picker hide + `model_load` circuit |
| Timeouts on general VLMs (`llava`, …) | Use an OCR-oriented first pass |
| Chatty wrappers (`devstral`, …) / `got-ocr` / `paddleocr` / `nougat` / `olmocr` / `minicpm-v` | Advice-only until a measured fail mode exists |

Add a custom overlay only when you have evidence (token-repeat rate, empty
`eval_count=1`, a required short prompt).

## Configure without editing Python

**Settings → Models → OCR model recipes:**

- Toggle **On** to disable a shipped lane
- **Add or edit recipe overlay** — same `recipe_id` patches a builtin; a new id
  is custom (tried first)
- **Revert** drops a builtin overlay; **Remove** drops a custom row
- **Reset overlay** (only if the JSON is unreadable) writes an empty valid file

Power users may edit `data/config/ocr-model-recipes.json` directly. Schema and
merge rules: [ocr-model-recipes.md](../contracts/ocr-model-recipes.md).

Example — raise glm `repeat_penalty` without touching the prompt:

```json
{
  "format": "transcribe.ocr-model-recipes",
  "schema_version": 1,
  "recipes": [
    {
      "recipe_id": "glm_ocr",
      "generation_options": { "repeat_penalty": 1.35 }
    }
  ]
}
```

## How to add a shipped lane (maintainers)

1. Add a builtin prompt in [`src/transcribe/prompts/__init__.py`](../../src/transcribe/prompts/__init__.py) if the body is not already in the OCR catalogue.
2. Append an `OcrModelRecipe` in `ocr_model_recipes.py`: `recipe_id`, match fields, `freeze_prompt`, `prompt_id`, `advice_kind`, `warnings`, optional `generation_options`.
3. Unit-test `recipe_for_model("your-tag:latest")` and `_build_plan`; add advice coverage.
4. One-line note here and in [known_limitations.md](../known_limitations.md) if the tag has a known failure mode.

Do **not** special-case Ollama `/api/generate` (prompt + `images` + `options`
stays the same). Do **not** put recipes only in the HTTP client — fingerprint
and provenance need plan-owned prompt text.
