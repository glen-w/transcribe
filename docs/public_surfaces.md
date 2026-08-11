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
| `detect <project>` | Run a content detector (`--detector poetry`, `--force`, `--list`) |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

**Notebooks:** View · Search · Archive (shared page viewer for review/edit). Sidebar dropdown selects the active notebook for Workflow.

**Workflow:** New notebook · Import · Transcribe (OCR) · Review · Analyse · Export.

**Analyse** opens Run Analysis (Quick / Balanced / Thorough / Custom presets, ported from TranscriptX) plus published-result tabs: Overview · Themes · Mood & tone · Moments · Summaries · Ask notebook. Analysis is project-local under `analysis/` ([contracts/analysis-run-storage.md](contracts/analysis-run-storage.md)); LLM modules need a text-capable Ollama model. Preset policies and module knobs live under **App → Settings** ([contracts/workspace-settings.md](contracts/workspace-settings.md)).

### Helper script

`./transcribe.sh` resolves a project-local `.venv` and accepts: `ui|web` (default), `cli|run …`, `install|setup`, `install-dev`, or passthrough argv to the CLI.

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.
