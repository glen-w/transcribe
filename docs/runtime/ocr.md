Type: GUIDE
Authority: OCR / multipass / batch operations — summarizes page-result and OCR contracts; does not redefine schemas

# OCR and transcription

Run local vision OCR via Ollama on notebook pages. Product framing: [PRODUCT.md](../PRODUCT.md). Limits and model caveats: [known_limitations.md](../known_limitations.md).

**Contracts:** [page-result](../contracts/page-result.md) · [ocr-multipass](../contracts/ocr-multipass.md) · [ocr-preference](../contracts/ocr-preference.md) · [ocr-batch-run](../contracts/ocr-batch-run.md).

## Prerequisites

- Running Ollama (`TRANSCRIBE_OLLAMA_BASE_URL`, default `http://localhost:11434`)
- At least one vision-capable, OCR-oriented model

```bash
./transcribe.sh cli models
./transcribe.sh cli models --refresh --prefs
```

Prefer OCR-oriented tags over general VLMs. After **3 consecutive timeouts** or **1 fatal model-load** error on a frozen vision plan, remaining pages for **that** model are skipped (`circuit_open`) so a bad tag does not burn the notebook. Some tags (DeepSeek-OCR) use a **model recipe** for the frozen prompt — [ocr_model_recipes.md](ocr_model_recipes.md). Whitespace-only OCR is **failed** (`empty_output`) and does not overwrite a prior reading. **Thinking vision models** (for example `gemma4`) often burn `num_predict` internally and return empty text — see [ocr_model_matrix.md](ocr_model_matrix.md).

## This notebook (single model)

```bash
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
# force re-OCR: add --force
```

**UI:** **Workflow → Transcribe** → Target **This notebook** → vision model → optional **Clean OCR with text model** → Start. Open **Model information** under a picker for family, size, capabilities, and OCR-fit caveats. Vision pickers list **OCR-appropriate VLMs only** (thinking models, text-only tags, and broken loaders excluded); text pickers list **completion LLMs only** (vision/embedding/OCR tags excluded).

Matching fingerprints on succeeded pages are skipped when model identity was verified. Settings saved mid-job apply to the **next** job; the active run uses a frozen plan. Cleanup failures keep raw OCR and do not fail the page.

## Multipass compare

```bash
./transcribe.sh cli multipass "$TRANSCRIBE_PROJECTS_DIR/my-notebook" \
  --model gemma3:4b --model qwen2.5vl:7b --text-model qwen2.5:7b
```

**UI:** **Compare models** (multi-select) → Start multipass compare (background). Vision-phase cleanup defaults **off** unless you opt in. Rank + optional **merged draft** (composite) use the text/cleanup model. If two or more models already have succeeded text on disk (separate Transcribe jobs), **Rank and merge existing OCR** on Transcribe or Review runs rank/composite without re-running vision. Review the draft in the **Transcription** tab beside the scan: [ocr_review_workbench_plan.md](../dev/ocr_review_workbench_plan.md). Notebook OCR settings (below) and contract detail: [page-result](../contracts/page-result.md). Preference ledger: [ocr-preference](../contracts/ocr-preference.md).

## Notebook OCR settings

Per-notebook overrides for **When setting a notebook default** (prefer mode) and **Seed transcription from merged draft after multipass** (`auto_activate_composite`). Workspace defaults seed new notebooks; these fields live on `project.json` → `settings`.

| Where in UI | Notes |
|-------------|-------|
| **Workflow → Review** → **Other** tab | **OCR settings** — labels match the Review workbench |
| **Reading / Archive** page viewer → **Compare OCR attempts** | Same semantics; slightly shorter control labels |
| **Workflow → Transcribe** → **Advanced** (single-model / batch) | Prefer mode + auto-activate composite for the next run |
| **Workflow → Transcribe** → multipass row | **Do not auto-activate composite** inverts the seed checkbox for that compare only |

Changes apply to the **next** multipass or Prefer action; an active job keeps its frozen plan.

### When setting a notebook default

Controls what happens when you **Prefer** an OCR attempt (or when multipass auto-activates a merged draft under `prefer_is_promote`). **Promote** always sets the active attempt without clearing your edit overlay.

| UI label (Review) | Mode | Behaviour |
|-------------------|------|-----------|
| **Notebook default = current text** (default) | `prefer_is_promote` | Prefer sets both notebook default (`preferred_attempt_id`) and **current text** (`active_attempt_id`). Effective text follows the active attempt unless you have an edit in Transcription. |
| **Notebook default only (stats / fine-tune)** | `prefer_only` | Prefer records the notebook default and preference stats only — **does not** change current text or what Transcription shows. Use when tagging a favourite model for export / ledger without switching the live reading. |
| **Notebook default + current, with edit gate** | `prefer_promote_with_edit_gate` | Like the default, but if Transcription already has a human edit, Prefer asks **Keep edit overlay** vs **Adopt new (clear edit)** before applying. |

Preference history and rollup stats: [ocr-preference](../contracts/ocr-preference.md).

### Seed transcription from merged draft after multipass

When **on** (default), multipass activation after a successful **merged draft** (composite):

1. Sets the merged draft as the **active** attempt (and notebook default when prefer mode is **Notebook default = current text**).
2. Seeds the Review **Transcription** buffer from that draft when there is no edit overlay.
3. Records an `auto_composite` event in the preference ledger.

When **off**, multipass still ranks vision attempts and builds a merged draft for review, but does **not** auto-activate it. Pages with no prior active attempt fall back to the best-ranked raw vision output. Use this when you want every page reviewed manually before the merged draft becomes current text.

CLI equivalent: omit `--no-auto-composite` (default seeds) or pass `--no-auto-composite` to disable.

## Batch OCR

```bash
./transcribe.sh cli bulk-run pending --model llama3.2-vision
./transcribe.sh cli bulk-run import-run <import_run_id> --model llama3.2-vision
./transcribe.sh cli bulk-run pending --model vision-a --model vision-b --text-model qwen2.5
./transcribe.sh cli bulk-run status|resume <ocr_run_id>
```

**UI:** **Workflow → Transcribe → Batch** (also reachable after Import → Batch via **Transcribe imported notebooks**). Single-model or multipass compare across notebooks; live progress panel. Contract: [ocr-batch-run](../contracts/ocr-batch-run.md).

## Review after OCR

**Review** is the needs-attention queue (dates, empty text, failures). Right-pane tabs walk **Transcription → Date → Tags → Other** beside the scan; layout and evidence hierarchy: [ocr_review_workbench_plan.md](../dev/ocr_review_workbench_plan.md). **Other → Re-run OCR** picks a vision model and can force this page, all pages, or pages not marked reviewed. **Rank and merge** (this page / all comparable pages) runs rank + merged draft on existing readings. Failed attempts appear in OCR evidence. Golden path detail: [user_guide.md](../user_guide.md).

## Related

- Settings / preprocess seed: [settings.md](settings.md)
- Model recipes (DeepSeek-OCR `Free OCR.` lane): [ocr_model_recipes.md](ocr_model_recipes.md)
- Local probe matrix (first-OCR picks): [ocr_model_matrix.md](ocr_model_matrix.md)
- Import / bulk import: [user_guide.md](../user_guide.md)
- Docker Ollama URL: [docker.md](docker.md)
