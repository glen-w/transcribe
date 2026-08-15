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

Prefer OCR-oriented tags over general VLMs. After **3 consecutive timeouts** or **1 fatal model-load** error on a frozen vision plan, remaining pages for **that** model are skipped (`circuit_open`) so a bad tag does not burn the notebook.

## This notebook (single model)

```bash
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
# force re-OCR: add --force
```

**UI:** **Workflow → Transcribe** → Target **This notebook** → vision model → optional **Clean OCR with text model** → Start. Open **Model information** under a picker for family, size, capabilities, and OCR-fit caveats.

Matching fingerprints on succeeded pages are skipped when model identity was verified. Settings saved mid-job apply to the **next** job; the active run uses a frozen plan. Cleanup failures keep raw OCR and do not fail the page.

## Multipass compare

```bash
./transcribe.sh cli multipass "$TRANSCRIBE_PROJECTS_DIR/my-notebook" \
  --model gemma3:4b --model qwen2.5vl:7b --text-model qwen2.5:7b
```

**UI:** **Compare models** (multi-select) → Start multipass compare (background). Vision-phase cleanup defaults **off** unless you opt in. Rank + optional composite use the text/cleanup model. Prefer / Promote in Review: [page-result](../contracts/page-result.md). Preference ledger: [ocr-preference](../contracts/ocr-preference.md).

## Batch OCR

```bash
./transcribe.sh cli bulk-run pending --model llama3.2-vision
./transcribe.sh cli bulk-run import-run <import_run_id> --model llama3.2-vision
./transcribe.sh cli bulk-run pending --model vision-a --model vision-b --text-model qwen2.5
./transcribe.sh cli bulk-run status|resume <ocr_run_id>
```

**UI:** **Workflow → Transcribe → Batch** (also reachable after Import → Batch via **Transcribe imported notebooks**). Single-model or multipass compare across notebooks; live progress panel. Contract: [ocr-batch-run](../contracts/ocr-batch-run.md).

## Review after OCR

**Review** is the needs-attention queue (dates, empty text, failures). **Compare OCR attempts** for Prefer / Promote. Edits live in `edited_text` and survive re-runs. Golden path detail: [user_guide.md](../user_guide.md).

## Related

- Settings / preprocess seed: [settings.md](settings.md)
- Import / bulk import: [user_guide.md](../user_guide.md)
- Docker Ollama URL: [docker.md](docker.md)
