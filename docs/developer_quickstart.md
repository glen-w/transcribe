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
pip install -e '.[dev]'      # pytest, ruff, coverage extras; use '.[ui]' for Streamlit only
cp .env.example .env         # optional
```

Or `./transcribe.sh install-dev`.

## Tests

Named lanes match CI. Full marker policy: [tests/README.md](../tests/README.md).

```bash
make test-smoke           # critical-path smoke marker
make test-fast            # default offline suite (same as pytest -q)
make test-contracts       # tests/contracts/
make test-acceptance      # hardening + corpus + OCR lifecycle
make lint                 # ruff critical selects (CI lint job)
make docker-smoke         # Compose loopback bind assert
make docs                 # Sphinx HTML (requires pip install -e '.[docs]')
make test-coverage        # default suite + coverage fail-under
make release-hygiene      # secrets / tracked-data / stale-refs / root docs
```

Default suite is **offline** (fake vision provider / recorded LLM doubles). Do not require a live Ollama daemon for PR confidence. Optional live probes belong in deep-test / local scripts under `.test_outputs/`.

### Markers

Configured in `pyproject.toml`. Default `addopts` **excludes** `quarantined`, `requires_ollama`, `requires_docker`, `requires_network`, `slow`, `integration`, and `release_only`. See [tests/README.md](../tests/README.md).

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

Do not run `black .` at repo root (can touch `.venv`). `.[dev]` includes pytest, pytest-cov, pytest-timeout, and ruff. Install `black` / `pre-commit` on the host or in the venv when formatting. CI gates ruff **critical** selects only (not full `black --check`). Optional: `pre-commit install` using `.pre-commit-config.yaml`.

## Docs when you change behaviour

Follow [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md): update the owning CONTRACT (or PRODUCT/ARCHITECTURE) rather than inventing rules in guides. Docs surfaces: [dev/docs_architecture.md](dev/docs_architecture.md). Hosted HTML is the same Markdown (`make docs`); new `docs/contracts/` and `docs/dev/` pages are picked up by glob toctrees. Optional live rebuild: `sphinx-autobuild docs docs/_build/html` after `pip install -e '.[docs]'`.
