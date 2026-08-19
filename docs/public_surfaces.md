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
| `bulk-analyse pending\|import-run\|notebooks` | Batch Analyse across notebooks (`--preset`, optional `--module` / `--question` / `--text-model`) |
| `bulk-analyse status\|resume <analysis_batch_id>` | Inspect or resume an AnalysisBatchRun |
| `multipass <project> --model A --model B …` | Multi-model OCR then rank/composite (`--force`, `--no-auto-composite`, `--text-model`, `--cleanup` to opt in vision-phase cleanup) |
| `export <project> [dest]` | Write selected formats (JSON, Markdown, text, HTML, EPUB, PDF) |
| `export-finetune <project> [dest]` | Export images + preferred/active text for external fine-tuning |
| `status <project>` | Print per-page status |
| `detect <project>` | Run a content detector (`--detector poetry\|todo_lists\|lists\|quotations\|beer_labels`, `--force`, `--auto-tag`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |
| `corpus-doctor` | Workspace corpus integrity (`--deep` also doctors each notebook) |
| `backup create` | Full-workspace ZIP to `{EXPORT}/backups/` (`--dest`, `--force`, `--include-inbox`, `--include-exports`) |
| `backup verify <archive.zip>` | Verify manifest + file index without changing the workspace |
| `restore <archive.zip>` | Replace-only restore (`--yes` required; `--dry-run`; `--no-safety-backup`) |

### UI modes

Sidebar order matches TranscriptX: unlabeled **primary** → **Workflow** → **View** (notebook picker, then consume pages) → **System**.

**Primary (unlabeled):** Home · Library · Search · Archive · Places. **Library** is the cover gallery (legacy nav name `View`). Archive remains the timeline listing. Places is the corpus NER map.

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Analyse · Detect · Export.

**View** (after the notebook picker): Read · Overview · Summaries · Ask · Themes · Mood. Themes includes an in-page **People** section (People & places map); Mood includes **Moments**. Nav labels are short; section titles stay long (Read → “Reading”, Mood → “Mood & tone”, People → “People & places”, Ask → “Ask notebook”). Legacy mode ids `People` and `Moments` still open those sections. View pages consume **current** `published.json`. There is no analysis-run picker. Missing published analysis **disables** Themes and Mood (`help`: “Select a notebook” / “Analyse this notebook first”) but **does not bounce** the current page — empty state + Analyse CTA. Overview, Summaries, and Ask require a notebook only (`page_metrics` is independent of text Analyse).

**System:** Settings · Diagnostics.

**Settings** tabs (chrome order): Configuration · Analysis · Detection · Tags · Prompts · Interface · Models · Profiles · Export. Settings `required_context` is `none` (no bounce to Home). **Tags** is the workspace catalogue (rename labels, colours, merge/delete with corpus rewrite). Configuration holds folders, **Backup** (full-workspace ZIP create / verify / dry-run / restore via on-disk paths), import/declutter, Archive paging, and Overview cards. Models holds workspace Ollama URL, OCR `preprocess_profile` seed, LLM budgets, and Apply-OCR-to-notebook (gated on a selected notebook). Live model discovery stays on Transcribe / Analyse. Profiles is a tab (activation pointer; not a System page). Export is read-only workspace defaults; live editors stay on Workflow → Export. Alignment note: [dev/settings_tx_alignment.md](dev/settings_tx_alignment.md).

First visit lands on **Home**. Unknown `ui_mode` still normalises to **Archive**.

**Stay, don’t bounce:** the picker never rewrites the current page. Context bar (“Notebook · *title*”) is hidden on Home, New notebook, Import, Transcribe, Analyse, Settings, and Diagnostics.

**Home:** empty → Create notebook / Import + one-line Ollama health. Non-empty → cheap archive counts, recent notebooks, action strips. No sample-notebook wizard (that remains U2.2).

**Diagnostics:** workspace corpus-doctor always; notebook doctor when a notebook is selected; Ollama line as on Home.

**Library** shows cover thumbnails and coloured notebook tag chips; Search supports Period/Year/Range filters with clear empty states. **Archive** supports clickable activity bins (filter to that date — not Reading), notebook-strip paging via workspace `ui.archive_notebooks_initial` (**Settings → Configuration → Archive**; `0` = show all), and configurable action menus (**Settings → Interface**). Page viewer supports Prefer/Promote when multiple OCR attempts exist, **Delete page** (refuses last page / OCR job lock), and clickable page-tag pills that AND-filter the current Prev/Next set.

**Review** is an OCR comparison workbench: large page scan on the left; **Transcription**, **Date**, **Tags**, and **Other** tabs on the right (typical pass through those lanes). **Transcription** holds the editor, compact raw-attempt evidence, optional **Merged draft** (LLM composite — a recommendation, not a vote), and disagreement-centric navigation (source disagreements only count raw OCR). Queue filters: unreviewed, needs attention, high disagreement, unapproved dates, empty text, failed OCR, reviewed, skipped. **Save** stays on the page; **Save + Mark reviewed** persists the editor then fingerprints the current effective text + OCR evidence. **Date** tab: manual entry, approve/ignore suggestions, **💾 Save date** (nav **✓ date** for quick approve). **Tags** tab: tag assignment + **💾 Save tags**. **Other**: notebook cover, per-notebook **OCR settings** (**When setting a notebook default**, **Seed transcription from merged draft after multipass**), re-run OCR, delete page — [runtime/ocr.md](runtime/ocr.md#notebook-ocr-settings).

**Reading** is a first-class View page (chronological image + read-only text, jump-by-date, session continue-reading). **Open** from Library / Archive, Search hits, Moments jump, and Overview / Themes / Mood / page-metrics chart clicks all land on Reading (Back returns to the source listing or View page). Detect’s page viewer returns to Detect. Clicking a page-tag pill (for example **Poetry**) constrains served pages to those with that tag; **Clear tag filter** restores the baseline.

**Import** uses a Target switcher (TranscriptX-style): **This notebook** (file uploader into the selected notebook) or **Batch** (folder / parent-of-folders ImportRun, recent runs, resume). Legacy **Inbox** aliases to Import → Batch. Import commits show a live progress panel.

**Transcribe (OCR)** uses the same Target switcher: **This notebook** (vision model + Start transcription, optional cleanup, Compare models) or **Batch** (same OCR plan × many notebooks — single-model or Compare models; pending pages, an ImportRun, or a manual pick). A **Model information** expander on each live picker shows discovery metadata, verified/unverified identity, size, preference last-used, and first-OCR vs quality guidance for the **current selection**. **Compare models** runs multipass in the background (multi-select vision models → rank + composite); on Batch it runs that plan sequentially per notebook. Vision-phase cleanup is off unless **Clean OCR during compare** is checked. Single-notebook, multipass, and batch OCR jobs use the shared live progress panel. After repeated vision **timeouts** or a fatal **model-load** error, remaining pages for that frozen vision plan are skipped (`circuit_open`); multipass continues with other models. Workers, force re-OCR, cleanup mode/model, prefer mode, and capability dumps sit under **Advanced**. OCR comparison happens in **Review** (workbench), not as stacked Prefer/Promote cards on this page. Non-local Ollama hosts still require an explicit acknowledgement checkbox because page images leave the machine.

**Analyse** is the **launcher only** (This notebook | Batch). Quick / Balanced / Thorough / Custom presets, live progress, and a post-run strip. This-notebook complete navigates to **Overview**; Batch complete **stays on Analyse** (post-batch gallery control → Library; per-item Open → Overview if published, else Reading). Product read-models are **View** pages, not Analyse tabs. A shared status strip on analysis-backed View pages answers notebook revision and batch health. Module ids, capability enums, and raw JSON can live under **Advanced** expanders on View pages — **off by default** (`ui.view_show_advanced`; enable under **Settings → Configuration → Overview**). Ordinary use does not require module/cache literacy. Overview cards are a Settings checklist (`ui.overview_cards`; status strip always on). Overview and Mood can **compare** numeric metrics (lexical diversity, readability, sentiment, emotion, …) with the **corpus average** or a **year / date-range** period (peer notebooks’ diary spans; this notebook excluded from the average). Themes / Mood → Moments / Summaries use module-appropriate charts and lists (topic weights, motif pairs, quote scores, grouped action items) rather than JSON dumps; Moments and page-series charts **Jump to page** into Reading. **Word themes** let you choose **Basic** (static cloud) or **Advanced** (interactive TranscriptX-style explorer: search, top N, min value, sort, CSV) — Advanced is offline via vendored `wordcloud2.js`. **Themes → People** maps GPE/LOC/FAC entities from published NER for this notebook and shows **entity tone** when `entity_sentiment` is published (optional OpenStreetMap Nominatim geocoding with a local cache; opt-in because place names leave the machine). **Places** (primary nav) aggregates the same map across all notebooks. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); workspace bulk runs are [analysis-batch-run.md](contracts/analysis-batch-run.md). LLM modules need a text-capable Ollama model. Preset policies, import/declutter, Archive strip paging, Overview cards, View Advanced expanders, and module knobs live under **Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)). **Settings → Configuration → Import** can **re-apply visual declutter** to an existing notebook without re-running OCR.

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
| UI **Workflow → Analyse → Batch** | Streamlit Analyse Target=Batch | Same Analyse plan × N notebooks; pick (default, labels show published status) / needing-analysis / import-run; batch text-model freeze when LLM modules included; dual-bar live progress |
| CLI `backup create\|verify` / `restore` | `transcribe backup …` / `transcribe restore …` | Full-workspace ZIP; replace-only restore with safety ZIP; see [workspace-backup.md](contracts/workspace-backup.md) · [backup_and_restore.md](backup_and_restore.md) |
| UI **Settings → Configuration → Backup** | Streamlit Configuration | Path-based create / verify / dry-run / restore (no browser zip transfer) |

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.

Place-name geocoding for People & places / Places maps uses OpenStreetMap Nominatim only when the user opts in; results are cached under `data/cache/geocode.json`. Without opt-in, only already-cached coordinates are shown.
