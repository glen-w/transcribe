Type: GUIDE
Authority: user flows and examples — summarizes contracts; does not define schemas

# User guide

Import pages → run local OCR → review/edit → export. Product framing: [PRODUCT.md](PRODUCT.md). Entrypoints: [public_surfaces.md](public_surfaces.md).

## 1. Create or open a project

**UI:** open Workflow and choose/create a project under your projects directory.

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

In the UI: Import tab → upload → Import files.

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

In the UI: Run tab → select model → Start transcription. Settings saved mid-job apply to the **next** job; the active run uses a frozen plan.

Matching fingerprints on succeeded pages are skipped when model identity was verified. Details: [contracts/page-result.md](contracts/page-result.md).

## 4. Review and edit

Open Archive / Notebooks / Search / Workflow, then the page viewer. Edits are stored as `edited_text` and survive re-runs.

```bash
./transcribe.sh cli status "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

## 5. Notebook analysis (optional)

After pages have text (OCR and/or edits), open Workflow analysis tabs:

| Tab | What it shows |
|-----|----------------|
| **Overview** | Counts, diversity, readability, entities, baseline wordcloud |
| **Themes** | Keyphrases, topics, similarity, topic shifts |
| **Mood & tone** | Sentiment, emotion family, hedging |
| **Moments** | Salient spans / pages |
| **Summaries** | Deterministic highlights → summary → insights; optional LLM summary / action items / narrative |
| **Ask notebook** | Grounded custom QA (`llm_custom_qa`) with unit evidence |

Use a **text** Ollama model for Summaries LLM modules and Ask notebook. Deterministic synthesis works without it. Capability banners (`unavailable_model`, `unavailable_extra`, `insufficient_data`, …) are intentional honesty, not blank failures. Roadmap: [ROADMAP.md](ROADMAP.md).

## 6. Export

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
# or: … export <project> /path/to/dest
```

Produces notebook JSON, Markdown, plain text, and an export manifest. Contract: [contracts/notebook-export.md](contracts/notebook-export.md).

## 7. Integrity check

```bash
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --deep
```

## Privacy reminder

Prefer loopback Ollama. Remote hosts send page images off-machine and require acknowledgement. See [known_limitations.md](known_limitations.md).
