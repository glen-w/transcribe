Type: GUIDE
Authority: local probe results for OCR model pickers — does not redefine page-result contracts

# OCR model matrix (local probes)

Live probe of installed Ollama vision tags on `tests/fixtures/mini_page.png` plus spot checks on the **green** notebook (handwriting). Re-run after pulling new models:

```bash
PYTHONPATH=src python scripts/probe_ollama_vision_models.py --json .test_outputs/model_probe_results.json
```

Probe uses the same prompt lane as a real job (`faithful_markdown`, or a model recipe such as DeepSeek-OCR `free_ocr`). **Last run:** 2026-08-23 on Ollama against `http://localhost:11434`.

Picker lists are filtered in the UI and enforced at job start — see [model_selection.py](../../src/transcribe/services/model_selection.py).

## Picker policy (shipped)

| Picker | Shows | Excludes |
|--------|-------|----------|
| **Vision / OCR** | OCR-oriented tags, recommended VLMs (`granite3.2-vision`, `qwen2.5vl`, …), general VLMs for compare | Thinking models (`gemma4`, `qwen3-vl`, …), text-only LLMs, `llama3.2-vision` (mllama) |
| **Text analysis / cleanup** | Completion/chat LLMs | Vision, embedding, OCR-oriented tags |

## Why your job failed (`empty_output`)

The **green** notebook job (`7ce4752e…`) used **`gemma4:26b`**. That tag is a **thinking** vision model: on many dense pages it spends the full `num_predict` budget (4096) internally and returns **no visible text**. Transcribe correctly marks that as **failed** (`empty_output` / “model returned no text”) — not a timeout or Ollama crash.

Spot checks on green pages (same `faithful_markdown` prompt):

| Page | gemma4:26b | glm-ocr | granite3.2-vision |
|------|------------|---------|-------------------|
| green 130.jpg | text (778 chars) | text | text |
| green 131.jpg | **empty** (eval=4096) | text | text |
| green 156.jpg | **empty** (eval=4096) | text | text |
| green 157.jpg | **empty** (eval=4096) | text | text |

**Fix:** In **Workflow → Transcribe** (or notebook settings), switch to an OCR-oriented or recommended tag below, then re-run (use **Force** if fingerprints skip pages).

## Mini-page probe summary

| Model | Load | OCR on fixture | Notes |
|-------|------|----------------|-------|
| **glm-ocr:latest** | ok | ok | Best OCR-oriented pick; may loop on long output (watch `truncated`) |
| **deepseek-ocr:latest** | ok | ok | Uses `free_ocr` recipe — do not override with long faithful prompts |
| **granite3.2-vision:latest** | ok | ok | Fast, reliable general VLM for handwriting |
| **qwen2.5vl:3b** / **7b** | ok | ok | Good size/quality trade-off |
| **minicpm-v:8b** | ok | ok | Small general VLM; compare pass |
| **gemma3:4b** / **12b** | ok | ok | Non-thinking Gemma vision |
| **llava:7b** | ok | ok | General VLM — compare pass only |
| **devstral-small-2:latest** | ok | ok | Large; chatty wrapper text |
| **qwen3-vl:4b** | ok | ok | Thinking; slower |
| **qwen3-vl:8b** | ok | **empty** | Thinking burned 512 tokens with no text on fixture |
| **qwen3.6:27b** | ok | ok | Thinking family — risky on dense pages |
| **gemma4:26b** | ok | ok on fixture | **High empty-OCR risk on real notebook pages** (see above) |
| **llama3.2-vision:11b** | **fail** | error | `unknown model architecture: mllama` on Ollama 0.30+ |

Tags without `vision` in Ollama discovery are omitted from vision pickers unless they match OCR-oriented name heuristics. A previously saved unsuitable tag (for example `gemma4`) is warned but not listed — pick a model from the filtered list and save settings.

## Recommended first OCR picks

1. **OCR-oriented:** `glm-ocr`, `deepseek-ocr` (recipe applies automatically)
2. **General vision (probed):** `granite3.2-vision`, `qwen2.5vl:7b` (or `:3b` for speed)
3. **Compare / second pass:** `minicpm-v`, `llava` — after a solid first model

## Avoid for first OCR

| Tag family | Why |
|------------|-----|
| **Thinking** (`gemma4`, `gpt-oss`, `qwen3-vl`, `qwen3.6`, `deepseek-r1`) | Often `empty_output` when thinking consumes `num_predict` |
| **llama3.2-vision** | Fatal model-load on current Ollama (mllama) — circuit opens after first page |
| **General VLMs first** (`llava`, …) | Timeouts on dense scans; use after an OCR-oriented first pass |

Picker copy and **Model information** expander follow [`model_advice.py`](../../src/transcribe/services/model_advice.py). Per-tag prompt lanes: [ocr_model_recipes.md](ocr_model_recipes.md). Product limits: [known_limitations.md](../known_limitations.md).
