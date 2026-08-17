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
- At least one **vision-capable**, OCR-friendly model (e.g. `deepseek-ocr`, `granite3.2-vision`, `qwen2.5vl:7b`). Prefer OCR-oriented tags over general VLMs; some listed “vision” tags still fail to load on a given Ollama build — see [known_limitations.md](docs/known_limitations.md)

## How you use it

| Surface | Role |
|---------|------|
| **Streamlit UI** (`./transcribe.sh ui`) | Primary — Home / Library / Search / Archive / Places · Workflow (Import / Transcribe / Review / Analyse / Export) · View (Reading / Overview / …) · System |
| **CLI** (`./transcribe.sh cli …` / `python -m transcribe`) | Init, import, run, export, status, doctor, backup, restore |
| **Services API** | Shared by UI and CLI (`transcribe.services`) |

```bash
./transcribe.sh cli init "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli import "$TRANSCRIBE_PROJECTS_DIR/my-notebook" ./page.jpg
./transcribe.sh cli models
./transcribe.sh cli run "$TRANSCRIBE_PROJECTS_DIR/my-notebook" --model gemma3:4b
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli doctor "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
./transcribe.sh cli backup create
./transcribe.sh cli backup verify "$TRANSCRIBE_EXPORT_DIR/backups/transcribe-workspace-….zip"
```

More: [user guide](docs/user_guide.md) · [OCR](docs/runtime/ocr.md) · [analysis](docs/runtime/analysis.md) · [export](docs/runtime/export.md) · [settings](docs/runtime/settings.md) · [backup & restore](docs/backup_and_restore.md) · [public surfaces](docs/public_surfaces.md).

## What it does today

- Page-preserving projects (`transcribe.project` + per-page `transcribe.page-result`)
- Local Ollama vision OCR with content fingerprints for skip/resume; multipass compare / prefer / promote / composite / fine-tune export; timeout and model-load fail-fast circuits
- Immutable OCR attempts; human edits live in `edited_text`; page delete from the viewer
- Workspace Library / Archive / Search (activity-bin filter, strip paging) over your notebooks directory
- Unified Import / Transcribe targets (this notebook vs batch) with live job progress; corpus bulk import supported
- Visual declutter on import (and explicit re-apply); Prompt Hub + Detect (poetry, lists, beer labels, …)
- Analyse presets (Quick / Balanced / Thorough / Custom); product read-models under View (corpus/period compare on Overview/Mood; Moments and page-series jump-to-page → Reading)
- Portable export (`transcribe.notebook` JSON + Markdown + plain text + HTML/EPUB/PDF)
- **Full-workspace backup / restore** (ZIP of notebooks + corpus + config; CLI + Settings → Configuration) — [backup_and_restore.md](docs/backup_and_restore.md)
- **Core notebook analysis** on transcribed text (Overview, Themes with People, Mood with Moments, Summaries with Ask, Detect) with project-local `analysis/` results — [ROADMAP.md](docs/ROADMAP.md)

Invariants live in **contracts**, not this README — see [CONTRACT_INDEX.md](docs/CONTRACT_INDEX.md).

## Architecture (brief)

File-shaped authoritative storage (project + per-page results + optional `analysis/`), OCR behind a provider boundary, rebuildable archive SQLite cache, CLI and Streamlit sharing the same services. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Direction

OCR notebook core is stable (import → run → review → export). **Core analysis modules are shipped**; current product work is the **usability wave** — **U0–U1** and **U3** done; open track **U2** first-run operability; **U4** corpus gate green — [usability_wave_plan.md](docs/usability_wave_plan.md) · [ROADMAP.md](docs/ROADMAP.md). Package **0.8.5** sits on maintainer CI and release hygiene (I0–I3); remaining infra **I4–I6** plus **U2** enable **0.9.0**, then **0.9-1** unfamiliar testing → **1.0**. After 1.0 autobiography is planned and gated. Deferred reinterpretations and `ocr_quality` are **not scheduled**. Transcribe does **not** depend on TranscriptX; a future handoff seam is documented in [INTEGRATION_SEAM.md](docs/INTEGRATION_SEAM.md).

## Privacy

By default Transcribe talks to `http://localhost:11434` (native) or `http://host.docker.internal:11434` (Docker → host Ollama). A non-local Ollama host means page images leave this machine; UI/CLI warn and require acknowledgement.

## Links

- [Product](docs/PRODUCT.md) · [User index](docs/USER_INDEX.md) · [Developer index](docs/DEV_INDEX.md) · [Contract index](docs/CONTRACT_INDEX.md) · [Docs hub](docs/index.md)
- [User guide](docs/user_guide.md) · [Developer quickstart](docs/developer_quickstart.md) · [Contributing](CONTRIBUTING.md)
- [Architecture](docs/ARCHITECTURE.md) · [Installation](docs/runtime/installation.md) · [Docker](docs/runtime/docker.md) · [Settings](docs/runtime/settings.md)
- [Known limitations](docs/known_limitations.md) · [Roadmap](docs/ROADMAP.md) · [Usability wave](docs/usability_wave_plan.md) · [Terms](docs/TERMS.md)
- [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · License: MIT · Third-party: [NOTICE](NOTICE)
