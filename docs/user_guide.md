Type: GUIDE
Authority: user flows and examples — summarizes contracts; does not define schemas

# User guide

Import pages → run local OCR → review/edit → export. Product framing: [PRODUCT.md](PRODUCT.md). Entrypoints: [public_surfaces.md](public_surfaces.md).

## 1. Create or open a notebook

**UI:** pick an existing notebook from the sidebar **View** picker (sets context for Workflow and View pages), or choose **Workflow → New notebook**, name it, and create. Rename later from **Library** (Rename action) or **Workflow → Import**. First visit opens **Home**.

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

In the UI: select a notebook → **Workflow → Import** → Target **This notebook** → set **Notebook name** if needed → upload → Import files. A live progress panel shows per-file status.

**Visual declutter** (scanner-border crop) defaults **on** for imports (`ingest.visual_declutter_enabled`). Toggle and **re-apply to an existing notebook** under **Settings → Configuration → Import** (does not re-run OCR).

## 3. Choose a vision model and run

List models:

```bash
./transcribe.sh cli models
```

Run:

```bash
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
# force re-OCR: add --force

# Compare two models, then rank + composite with the notebook text/cleanup model:
./transcribe.sh cli multipass "$TRANSCRIBE_PROJECTS_DIR/my-notebook" \
  --model gemma3:4b --model qwen2.5vl:7b --text-model qwen2.5:7b
```

In the UI: **Workflow → Transcribe** → Target **This notebook** → select vision model → optional **Clean OCR with text model** → Start transcription. Open **Model information** under a picker for family, size, capabilities, and OCR-fit caveats (follows the live picker selection). Or **Compare models** (multi-select) → Start multipass compare (runs in the background; vision cleanup off unless you opt in). Jobs show a live progress panel (per-page status and readable filenames). Prefer **OCR-oriented** vision tags for handwriting; general VLMs can hang. After repeated timeouts or a fatal model-load error, remaining pages for **that** model are skipped so a bad tag does not burn the whole notebook (multipass continues with the next model) — see [known_limitations.md](known_limitations.md). Settings saved mid-job apply to the **next** job; the active run uses a frozen plan. Cleanup failures keep raw OCR and do not fail the page.

Matching fingerprints on succeeded pages are skipped when model identity was verified. Multipass skips when any succeeded vision attempt matches. Details: [contracts/page-result.md](contracts/page-result.md) · [contracts/ocr-multipass.md](contracts/ocr-multipass.md).

## 4. Review, Reading, and search

**Review** is a needs-attention queue for the open notebook. Filter to pages that need date approval, have no text, or failed OCR. Approve or ignore all suggested dates in one pass (suspicious date regressions ask for a second confirm). Unapproved suggested dates still appear in the Archive timeline; time-of-day stamps are ignored.

Open Library / Search / Archive / Review / Reading, then the page viewer. Use ← / → or type a page number and press Enter / Go to jump. Review’s viewer shows status, the transcription model used for the active OCR attempt, and any cleanup note. When multiple attempts exist, **Compare OCR attempts** lets you Prefer / Promote (modes: prefer=promote, prefer-only, or edit-gate); attempt previews stay plain text so OCR that looks like markdown (leading `#`, `*`, …) does not blow up the layout. Edits are stored as `edited_text` and survive re-runs. **Delete page** removes one page from the notebook (refuses the last page and while OCR is running).

**Reading** opens the same pages chronologically (dated pages first) as image + read-only text — no edit, re-run, or delete controls. Jump by date when dates exist; the last page is remembered for the session.

**Archive:** click an activity bar to filter notebooks/pages to that date bin. The notebook strip loads `ui.archive_notebooks_initial` cards first (default **all**; change under **Settings → Configuration → Archive**), then **Show more** / **Show fewer**.

**Search** finds text across notebooks. Use Period / Year / Range (same idea as Archive), tags, and media filters. Open a hit to browse matching pages with Prev/Next.

```bash
./transcribe.sh cli status "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

Preference stats (which models you Prefer) appear beside model pickers and via `transcribe models --prefs`. Ledger: [contracts/ocr-preference.md](contracts/ocr-preference.md).

## 5. Notebook analysis (optional)

After pages have text (OCR and/or edits), open **Workflow → Analyse**:

1. Choose an analysis preset (**Quick** / **Balanced** / **Thorough** / **Custom**) — same policy model as TranscriptX.
2. Optionally enable an Ask-notebook question.
3. Run analysis. This-notebook complete opens **View → Overview**. Inspect published results under **View**: Overview / Themes / Mood / Summaries. Themes includes **People**; Mood includes **Moments**; Summaries includes **Ask**. A shared status strip shows whether results are current. Each page shows module-appropriate charts and lists (not raw JSON). **Word themes** can be **Basic** or **Advanced** (interactive filters). Overview and Mood include **Compare with corpus / period** for numeric metrics vs other notebooks. On **Mood → Moments**, **Jump to page** (and page-series chart clicks on Overview / Themes / Mood) opens that page in **Reading**. Themes → People adds **entity tone** when that module has run. Technical module details live under **Advanced**. Use **Places** in the primary nav for a map of places mentioned across all notebooks (opt-in OpenStreetMap geocoding; results cached locally).
4. **Thorough** (and Custom when you select them) can include **Detect** detectors in the same Analyse plan. Open **View → Detect** to review findings (approve/reject, jump to pages). Ad-hoc / page-scoped runs still launch from Detect → Run Detection.

Edit what each preset includes under **Settings → Analysis**. Manage prompts under **Settings → Prompts** and custom detectors under **Settings → Detection**. **Settings** tabs: Configuration · Analysis · Detection · Prompts · Interface · Models · Profiles · Export. Configuration holds folders, **Backup** (full-workspace ZIP), import/declutter, Archive paging, and Overview cards. Models holds the workspace Ollama URL, OCR preprocess seed (`none` / `gentle_contrast`), LLM budgets, and Apply-OCR to the open notebook. Profiles activates named overlays (`workflow` / `ocr` / `llm` / `export`). Interface customises action menus. Export shows read-only typography defaults (`readable` / `compact` / `large_print`); change them on **Workflow → Export** or by activating an export profile.

| Preset | Includes |
|--------|----------|
| **Quick** | Light/medium only — no LLM, no heavy modules, no detectors |
| **Balanced** | Adds `semantic_similarity` + `llm_summary` |
| **Thorough** | All suitable core modules (including heavy + LLM suite) + all detectors |
| **Custom** | Pick modules and detectors (modules seeded from Balanced) |

Use a **text** Ollama model for LLM modules and detectors. Set a workspace default under **Settings → Models**, configure per notebook under This notebook Analyse, or pick one for a whole **Batch** run. Deterministic synthesis works without it. When a model or optional component is missing, Analyse says so in plain language (for example “Needs a text model”) rather than raw capability enums. Roadmap: [ROADMAP.md](ROADMAP.md).

**Transcribe:** choose a vision model and start transcription. Optional OCR cleanup is a one-line toggle; workers, force re-run, and cleanup detail sit under **Advanced**. Batch OCR, Batch Analyse, and Import → Batch share the same live progress panel style.

CLI detection:

```bash
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --detector poetry
./transcribe.sh cli detect "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --list
```

## 6. Export

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
# or: … export <project> /path/to/dest
# formats / typography:
#   … export <project> --format pdf --format epub --profile large_print
# multi-notebook anthology:
#   … export --notebooks nb-a nb-b --title "Spring journals" /path/to/dest
```

In the UI: **Workflow → Export** (formats, typography, profiles, multi-notebook).
Produces JSON, Markdown, plain text, HTML, EPUB, PDF, and an export manifest
(formats selectable). Profiles: `readable` / `compact` / `large_print` under
Settings → Profiles (target **export**). Contract:
[contracts/notebook-export.md](contracts/notebook-export.md).

## 7. Integrity check

```bash
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --deep
```

In the UI: **System → Diagnostics** (workspace doctor always; notebook doctor when a notebook is selected).

## 7b. Workspace backup / restore

Pack the authoritative workspace (notebooks + corpus + config) into a ZIP, move it, then replace-restore onto the current mounts. Full operator guide: [backup_and_restore.md](backup_and_restore.md).

```bash
./transcribe.sh cli backup create
./transcribe.sh cli backup create --dest /path/to/workspace.zip
./transcribe.sh cli backup create --include-inbox --include-exports
./transcribe.sh cli backup verify /path/to/workspace.zip
./transcribe.sh cli restore /path/to/workspace.zip --dry-run
./transcribe.sh cli restore /path/to/workspace.zip --yes
```

Default write path: `{TRANSCRIBE_EXPORT_DIR}/backups/transcribe-workspace-<stamp>.zip`. Restore remaps archive role roots onto the current `TRANSCRIBE_*` paths, writes a safety ZIP first (unless `--no-safety-backup`), clears rebuildable `data/cache/`, then runs corpus-doctor. Inbox and exports are **off** by default.

In the UI: **Settings → Configuration → Backup** (create, verify, dry-run, confirm-gated restore). Prefer the CLI for large corpora. Contract: [contracts/workspace-backup.md](contracts/workspace-backup.md).

## 8. Bulk import, batch OCR, and bulk Analyse

Corpus bulk import is **supported** ([contracts/corpus-integrity.md](contracts/corpus-integrity.md) acceptance gate green). Single-file import (§2) remains the everyday path for one notebook at a time.

**UI:** **Workflow → Import** → Target **Batch** (legacy **Inbox** opens this).

- **One folder → one notebook** — path to a flat folder of scans.
- **Parent of folders → one notebook each** — path to a parent directory; each immediate child folder with JPEG/PNG/PDF becomes a notebook titled with that folder’s name. Already-imported folder names can be **skipped** or **overwritten**. Overwrite permanently deletes the managed notebook directory and requires typing exactly `OVERWRITE ALL`.

After a successful import, **Transcribe imported notebooks** opens **Workflow → Transcribe → Batch** with those notebooks selected. You can also pick **Notebooks with pending pages** or a manual list. Batch OCR uses one shared plan and runs notebooks one after another (fingerprint skip unless Force). Use **Start batch transcription** for a single vision model, or **Compare models** / **Start batch multipass compare** to run two or more vision models on each notebook (rank + optional composite), same as This notebook compare. Import, Transcribe, and batch OCR jobs show live progress (per-item / per-page status with readable filenames).

**Workflow → Analyse → Batch** opens with a **Pick notebooks** list (default). You can also scan **Notebooks needing analysis** or seed from an import run. Choose a preset (and a **text model** when the plan includes LLM modules or detectors — applied to every notebook in the batch), then **Start batch analysis**. Progress shows an outer notebook bar and an inner steps bar for the current notebook (modules then detectors); **Stop after current notebook** cancels the rest. Empty-text notebooks are skipped. After the batch finishes you stay on Analyse; **Library** opens the gallery, and per-item **Open** goes to Overview if that notebook has published analysis, otherwise Reading. Consume published results under **View** for the selected notebook.

**Docker:** paste **container** paths (`/mnt/inbox`, or `/mnt/notebooks` if you mounted `HOST_BULK_IMPORT_DIR`), not host paths like `/Users/...`. Details: [runtime/docker.md](runtime/docker.md#bulk-import-paths-inbox-ui--cli-in-docker).

**CLI:**

```bash
./transcribe.sh cli bulk-import folder ./scans --dry-run
./transcribe.sh cli bulk-import folder ./scans --policy skip_existing_v1
./transcribe.sh cli bulk-import folders ./scan-batches --dry-run
./transcribe.sh cli bulk-import folders ./scan-batches --on-existing skip
./transcribe.sh cli bulk-import folders ./scan-batches --on-existing overwrite --confirm-overwrite 'OVERWRITE ALL'
./transcribe.sh cli bulk-import status <import_run_id>
./transcribe.sh cli bulk-import resume <import_run_id>
./transcribe.sh cli bulk-run pending --model llama3.2-vision
./transcribe.sh cli bulk-run import-run <import_run_id> --model llama3.2-vision
./transcribe.sh cli bulk-run pending --model vision-a --model vision-b --text-model qwen2.5
./transcribe.sh cli corpus-doctor --deep
```

Overwrite deletes **managed** notebook copies under the projects directory only; external originals outside that tree are untouched. After recovery or index rebuild, retained quarantine artifacts may show as doctor **warnings** (`corpus_quarantine_present`) until an operator deletes them.

## Privacy reminder

Prefer loopback Ollama. Remote hosts send page images off-machine and require acknowledgement. See [known_limitations.md](known_limitations.md).
