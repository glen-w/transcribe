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
| `bulk-analyse pending\|import-run\|notebooks` | Batch Analyse across notebooks (`--preset`, optional `--module` / `--question`) |
| `bulk-analyse status\|resume <analysis_batch_id>` | Inspect or resume an AnalysisBatchRun |
| `multipass <project> --model A --model B …` | Multi-model OCR then rank/composite (`--force`, `--no-auto-composite`, `--text-model`, `--cleanup` to opt in vision-phase cleanup) |
| `export <project> [dest]` | Write selected formats (JSON, Markdown, text, HTML, EPUB, PDF) |
| `export-finetune <project> [dest]` | Export images + preferred/active text for external fine-tuning |
| `status <project>` | Print per-page status |
| `detect <project>` | Run a content detector (`--detector poetry\|todo_lists\|lists\|quotations\|beer_labels`, `--force`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

Sidebar order matches TranscriptX: unlabeled **primary** → **Workflow** → **View** (notebook picker, then consume pages) → **System**.

**Primary (unlabeled):** Home · Library · Search · Archive · Places. **Library** is the cover gallery (legacy nav name `View`). Archive remains the timeline listing. Places is the corpus NER map.

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Analyse · Export.

**View** (after the notebook picker): Reading · Overview · Themes · Mood · Summaries · Detect. Themes includes an in-page **People** section (People & places map); Mood includes **Moments**; Summaries includes **Ask**. Nav labels are short; section titles stay long (Mood → “Mood & tone”, People → “People & places”, Ask → “Ask notebook”). Legacy mode ids `People`, `Moments`, and `Ask` still open those sections. View pages consume **current** `published.json`. There is no analysis-run picker. Missing published analysis **disables** Themes and Mood (`help`: “Select a notebook” / “Analyse this notebook first”) but **does not bounce** the current page — empty state + Analyse CTA. Overview and Summaries require a notebook only (Ask remains reachable without published analysis; `page_metrics` is independent of text Analyse).

**System:** Settings · Diagnostics.

First visit lands on **Home**. Unknown `ui_mode` still normalises to **Archive**.

**Stay, don’t bounce:** the picker never rewrites the current page. Context bar (“Notebook · *title*”) is hidden on Home, New notebook, Import, Transcribe, Analyse, Settings, and Diagnostics.

**Home:** empty → Create notebook / Import + one-line Ollama health. Non-empty → cheap archive counts, recent notebooks, action strips. No sample-notebook wizard (that remains U2.2).

**Diagnostics:** workspace corpus-doctor always; notebook doctor when a notebook is selected; Ollama line as on Home.

**Library** shows cover thumbnails and notebook tag chips; Search supports Period/Year/Range filters with clear empty states. **Archive** supports clickable activity bins (filter to that date — not Reading), notebook-strip paging via workspace `ui.archive_notebooks_initial` (**Settings → Configuration → Archive**; `0` = show all), and configurable action menus (**Settings → Interface**). Page viewer supports Prefer/Promote when multiple OCR attempts exist, and **Delete page** (refuses last page / OCR job lock).

**Review** is a needs-attention queue: filter to unapproved dates, empty text, or failed OCR; batch approve/ignore suggested dates; edit transcription and metadata in the shared page viewer.

**Reading** is a first-class View page (chronological image + read-only text, jump-by-date, session continue-reading). **Open** from Library / Archive, Search hits, Moments jump, and Overview / Themes / Mood / page-metrics chart clicks all land on Reading (Back returns to the source listing or View page). Review’s edit viewer is unchanged. Detect’s page viewer returns to Detect.

**Import** uses a Target switcher (TranscriptX-style): **This notebook** (file uploader into the selected notebook) or **Batch** (folder / parent-of-folders ImportRun, recent runs, resume). Legacy **Inbox** aliases to Import → Batch. Import commits show a live progress panel.

**Transcribe (OCR)** uses the same Target switcher: **This notebook** (vision model + Start transcription, optional cleanup, Compare models) or **Batch** (same OCR plan × many notebooks — single-model or Compare models; pending pages, an ImportRun, or a manual pick). A **Model information** expander on each live picker shows discovery metadata, verified/unverified identity, size, preference last-used, and first-OCR vs quality guidance for the **current selection**. **Compare models** runs multipass in the background (multi-select vision models → rank + composite); on Batch it runs that plan sequentially per notebook. Vision-phase cleanup is off unless **Clean OCR during compare** is checked. Single-notebook, multipass, and batch OCR jobs use the shared live progress panel. After repeated vision **timeouts** or a fatal **model-load** error, remaining pages for that frozen vision plan are skipped (`circuit_open`); multipass continues with other models. Workers, force re-OCR, cleanup mode/model, prefer mode, and capability dumps sit under **Advanced**. Review shows Compare OCR attempts when multiple succeeded outputs exist (plain-text previews so markdown-looking OCR does not inflate headings). Non-local Ollama hosts still require an explicit acknowledgement checkbox because page images leave the machine.

**Analyse** is the **launcher only** (This notebook | Batch). Quick / Balanced / Thorough / Custom presets, live progress, and a post-run strip. This-notebook complete navigates to **Overview**; Batch complete **stays on Analyse** (post-batch gallery control → Library; per-item Open → Overview if published, else Reading). Product read-models are **View** pages, not Analyse tabs. A shared status strip on analysis-backed View pages answers notebook revision and batch health. Module ids, capability enums, and raw JSON live under **Advanced** expanders — ordinary use does not require module/cache literacy. Overview cards are a Settings checklist (`ui.overview_cards`; status strip always on). Overview and Mood can **compare** numeric metrics (lexical diversity, readability, sentiment, emotion, …) with the **corpus average** or a **year / date-range** period (peer notebooks’ diary spans; this notebook excluded from the average). Themes / Mood → Moments / Summaries use module-appropriate charts and lists (topic weights, motif pairs, quote scores, grouped action items) rather than JSON dumps; Moments and page-series charts **Jump to page** into Reading. **Word themes** let you choose **Basic** (static cloud) or **Advanced** (interactive TranscriptX-style explorer: search, top N, min value, sort, CSV) — Advanced is offline via vendored `wordcloud2.js`. **Themes → People** maps GPE/LOC/FAC entities from published NER for this notebook and shows **entity tone** when `entity_sentiment` is published (optional OpenStreetMap Nominatim geocoding with a local cache; opt-in because place names leave the machine). **Places** (primary nav) aggregates the same map across all notebooks. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); workspace bulk runs are [analysis-batch-run.md](contracts/analysis-batch-run.md). LLM modules need a text-capable Ollama model. Preset policies, import/declutter, Archive strip paging, Overview cards, and module knobs live under **Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)). **Settings → Configuration → Import** can **re-apply visual declutter** to an existing notebook without re-running OCR.

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
| CLI `bulk-analyse pending` | `transcribe bulk-analyse pending --preset …` | Analyse notebooks needing analysis |
| CLI `bulk-analyse import-run <id>` | `transcribe bulk-analyse import-run …` | Analyse notebooks committed by an ImportRun |
| CLI `bulk-analyse notebooks …` | `transcribe bulk-analyse notebooks <id-or-path> …` | Explicit notebook list |
| CLI `bulk-analyse status\|resume <id>` | `transcribe bulk-analyse status\|resume …` | Inspect or resume an AnalysisBatchRun |
| UI **Workflow → Import → Batch** | Streamlit Import Target=Batch | Single-folder or parent-of-folders ImportRun; skip/overwrite with typed `OVERWRITE ALL`; recovery outcomes; live progress. Legacy Inbox aliases here. |
| UI **Workflow → Transcribe → Batch** | Streamlit Transcribe Target=Batch | Single-model or multipass Compare models × N notebooks; pending / import-run / pick; resume; live progress |
| UI **Workflow → Analyse → Batch** | Streamlit Analyse Target=Batch | Same Analyse plan × N notebooks; needing-analysis / import-run / pick; dual-bar live progress |

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.

Place-name geocoding for People & places / Places maps uses OpenStreetMap Nominatim only when the user opts in; results are cached under `data/cache/geocode.json`. Without opt-in, only already-cached coordinates are shown.
