# Transcribe

**Transcribe** is a local-first handwritten notebook OCR workbench.

Import JPEG/PNG/PDF pages into a project on your machine, transcribe them with a locally hosted [Ollama](https://ollama.com) vision model, review and correct page text side-by-side, then export Markdown, plain text, and a portable `transcribe.notebook` JSON artifact — without sending your pages to a cloud OCR SaaS.

Product definition (authoritative): [docs/PRODUCT.md](docs/PRODUCT.md).  
Known limits: [docs/known_limitations.md](docs/known_limitations.md).

## Get started

### Local venv (recommended on the host)

Python 3.10+. Dependencies stay in `.venv`.

```bash
cd /path/to/transcribe
cp .env.example .env          # optional path / Ollama overrides
chmod +x transcribe.sh
./transcribe.sh setup         # creates .venv and installs .[ui]
./transcribe.sh ui            # → http://127.0.0.1:8510/
```

Point durable workspace dirs outside the clone when you want data to survive repo wipes:

```bash
# in .env
TRANSCRIBE_PROJECTS_DIR=/Users/you/Documents/transcribe-projects
TRANSCRIBE_INBOX_DIR=/Users/you/Documents/notebook-scans
TRANSCRIBE_EXPORT_DIR=/Users/you/Documents/transcribe-exports
```

### Docker (no host Python packages)

```bash
cp .env.example .env
# set HOST_PROJECTS_DIR to an absolute path outside this repository
docker compose up --build transcribe-web
# → http://127.0.0.1:8510/
```

Details: [docs/runtime/docker.md](docs/runtime/docker.md) · [docs/runtime/installation.md](docs/runtime/installation.md).

### Prerequisites

- A running Ollama server (`http://localhost:11434` by default)
- At least one **vision-capable** model (e.g. `gemma3:4b`, `llava:7b`, `qwen3-vl:8b`)

## How you use it

| Surface | Role |
|---------|------|
| **Streamlit UI** (`./transcribe.sh ui`) | Primary — Archive, Notebooks, Search, Workflow |
| **CLI** (`./transcribe.sh cli …` / `python -m transcribe`) | Init, import, run, export, status, doctor |
| **Services API** | Shared by UI and CLI (`transcribe.services`) |

```bash
./transcribe.sh cli init "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./page.jpg
./transcribe.sh cli models
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

More: [user guide](docs/user_guide.md) · [public surfaces](docs/public_surfaces.md).

## What it does today

- Page-preserving projects (`transcribe.project` + per-page `transcribe.page-result`)
- Local Ollama vision OCR with content fingerprints for skip/resume
- Immutable OCR attempts; human edits live in `edited_text`
- Workspace Archive / Notebooks / Search over your projects directory
- Portable export (`transcribe.notebook` JSON + Markdown + plain text)

Invariants live in **contracts**, not this README — see [CONTRACT_INDEX.md](docs/CONTRACT_INDEX.md).

## Architecture (brief)

File-shaped authoritative storage (project + per-page results), OCR behind a provider boundary, rebuildable archive SQLite cache, CLI and Streamlit sharing the same services. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Direction

Stabilise the OCR notebook core (import → run → review → export) before analysis-module ports. Planned ports from TranscriptX ideas: [ROADMAP.md](docs/ROADMAP.md). Transcribe does **not** depend on TranscriptX; a future handoff seam is documented in [INTEGRATION_SEAM.md](docs/INTEGRATION_SEAM.md).

## Privacy

By default Transcribe talks to `http://localhost:11434` (native) or `http://host.docker.internal:11434` (Docker → host Ollama). A non-local Ollama host means page images leave this machine; UI/CLI warn and require acknowledgement.

## Links

- [Product](docs/PRODUCT.md) · [User index](docs/USER_INDEX.md) · [Developer index](docs/DEV_INDEX.md) · [Contract index](docs/CONTRACT_INDEX.md)
- [User guide](docs/user_guide.md) · [Developer quickstart](docs/developer_quickstart.md)
- [Architecture](docs/ARCHITECTURE.md) · [Installation](docs/runtime/installation.md) · [Docker](docs/runtime/docker.md)
- [Known limitations](docs/known_limitations.md) · [Roadmap](docs/ROADMAP.md) · [Terms](docs/TERMS.md)
- License: MIT · Third-party: [NOTICE](NOTICE)
