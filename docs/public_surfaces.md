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
| `export <project> [dest]` | Write notebook JSON + Markdown + plain text |
| `status <project>` | Print per-page status |
| `doctor <project>` | Integrity report (`--deep` hashes source/render files) |

### UI modes

Archive · Notebooks · Search · Workflow (shared page viewer for review/edit).

### Helper script

`./transcribe.sh` resolves a project-local `.venv` and accepts: `ui|web` (default), `cli|run …`, `install|setup`, `install-dev`, or passthrough argv to the CLI.

## Explicitly unsupported

- Binding Transcribe UI to port **8501** by project convention (reserved for TranscriptX when both are developed side by side)
- Cloud OCR providers as shipped surfaces
- Treating `data/cache/archive.sqlite` as a migration or backup authority
- Calling into TranscriptX APIs from Transcribe (no dependency)

## Privacy support policy

Default Ollama hosts are loopback / Docker→host bridge. Non-local hosts require explicit acknowledgement (`--allow-remote-ollama` / UI checkbox) because page images leave the machine.
