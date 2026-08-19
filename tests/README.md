# Transcribe tests: how to run locally

Lane names here match the root `Makefile` and `.github/workflows/ci.yml`. Default pytest stays **offline** (fake vision provider / recorded LLM doubles). Do not require a live Ollama daemon for PR confidence.

## Quick commands (single source of truth)

| Command | What it runs |
|---------|----------------|
| `make test-smoke` | `@pytest.mark.smoke` critical-path subset |
| `make test-fast` / `pytest -q` | Default offline suite (`pyproject.toml` `addopts`) |
| `make test-contracts` | `tests/contracts/` (offline storage/shape) |
| `make test-acceptance` | `tests/acceptance/` (hardening + corpus + OCR lifecycle) |
| `make test-coverage` | Default suite + coverage (`.coveragerc` `fail_under`; I3) |
| `make lint` | Ruff critical selects on `src/transcribe` (same as CI `lint`) |
| `make docker-smoke` | Compose loopback bind assert |
| `make docs` | Sphinx HTML from `docs/` Markdown (`pip install -e '.[docs]'`) |

`# pre-release` runs smoke then the default offline suite (Makefile targets when present).

## CI lane order and time budgets

**PR order (0.7 / I1):** Compose bind → Ruff critical → Smoke → default offline suite on Python **3.10 / 3.11 / 3.12**.

**PR add-ons (0.8 / I3):** `release-checks` (secrets, tracked-data, stale refs, compose assert, package build/import). Coverage on Python 3.11 via `make test-coverage`.

**PR add-ons (I4):** `docs` job — `pip install -e '.[docs]'` then `make docs` (Sphinx HTML artifact).

**Not in PR CI yet (I5–I6):** GitHub Pages, nightly heavier acceptance, full `docker compose build` image smoke.

Time budgets (target ceilings):

- `test-smoke` ≤ 5 min
- `test-contracts` ≤ 5 min
- `test-fast` (default offline) ≤ 15 min
- `test-acceptance` ≤ 15 min (subset of default; included in `test-fast` today)

## Markers in this repo

Configured in `pyproject.toml`. Default `addopts` **excludes** `quarantined`, `requires_ollama`, `requires_docker`, `requires_network`, `slow`, and `integration`.

| Marker | Meaning |
|--------|---------|
| `smoke` | Fast critical-path gate used by CI and `# pre-release` |
| `unit` | Isolated unit tests (optional tagging; not required) |
| `integration` | **Live** local Ollama (or other live dependency) only — never for offline doubles |
| `slow` | Intentionally slow tests |
| `requires_ollama` | Live Ollama HTTP required |
| `requires_docker` | Docker daemon required |
| `requires_network` | Outbound network required |
| `quarantined` | Temporarily excluded from the default suite (pytest marker, not corpus quarantine) |
| `contract` | Optional; `make test-contracts` selects by path today (no mass-retag) |
| `release_only` | Optional future packaging smoke; not in the default suite |

### Policy

- Offline multi-component detector/service tests live under `tests/services/` (or `tests/unit/`) and must **not** use `@pytest.mark.integration`.
- `smoke` is additive: those tests also run in the default suite unless they carry an excluded marker.
- Do not add `requires_*` / `slow` / `quarantined` to new tests unless the environment contract is real.
- Optional `contract` / `release_only` markers may be added without retagging the whole tree.

## Layout

| Path | Role |
|------|------|
| `tests/unit/` | Isolated unit tests |
| `tests/services/` | Service-layer tests with fakes |
| `tests/contracts/` | Persistence/shape contracts |
| `tests/acceptance/` | Product exit gates (hardening, corpus, OCR lifecycle) |
| `tests/ingest/` · `tests/export/` · `tests/providers/` · `tests/persistence/` | Focused packages |
| `tests/fixtures/` | Tiny tracked binaries (allowlisted) |
| `tests/release/` | Hygiene script smoke (I2) |

## Environment

CI isolates writable roots via `TRANSCRIBE_DATA_DIR`, `TRANSCRIBE_PROJECTS_DIR`, `TRANSCRIBE_INBOX_DIR`, and `TRANSCRIBE_EXPORT_DIR`. Local runs may use repo `data/` (gitignored).

Live OCR probes belong in deep-test / local scripts under `.test_outputs/`, not the default suite.

## I0 inventory (docs / scripts)

Root Markdown allowlist intent (enforced in I2 `repo_hygiene_audit.py`): `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`. New root `*.md` files belong under `docs/`.

Release kit under `scripts/release/` (**I2**, 0.8.0): secrets/denylist, tracked-data allowlist, stale refs, repo hygiene, compose-bind. `# pre-release` prefers those scripts. Tag authority: [docs/dev/release_governance.md](../docs/dev/release_governance.md).
