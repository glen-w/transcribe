Type: GUIDE
Authority: user flows and examples — summarizes contracts; does not define schemas

# User guide

Import pages → run local OCR → review/edit → export. Product framing: [PRODUCT.md](PRODUCT.md). Entrypoints: [public_surfaces.md](public_surfaces.md).

## 1. Create or open a notebook

**UI:** pick an existing notebook from the sidebar dropdown (sets context for Workflow), or choose **Workflow → New notebook**, name it, and create. Rename later from **View** (Rename action) or **Workflow → Import**.

**CLI:**

```bash
./transcribe.sh cli init "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --title "Travel 2024"
```

On-disk layout summary: [contracts/project-on-disk.md](contracts/project-on-disk.md).

## 2. Import

Supported inputs: JPEG, PNG, PDF (unencrypted). PDFs are rendered to per-page PNGs.

```bash
./transcribe.sh cli import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./scan.pdf --dpi 200
```

In the UI: select a notebook → **Workflow → Import** → set **Notebook name** if needed → upload → Import files.

## 3. Choose a vision model and run

List models:

```bash
./transcribe.sh cli models
```

Run:

```bash
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
# force re-OCR: add --force
```

In the UI: **Transcribe → Run OCR** → select vision model → optional **Clean OCR with text model** (mode + cleanup model) → Start transcription. Settings saved mid-job apply to the **next** job; the active run uses a frozen plan. Cleanup failures keep raw OCR and do not fail the page.

Matching fingerprints on succeeded pages are skipped when model identity was verified. Details: [contracts/page-result.md](contracts/page-result.md).

## 4. Review and edit

Open Archive / View / Search / Review, then the page viewer. Use ← / → or type a page number and press Enter / Go to jump. The viewer shows status, the transcription model used for the active OCR attempt, and any cleanup note. Edits are stored as `edited_text` and survive re-runs.

```bash
./transcribe.sh cli status "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

## 5. Notebook analysis (optional)

After pages have text (OCR and/or edits), open **Workflow → Analyse**:

1. Choose an analysis preset (**Quick** / **Balanced** / **Thorough** / **Custom**) — same policy model as TranscriptX.
2. Optionally enable an Ask-notebook question.
3. Run analysis, then inspect published results in Overview / Themes / Mood & tone / Moments / Summaries / Ask notebook.
4. Open the **Detect** tab to scan for poetry, to-do lists, other lists, and quotations (or custom detectors). Review findings, jump to source pages, and approve/reject.

Edit what each preset includes under **App → Settings → Analysis**. Manage prompts under **Settings → Prompts** and custom detectors under **Settings → Detection**. Models / Profiles tabs hold LLM budgets and named profile activations.

| Preset | Modules |
|--------|---------|
| **Quick** | Light/medium only — no LLM, no heavy modules |
| **Balanced** | Adds `semantic_similarity` + `llm_summary` |
| **Thorough** | All suitable core modules (including heavy + LLM suite) |
| **Custom** | Pick modules (seeded from Balanced) |

Use a **text** Ollama model for LLM modules. Deterministic synthesis works without it. Capability banners (`unavailable_model`, `unavailable_extra`, `insufficient_data`, …) are intentional honesty, not blank failures. Roadmap: [ROADMAP.md](ROADMAP.md).

CLI detection:

```bash
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --detector poetry
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --list
```

## 6. Export

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
# or: … export <project> /path/to/dest
```

In the UI: **Workflow → Export**.
Produces notebook JSON, Markdown, plain text, and an export manifest. Contract: [contracts/notebook-export.md](contracts/notebook-export.md).

## 7. Integrity check

```bash
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --deep
```

## Privacy reminder

Prefer loopback Ollama. Remote hosts send page images off-machine and require acknowledgement. See [known_limitations.md](known_limitations.md).
