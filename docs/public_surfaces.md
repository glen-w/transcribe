Type: CONTRACT
Authority: self — supported public entrypoints and support policy for how users invoke Transcribe

# Public surfaces

## Supported

| Surface | How to invoke | Notes |
|---------|---------------|-------|
| Streamlit UI | `./transcribe.sh ui` · `transcribe-ui` · `streamlit run src/transcribe/ui/app.py` | Default port **8510** (`TRANSCRIBE_PORT`) |
| CLI | `./transcribe.sh cli …` · `python -m transcribe …` · `transcribe …` | Same services as the UI |
| Docker Compose web | `docker compose up transcribe-web` | Published at `127.0.0.1:8510` by default |

### CLI commands

| Command | Purpose |
|---------|---------|
| `init <project>` | Create a new project directory |
| `import <project> <source>` | Import JPEG/PNG/PDF (`--dpi` for PDFs) |
| `models` | List vision-capable Ollama models (`--base-url`, `--all`, `--refresh`, `--prefs`) |
| `run <project> --model …` | Run OCR (`--force`, `--workers 1|2`, `--base-url`, `--allow-remote-ollama`) |
| `bulk-run pending\|import-run\|notebooks` | Batch OCR across notebooks (repeat `--model` for multipass; `--force`, `--workers`, `--text-model`, `--no-auto-composite`, `--cleanup`) |
| `bulk-run status\|resume <ocr_run_id>` | Inspect or resume an OcrBatchRun |
| `multipass <project> --model A --model B …` | Multi-model OCR then rank/composite (`--force`, `--no-auto-composite`, `--text-model`, `--cleanup` to opt in vision-phase cleanup) |
| `export <project> [dest]` | Write selected formats (JSON, Markdown, text, HTML, EPUB, PDF) |
| `export-finetune <project> [dest]` | Export images + preferred/active text for external fine-tuning |
| `status <project>` | Print per-page status |
| `detect <project>` | Run a content detector (`--detector poetry\|todo_lists\|lists\|quotations\|beer_labels`, `--force`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

**Notebooks:** View · Search · Archive · Places (shared page viewer for review/edit). Sidebar dropdown selects the active notebook for Workflow. View shows cover thumbnails and notebook tag chips; Search supports Period/Year/Range filters with clear empty states. **Archive** supports clickable activity bins (filter to that date), notebook-strip paging via workspace `ui.archive_notebooks_initial` (**Settings → Configuration → Archive**; `0` = show all), and configurable action menus (**Settings → Interface**). Page viewer supports Prefer/Promote when multiple OCR attempts exist, and **Delete page** (refuses last page / OCR job lock).

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Reading · Analyse · Export.

**Review** is a needs-attention queue: filter to unapproved dates, empty text, or failed OCR; batch approve/ignore suggested dates; edit transcription and metadata in the shared page viewer.

**Reading** is a distinct chronological presentation (image + read-only text, jump-by-date, session continue-reading) without edit/re-run/delete controls.

**Import** uses a Target switcher (TranscriptX-style): **This notebook** (file uploader into the selected notebook) or **Batch** (folder / parent-of-folders ImportRun, recent runs, resume). Legacy **Notebooks → Inbox** aliases to Import → Batch. Import commits show a live progress panel.

**Transcribe (OCR)** uses the same Target switcher: **This notebook** (vision model + Start transcription, optional cleanup, Compare models) or **Batch** (same OCR plan × many notebooks — single-model or Compare models; pending pages, an ImportRun, or a manual pick). A **Model information** expander on each live picker shows discovery metadata, verified/unverified identity, size, preference last-used, and first-OCR vs quality guidance for the **current selection**. **Compare models** runs multipass in the background (multi-select vision models → rank + composite); on Batch it runs that plan sequentially per notebook. Vision-phase cleanup is off unless **Clean OCR during compare** is checked. Single-notebook, multipass, and batch OCR jobs use the shared live progress panel. Workers, force re-OCR, cleanup mode/model, prefer mode, and capability dumps sit under **Advanced**. Review shows Compare OCR attempts when multiple succeeded outputs exist. Non-local Ollama hosts still require an explicit acknowledgement checkbox because page images leave the machine.

**Analyse** opens Analyse (Quick / Balanced / Thorough / Custom presets) plus product read-model tabs: Overview · Themes · Mood & tone · Moments · People & places · Summaries · Ask notebook · Detect. A shared status strip above the tabs answers notebook revision and batch health. Module ids, capability enums, and raw JSON live under **Advanced** expanders — ordinary use does not require module/cache literacy. Overview and Mood can **compare** numeric metrics (lexical diversity, readability, sentiment, emotion, …) with the **corpus average** or a **year / date-range** period (peer notebooks’ diary spans; this notebook excluded from the average). Themes / Moments / Summaries use module-appropriate charts and lists (topic weights, motif pairs, quote scores, grouped action items) rather than JSON dumps. **Word themes** render a real word-cloud image when the optional ``wordcloud`` package is present (``.[ui]``), falling back to token-weight bars otherwise. **People & places** maps GPE/LOC/FAC entities from published NER and shows **entity tone** when `entity_sentiment` is published (optional OpenStreetMap Nominatim geocoding with a local cache; opt-in because place names leave the machine). **Notebooks → Places** aggregates the same map across all notebooks. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); LLM modules need a text-capable Ollama model. Preset policies, import/declutter, Archive strip paging, and module knobs live under **App → Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)). **Settings → Configuration → Import** can **re-apply visual declutter** to an existing notebook without re-running OCR.

### Helper script

`./transcribe.sh` resolves a project-local `.venv` and accepts: `ui|web` (default), `cli|run …`, `install|setup`, `install-dev`, or passthrough argv to the CLI.

## Corpus surfaces (supported)

Bulk-import generation is **runtime-normative**; the [acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is green. Supported surfaces:

| Surface | How to invoke | Notes |
|---------|---------------|-------|
| CLI `bulk-import folder <dir>` | `transcribe bulk-import folder …` (`--policy`, `--dry-run`) | Plan/commit one flat folder into one notebook |
| CLI `bulk-import folders <parent>` | `transcribe bulk-import folders …` (`--on-existing skip\|overwrite`, `--confirm-overwrite 'OVERWRITE ALL'`, `--policy`, `--dry-run`) | Each child folder → one notebook named after it; overwrite requires exact confirmation |
| CLI `bulk-import status\|resume <id>` | `transcribe bulk-import status\|resume …` | Inspect or resume an ImportRun |
| CLI `corpus-doctor` | `transcribe corpus-doctor` (`--deep`) | Workspace corpus index integrity |
| CLI `bulk-run pending` | `transcribe bulk-run pending --model …` (repeat `--model` for multipass) | OCR notebooks with untranscribed/failed pages |
| CLI `bulk-run import-run <id>` | `transcribe bulk-run import-run … --model …` | OCR notebooks committed by an ImportRun |
| CLI `bulk-run notebooks …` | `transcribe bulk-run notebooks <id-or-path> … --model …` | Explicit notebook list |
| CLI `bulk-run status\|resume <id>` | `transcribe bulk-run status\|resume …` | Inspect or resume an OcrBatchRun |
| UI **Workflow → Import → Batch** | Streamlit Import Target=Batch | Single-folder or parent-of-folders ImportRun; skip/overwrite with typed `OVERWRITE ALL`; recovery outcomes; live progress. Legacy Inbox aliases here. |
| UI **Workflow → Transcribe → Batch** | Streamlit Transcribe Target=Batch | Single-model or multipass Compare models × N notebooks; pending / import-run / pick; resume; live progress |

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.

Place-name geocoding for People & places / Places maps uses OpenStreetMap Nominatim only when the user opts in; results are cached under `data/cache/geocode.json`. Without opt-in, only already-cached coordinates are shown.
