# Transcribe maintainer lanes. CI and `# pre-release` call these names.
# Sphinx / Pages / full Docker image smoke grow in I4–I6.

.DEFAULT_GOAL := help

ifeq ($(wildcard .venv/bin/python),)
PYTHON ?= python3
else
PYTHON ?= .venv/bin/python
endif
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help lint test-smoke test-fast test-contracts test-acceptance test-coverage docker-smoke docs docs-clean release-hygiene

help:
	@echo "Transcribe Makefile"
	@echo ""
	@echo "Testing:"
	@echo "  test-smoke        Critical-path smoke marker (CI / pre-release first gate)"
	@echo "  test-fast         Default offline suite (same as pytest -q)"
	@echo "  test-contracts    Offline tests under tests/contracts/"
	@echo "  test-acceptance   Hardening + corpus + OCR lifecycle acceptance"
	@echo "  test-coverage     Default offline suite + coverage (.coveragerc fail_under)"
	@echo ""
	@echo "Quality:"
	@echo "  lint              Ruff critical selects on src/transcribe (CI lint job)"
	@echo "  docker-smoke      Compose loopback bind (+ docker compose config when Docker exists)"
	@echo "  release-hygiene   Secrets, tracked-data, stale-refs, strict root/archive hygiene"
	@echo ""
	@echo "Docs (stubs until I4):"
	@echo "  docs              Point at the Markdown corpus (Sphinx lands in I4)"
	@echo "  docs-clean        No-op until Sphinx artifacts exist"
	@echo ""
	@echo "Usage: make test-smoke && make test-fast"

lint:
	@echo "Ruff critical + unused on src/transcribe..."
	@$(PYTHON) -m ruff check src/transcribe --select E9,F63,F7,F82,F401,F841

test-smoke:
	@echo "Running smoke gate..."
	@$(PYTEST) -q -m "smoke and not quarantined"

test-fast:
	@echo "Running default offline suite..."
	@$(PYTEST) -q

test-contracts:
	@echo "Running contract tests..."
	@$(PYTEST) -q tests/contracts -m "not quarantined"

test-acceptance:
	@echo "Running acceptance gates..."
	@$(PYTEST) -q tests/acceptance -m "not quarantined and not requires_ollama and not requires_docker and not requires_network and not slow and not integration"

test-coverage:
	@echo "Default offline suite with coverage (see .coveragerc fail_under)..."
	@$(PYTEST) -q --cov=src/transcribe --cov-config=.coveragerc --cov-report=term-missing --cov-report=xml:coverage.xml

docker-smoke:
	@echo "Compose bind honesty..."
	@bash scripts/release/assert_compose_bind.sh

release-hygiene:
	@echo "Release hygiene (I2)..."
	@bash scripts/secrets_check.sh
	@$(PYTHON) scripts/release/check_tracked_data.py
	@bash scripts/release/stale_refs.sh
	@$(PYTHON) scripts/release/repo_hygiene_audit.py --strict --checks root_md,archive_banners

docs:
	@echo "Markdown corpus is docs/ (indexes: docs/index.md)."
	@echo "Sphinx HTML build lands in infrastructure track I4."
	@echo "See docs/dev/docs_architecture.md"

docs-clean:
	@echo "No Sphinx build artifacts yet (I4). Nothing to clean."
