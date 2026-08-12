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
| `models` | List vision-capable Ollama models (`--base-url`, `--all`, `--refresh`) |
| `run <project> --model …` | Run OCR (`--force`, `--workers 1|2`, `--base-url`, `--allow-remote-ollama`) |
| `export <project> [dest]` | Write selected formats (JSON, Markdown, text, HTML, EPUB, PDF) |
| `status <project>` | Print per-page status |
| `detect <project>` | Run a content detector (`--detector poetry\|todo_lists\|lists\|quotations\|beer_labels`, `--force`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

**Notebooks:** View · Search · Archive · Places · Inbox (shared page viewer for review/edit). Sidebar dropdown selects the active notebook for Workflow. **Inbox** is a foundation surface for ImportRun recovery — see **Corpus foundation** below before treating it as fully supported.

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Analyse · Export.

**Analyse** opens Run Analysis (Quick / Balanced / Thorough / Custom presets) plus product read-model tabs: Overview · Themes · Mood & tone · Moments · People & places · Summaries · Ask notebook. A shared status strip above the tabs answers notebook revision and batch health. Module ids, capability enums, and raw JSON live under **Advanced** expanders — ordinary use does not require module/cache literacy. **People & places** maps GPE/LOC/FAC entities from published NER (optional OpenStreetMap Nominatim geocoding with a local cache; opt-in because place names leave the machine). **Notebooks → Places** aggregates the same map across all notebooks. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); LLM modules need a text-capable Ollama model. Preset policies and module knobs live under **App → Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)).

**Transcribe (OCR)** primary chrome is vision model + Start transcription (+ optional cleanup toggle). Workers, force re-OCR, cleanup mode/model, and capability dumps sit under **Advanced**. Non-local Ollama hosts still require an explicit acknowledgement checkbox because page images leave the machine.

### Helper script

`./transcribe.sh` resolves a project-local `.venv` and accepts: `ui|web` (default), `cli|run …`, `install|setup`, `install-dev`, or passthrough argv to the CLI.

## Corpus foundation (not fully supported until activation gate)

Bulk-import generation ships as **foundation code** while contracts remain prospective and the [acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is still closing. Do **not** treat these as unconditionally supported production surfaces yet:

| Surface | How to invoke | Notes |
|---------|---------------|-------|
| CLI `bulk-import folder <dir>` | `transcribe bulk-import folder …` (`--policy`, `--dry-run`) | Plan/commit folder scans into the corpus |
| CLI `bulk-import status\|resume <id>` | `transcribe bulk-import status\|resume …` | Inspect or resume an ImportRun |
| CLI `corpus-doctor` | `transcribe corpus-doctor` (`--deep`) | Workspace corpus index integrity |
| UI **Notebooks → Inbox** | Streamlit Inbox mode | Plans/commits a folder via ImportRun; shows committed / skipped / failed recovery outcomes |

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.

Place-name geocoding for People & places / Places maps uses OpenStreetMap Nominatim only when the user opts in; results are cached under `data/cache/geocode.json`. Without opt-in, only already-cached coordinates are shown.
