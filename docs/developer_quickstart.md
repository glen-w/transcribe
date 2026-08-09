Type: GUIDE
Authority: contributor orientation and workflows — does not own contracts

# Developer quickstart

## Mental model

1. **Projects on disk** are the system of record
2. **Services** own mutations (UI/CLI are thin)
3. **JobPlan** freezes OCR execution for one run
4. **Archive SQLite** is a rebuildable cache under the workspace data dir

Shape: [ARCHITECTURE.md](ARCHITECTURE.md). Rules: [CONTRACT_INDEX.md](CONTRACT_INDEX.md).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'      # pytest; use '.[ui]' for Streamlit
cp .env.example .env         # optional
```

Or `./transcribe.sh install-dev`.

## Tests

```bash
pytest -q
```

Default suite is **offline** (fake vision provider). Do not require a live Ollama daemon for PR confidence. Optional live probes belong in deep-test / local scripts under `.test_outputs/`.

Pytest marker present today: `integration` (live Ollama) — not selected by default.

## Useful entrypoints

| Area | Module |
|------|--------|
| CLI | `transcribe.__main__` |
| UI | `transcribe.ui.app` |
| Project RMW | `transcribe.services.project` |
| Ingest | `transcribe.ingest` |
| OCR jobs | `transcribe.services.job` |
| Export | `transcribe.services.export` |
| Archive cache | `transcribe.services.archive` |
| Analysis runner / storage | `transcribe.analysis.runner` · `transcribe.analysis.storage` |
| Core modules | `transcribe.analysis.modules` |
| Validation | `transcribe.domain.validation` |
| Doctor | `transcribe.services.doctor` |
| Ollama provider | `transcribe.providers.ollama` |

## Extension points

- New vision backends: implement `VisionOCRProvider` and keep UI/CLI on services
- New preprocess profiles: extend `transcribe.preprocess` and validation allowlists together
- New analysis modules: register in `transcribe.analysis.modules`, pin in [dev/analysis_port_pins.md](dev/analysis_port_pins.md), follow [ROADMAP.md](ROADMAP.md)
- Do not put OCR, analysis, or persistence rules inside Streamlit widgets

## Docs when you change behaviour

Follow [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md): update the owning CONTRACT (or PRODUCT/ARCHITECTURE) rather than inventing rules in guides.
