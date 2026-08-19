Type: GUIDE
Authority: local install and environment operations only — does not define project-format invariants

# Installation

Operational guide only (installation, extras, environment, Ollama prereqs). For on-disk project layout see [contracts/project-on-disk.md](../contracts/project-on-disk.md). For behaviour and invariants, see [CONTRACT_INDEX.md](../CONTRACT_INDEX.md). Supported entrypoints: [public_surfaces.md](../public_surfaces.md).

For a quick start, see the [README](../../README.md).

## Native (venv)

Python **3.10+** (`requires-python` in `pyproject.toml`).

```bash
cd /path/to/transcribe
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'     # Streamlit UI (wordcloud is a default dependency)
# or
pip install -e '.[dev]'    # pytest + UI extras
# optional EPUB export without full UI:
pip install -e '.[export]' # ebooklib only
```

Helper (creates `.venv` and installs `.[ui]`):

```bash
chmod +x transcribe.sh
./transcribe.sh setup
./transcribe.sh ui
```

Developer extras: `./transcribe.sh install-dev`.

Console scripts after install: `transcribe`, `transcribe-ui`.

### Install extras (honesty)

| Extra | What it adds |
|-------|----------------|
| *(core)* | Pillow, PyMuPDF, wordcloud — CLI OCR / export text+PDF without Streamlit |
| `[ui]` | Streamlit + pydantic + ebooklib (primary interactive surface) |
| `[export]` | ebooklib for EPUB without pulling Streamlit |
| `[dev]` | pytest, pytest-cov, pytest-timeout, ruff, tomli (Python 3.10) + UI extras |
| `[docs]` | Sphinx + MyST + Furo (`make docs`); not required to run the app |

There is no published PyPI package today — install from this repository.

## Environment variables

Copy `.env.example` → `.env`. Repo-root `.env` is loaded by `transcribe._bootstrap` without overriding variables already set in the shell/Compose.

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

Docker host mounts use `HOST_*` counterparts — see [docker.md](docker.md). Prefer absolute paths **outside the git clone** for projects, inbox, and exports.

## Ollama

Install and run Ollama separately. Pull at least one **vision-capable**, OCR-friendly model before the first OCR run (prefer OCR-oriented tags over general VLMs). Native default URL: `http://localhost:11434`.

Model discovery and caveats: [ocr.md](ocr.md) · [known_limitations.md](../known_limitations.md).

## First checks

```bash
./transcribe.sh cli models
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli corpus-doctor
```

In the UI: **System → Diagnostics**.

## Next

- Golden path: [../user_guide.md](../user_guide.md)
- Settings: [settings.md](settings.md)
- OCR: [ocr.md](ocr.md)
- Analysis: [analysis.md](analysis.md)
- Export: [export.md](export.md)
- Docker: [docker.md](docker.md)
- Developer loops: [../developer_quickstart.md](../developer_quickstart.md)
