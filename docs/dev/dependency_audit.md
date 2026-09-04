# Dependency audit

Runtime and extra dependencies are declared in `pyproject.toml`. There is **no** lockfile in v1; CI installs current compatible wheels on each run.

## Inventory (declared)

| Extra / profile | Packages |
|-----------------|----------|
| Core | Pillow, pymupdf, wordcloud |
| `[ui]` | streamlit, pydantic, ebooklib |
| `[export]` | ebooklib |
| `[dev]` | pytest, pytest-cov, pytest-timeout, ruff + UI extras |

Ollama is an **external** local service, not a Python dependency.

## Audit practice

Before a public tag:

1. `pip install -e '.[dev]'` into a clean venv (or CI `release-checks` log).
2. Optionally `pip-audit` / GitHub Dependabot when enabled — record findings below.
3. Waive only with owner, expiry, and reason.

## Waiver log

| Date | Package | Advisory | Severity | Decision | Expiry | Owner |
|------|---------|----------|----------|----------|--------|-------|
| — | — | — | — | No open waivers | — | — |

When adding a waiver, link the advisory and the release tag that accepted it.
