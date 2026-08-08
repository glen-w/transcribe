# Transcribe

Local-first handwritten notebook OCR using [Ollama](https://ollama.com) vision models.

Import JPEG/PNG/PDF pages into a project directory, transcribe with a locally hosted vision model, review and correct side-by-side, then export Markdown/plain text plus a portable `transcribe.notebook` JSON artifact.

## Requirements

- Python 3.10+ **or** Docker
- A running Ollama server with at least one vision-capable model
- Optional: Streamlit UI (included via `.[ui]` / Docker image)

## Local venv (recommended on the host)

Dependencies stay inside `.venv` so they do not collide with other projects' pinned stacks.

```bash
cd /path/to/transcribe
cp .env.example .env          # optional path / Ollama overrides
chmod +x transcribe.sh
./transcribe.sh setup         # creates .venv and installs .[ui]
./transcribe.sh ui            # → http://127.0.0.1:8510/
```

Manual equivalent:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'        # or '.[dev]' for pytest
```

Point workspace dirs outside the clone when you want durable data (same env names as Docker):

```bash
# in .env
TRANSCRIBE_PROJECTS_DIR=/Users/you/Documents/transcribe-projects
TRANSCRIBE_INBOX_DIR=/Users/you/Documents/notebook-scans
TRANSCRIBE_EXPORT_DIR=/Users/you/Documents/transcribe-exports
```

## Docker (no host Python packages)

Follows the TranscriptX pattern: host dirs outside the repo, `HOST_*` mounts, `TRANSCRIBE_*` app paths, optional `docker-compose.override.yml`.

```bash
cp .env.example .env
# set HOST_PROJECTS_DIR to an absolute path outside this repository
docker compose up --build transcribe-web
# → http://127.0.0.1:8510/
```

Details: [docs/runtime/docker.md](docs/runtime/docker.md).

## CLI quick start

```bash
./transcribe.sh init "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./page.jpg
./transcribe.sh models
./transcribe.sh run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model llama3.2-vision
./transcribe.sh export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

Or with an activated venv: `python -m transcribe …` / `transcribe …`.

## Streamlit UI

Runs on **port 8510** by default (`.streamlit/config.toml` / `TRANSCRIBE_PORT`) so it does not collide with TranscriptX on 8501.

```bash
./transcribe.sh ui
# or: transcribe-ui
# or: streamlit run src/transcribe/ui/app.py
```

## Privacy

By default Transcribe talks to `http://localhost:11434` (native) or `http://host.docker.internal:11434` (Docker → host Ollama). Configuring a non-local Ollama host means page images leave this machine; the UI/CLI will warn and require acknowledgement.

## Design notes

- Page-preserving project format (`transcribe.project` + per-page `transcribe.page-result`)
- Workspace **Archive / Notebooks / Search** modes over `TRANSCRIBE_PROJECTS_DIR`, with a shared page viewer
- Portable interchange export (`transcribe.notebook`) with no required absolute paths
- Content fingerprints for skip/resume; immutable OCR attempts; human edits in `edited_text`
- No cloud providers; no TranscriptX dependency (future seam documented in `docs/INTEGRATION_SEAM.md`)

## License

MIT. See `NOTICE` for third-party attributions.
