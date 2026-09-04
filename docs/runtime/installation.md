# Installation

**Most people:** the native helper below, then the [user guide](../user_guide.md).
This page is the normal install path. Pip extras, environment variables, and
developer installs are under [Advanced](#advanced).

You also need a running [Ollama](https://ollama.com) server and at least one
**OCR-friendly vision model** before the first transcription.

## Native (recommended on the host)

Python **3.10+**. There is no published PyPI package — clone this repository.

```bash
cd /path/to/transcribe
cp .env.example .env          # optional path / Ollama overrides
chmod +x transcribe.sh
./transcribe.sh setup         # creates .venv and installs the UI extra
./transcribe.sh ui            # → http://127.0.0.1:8510/
```

Point notebooks, scans, and exports **outside the clone** when you want data to
survive repo wipes:

```bash
# in .env
TRANSCRIBE_PROJECTS_DIR=/Users/you/Documents/transcribe-projects
TRANSCRIBE_INBOX_DIR=/Users/you/Documents/notebook-scans
TRANSCRIBE_EXPORT_DIR=/Users/you/Documents/transcribe-exports
```

## Docker

No host Python packages. Copy `.env.example` to `.env` and set
**`HOST_PROJECTS_DIR`** to an absolute path **outside this repository**.

```bash
cp .env.example .env          # set HOST_PROJECTS_DIR
docker compose up --build transcribe-web
# → http://127.0.0.1:8510/
```

Ollama stays on the host. Compose notes: [docker.md](docker.md).

## After install

1. Confirm Ollama is up: **System → Diagnostics**, or `./transcribe.sh cli models`.
2. Follow [From a scan to a readable notebook](../user_guide.md#from-a-scan-to-a-readable-notebook).
3. If the first model returns empty text or times out, pick an OCR-oriented tag
   from the [model matrix](ocr_model_matrix.md) rather than a general VLM.

## Troubleshooting

- **Nothing in the vision picker** — Ollama is not reachable, or no vision tag is
  installed. Default URL: `http://localhost:11434`. Pull an OCR-friendly model,
  then **Refresh** on the Transcribe page.
- **Empty OCR / `empty_output`** — thinking vision models (for example `gemma4`)
  often return no text. Prefer OCR-oriented tags. [Known limitations](../known_limitations.md).
- **Docker cannot see notebooks** — `HOST_PROJECTS_DIR` must be an absolute path
  outside the repo. [docker.md](docker.md).
- **"No module named streamlit"** after a manual pip install — install the UI
  extra: `pip install -e '.[ui]'`, or re-run `./transcribe.sh setup`.

## Advanced

### Manual venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'
# developer extras: pip install -e '.[dev]'
# EPUB without Streamlit: pip install -e '.[export]'
```

`./transcribe.sh install-dev` installs `.[dev]`. Console scripts after install:
`transcribe`, `transcribe-ui`.

### Install extras

| Extra | What it adds |
|-------|----------------|
| *(core)* | Pillow, PyMuPDF, wordcloud — CLI OCR / text+PDF export without Streamlit |
| `[ui]` | Streamlit + pydantic + ebooklib (primary interactive surface) |
| `[export]` | ebooklib for EPUB without pulling Streamlit |
| `[dev]` | pytest, ruff, coverage + UI extras |
| `[docs]` | Sphinx (`make docs`); not required to run the app |

### Environment variables

Copy `.env.example` → `.env`. Repo-root `.env` is loaded without overriding
variables already set in the shell or Compose.

| Variable | Role |
|----------|------|
| `TRANSCRIBE_PROJECTS_DIR` | Notebook projects root |
| `TRANSCRIBE_INBOX_DIR` | Optional scans inbox |
| `TRANSCRIBE_EXPORT_DIR` | Optional export root |
| `TRANSCRIBE_DATA_DIR` | Workspace data (caches, config, corpus) |
| `TRANSCRIBE_OLLAMA_BASE_URL` | Ollama server root URL |
| `TRANSCRIBE_HOST` / `TRANSCRIBE_PORT` | UI listen (default port **8510**) |
| `TRANSCRIBE_BIND_HOST` | Compose publish bind (default `127.0.0.1`) |
| `TRANSCRIBE_PYTHON` | Interpreter for `transcribe.sh` venv creation |

Docker host mounts use `HOST_*` counterparts — [docker.md](docker.md).

### First checks (CLI)

```bash
./transcribe.sh cli models
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli corpus-doctor
```

Developer loops: [developer quickstart](../developer_quickstart.md).
