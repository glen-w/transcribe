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
| **Streamlit UI** (`./transcribe.sh ui`) | Primary — Notebooks (View/Search/Archive) · Workflow (Transcribe/Analyse/Export) |
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
- Local Ollama vision OCR with content fingerprints for skip/resume; multipass compare / prefer / promote / composite / fine-tune export
- Immutable OCR attempts; human edits live in `edited_text`; page delete from the viewer
- Workspace Archive / View / Search (activity-bin filter, strip paging) over your projects directory
- Unified Import / Transcribe targets (this notebook vs batch) with live job progress; corpus bulk import supported
- Visual declutter on import (and explicit re-apply); Prompt Hub + Detect (poetry, lists, beer labels, …)
- Analyse presets (Quick / Balanced / Thorough / Custom) with product read-models
- Portable export (`transcribe.notebook` JSON + Markdown + plain text + HTML/EPUB/PDF)
- **Core notebook analysis** on transcribed text (Overview, Themes, Mood, Moments, Places, Summaries, Ask) with project-local `analysis/` results — [ROADMAP.md](docs/ROADMAP.md)

Invariants live in **contracts**, not this README — see [CONTRACT_INDEX.md](docs/CONTRACT_INDEX.md).

## Architecture (brief)

File-shaped authoritative storage (project + per-page results + optional `analysis/`), OCR behind a provider boundary, rebuildable archive SQLite cache, CLI and Streamlit sharing the same services. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Direction

OCR notebook core is stable (import → run → review → export). **Core analysis modules are shipped**; current product work is the **usability wave** (trust / Analyse product UX → first-run operability → daily workbench; corpus bulk import supported) — [usability_wave_plan.md](docs/usability_wave_plan.md) · [ROADMAP.md](docs/ROADMAP.md). Deferred reinterpretations and `ocr_quality` are **not scheduled**. Transcribe does **not** depend on TranscriptX; a future handoff seam is documented in [INTEGRATION_SEAM.md](docs/INTEGRATION_SEAM.md).

## Privacy

By default Transcribe talks to `http://localhost:11434` (native) or `http://host.docker.internal:11434` (Docker → host Ollama). A non-local Ollama host means page images leave this machine; UI/CLI warn and require acknowledgement.

## Links

- [Product](docs/PRODUCT.md) · [User index](docs/USER_INDEX.md) · [Developer index](docs/DEV_INDEX.md) · [Contract index](docs/CONTRACT_INDEX.md)
- [User guide](docs/user_guide.md) · [Developer quickstart](docs/developer_quickstart.md)
- [Architecture](docs/ARCHITECTURE.md) · [Installation](docs/runtime/installation.md) · [Docker](docs/runtime/docker.md)
- [Known limitations](docs/known_limitations.md) · [Roadmap](docs/ROADMAP.md) · [Usability wave](docs/usability_wave_plan.md) · [Terms](docs/TERMS.md)
- License: MIT · Third-party: [NOTICE](NOTICE)
