Type: GUIDE
Authority: local install and environment operations only — does not define project-format invariants

# Installation

## Native (venv)

```bash
cd /path/to/transcribe
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'     # Streamlit UI (+ wordcloud for Analyse word themes)
# or
pip install -e '.[dev]'    # pytest (+ UI extras including wordcloud)
```

Helper (creates `.venv` and installs `.[ui]`):

```bash
chmod +x transcribe.sh
./transcribe.sh setup
./transcribe.sh ui
```

Console scripts after install: `transcribe`, `transcribe-ui`.

Requires Python **3.10+** (`requires-python` in `pyproject.toml`).

## Environment variables

Copy `.env.example` → `.env`. Repo-root `.env` is loaded by `transcribe._bootstrap` without overriding variables already set in the shell/Compose.

| Variable | Role |
|----------|------|
| `TRANSCRIBE_PROJECTS_DIR` | Notebook projects root |
| `TRANSCRIBE_INBOX_DIR` | Optional scans inbox |
| `TRANSCRIBE_EXPORT_DIR` | Optional export root |
| `TRANSCRIBE_DATA_DIR` | Workspace data (caches, etc.) |
| `TRANSCRIBE_OLLAMA_BASE_URL` | Ollama server root URL |
| `TRANSCRIBE_HOST` / `TRANSCRIBE_PORT` | UI listen (default port **8510**) |
| `TRANSCRIBE_PYTHON` | Interpreter for `transcribe.sh` venv creation |

Docker host mounts use `HOST_*` counterparts — see [docker.md](docker.md).

## Ollama

Install and run Ollama separately. Pull a vision-capable model before first OCR run. Native default URL: `http://localhost:11434`.

## Next

- User flows: [../user_guide.md](../user_guide.md)
- Developer loops: [../developer_quickstart.md](../developer_quickstart.md)
- Surfaces: [../public_surfaces.md](../public_surfaces.md)
