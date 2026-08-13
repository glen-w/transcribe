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
pytest -q                 # default offline suite
pytest -q -m smoke         # pre-release critical-path subset
```

Default suite is **offline** (fake vision provider / recorded LLM doubles). Do not require a live Ollama daemon for PR confidence. Optional live probes belong in deep-test / local scripts under `.test_outputs/`.

### Markers

Configured in `pyproject.toml`. Default `addopts` **excludes** `quarantined`, `requires_ollama`, `requires_docker`, `requires_network`, `slow`, and `integration`.

| Marker | Meaning |
|--------|---------|
| `smoke` | Fast critical-path gate used by `# pre-release` |
| `integration` | **Live** local Ollama (or other live dependency) only |
| `quarantined` | Pytest exclusion — unrelated to corpus/journal quarantine |

Offline multi-component detector tests belong under `tests/services/` (or `tests/unit/`) and must **not** use `@pytest.mark.integration`, or they would be deselected by default.

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

## Formatting / lint

```bash
black src tests          # line-length 100, target py310 ([tool.black] in pyproject.toml)
ruff check src tests     # same line-length / py310
ruff check --fix src tests
```

Do not run `black .` at repo root (can touch `.venv`). Prefer `.[dev]` extras for pytest; install `black` / `ruff` on the host or in the venv when formatting.

## Docs when you change behaviour

Follow [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md): update the owning CONTRACT (or PRODUCT/ARCHITECTURE) rather than inventing rules in guides.
