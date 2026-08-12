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
| `multipass <project> --model A --model B …` | Multi-model OCR then rank/composite (`--force`, `--no-auto-composite`, `--text-model`) |
| `export <project> [dest]` | Write selected formats (JSON, Markdown, text, HTML, EPUB, PDF) |
| `export-finetune <project> [dest]` | Export images + preferred/active text for external fine-tuning |
| `status <project>` | Print per-page status |
| `detect <project>` | Run a content detector (`--detector poetry\|todo_lists\|lists\|quotations\|beer_labels`, `--force`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

**Notebooks:** View · Search · Archive · Places · Inbox (shared page viewer for review/edit). Sidebar dropdown selects the active notebook for Workflow. **Inbox** is the ImportRun recovery / bulk-import surface — see **Corpus surfaces** below.

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Analyse · Export.

**Analyse** opens Run Analysis (Quick / Balanced / Thorough / Custom presets) plus product read-model tabs: Overview · Themes · Mood & tone · Moments · People & places · Summaries · Ask notebook. A shared status strip above the tabs answers notebook revision and batch health. Module ids, capability enums, and raw JSON live under **Advanced** expanders — ordinary use does not require module/cache literacy. **People & places** maps GPE/LOC/FAC entities from published NER (optional OpenStreetMap Nominatim geocoding with a local cache; opt-in because place names leave the machine). **Notebooks → Places** aggregates the same map across all notebooks. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); LLM modules need a text-capable Ollama model. Preset policies and module knobs live under **App → Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)).

**Transcribe (OCR)** primary chrome is vision model + Start transcription (+ optional cleanup toggle). **Compare models** runs multipass (multi-select vision models → rank + composite). Workers, force re-OCR, cleanup mode/model, prefer mode, and capability dumps sit under **Advanced**. Review shows Compare OCR attempts when multiple succeeded outputs exist. Non-local Ollama hosts still require an explicit acknowledgement checkbox because page images leave the machine.

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
| UI **Notebooks → Inbox** | Streamlit Inbox mode | Single-folder or parent-of-folders ImportRun; skip/overwrite with typed `OVERWRITE ALL`; recovery outcomes |

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.

Place-name geocoding for People & places / Places maps uses OpenStreetMap Nominatim only when the user opts in; results are cached under `data/cache/geocode.json`. Without opt-in, only already-cached coordinates are shown.
