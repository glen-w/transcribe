Review and Expand Test Suite (# tests)

Review the Transcribe test suite for health, coverage gaps, and quarantined/skipped tests; then propose and, where safe, implement targeted test expansions.

Execute from the workspace root.

⸻

0. Run backup first (mandatory)

Before doing anything else, run the backup custom command (# backup). Wait for it to complete, then proceed.

⸻

1. Operating rules

Primary goal: improve test confidence without broad production refactors.

* Bias toward tests-only changes.
* Do not run destructive clean-test-artifacts flows.
* If production-code changes appear necessary, stop and report the proposed fix unless it is a trivial import/path compatibility correction.
* If the default suite is failing before changes, do not expand tests until failures are understood and classified.
* Do not re-enable quarantined tests by default.
* New tests must not be marked quarantined, slow, requires_docker, requires_ollama, requires_models, or requires_network unless explicitly justified.
* Keep default test runs **fast and offline** (mock the Ollama provider; no live HTTP to `:11434`).

⸻

2. Test Artifact Cleanup

Cleanup is disabled.

Do not run destructive cleanup flows. Only report that cleanup is disabled unless explicitly requested to run a preview-only cleanup audit.

⸻

3. Review Phase

3.1 Run and summarize current suite

If `tests/` or pytest config is missing (greenfield), report that and stop after recommending an initial smoke layout; do not invent a huge suite unprompted.

Otherwise run:

```bash
pytest --co -q
pytest -q
```

If debugging a failure, use:

```bash
pytest -x
```

Report:

* Total collected tests
* Passed / failed / skipped / xfailed / xpassed
* Collection errors or import failures
* Whether baseline is green before adding tests

⸻

3.2 Structure and markers

List test directories under `tests/`, preferring mirrors of package areas when present:

`domain`, `providers`, `ingest`, `preprocess`, `prompts`, `services`, `persistence`, `export`, `ui` (UI tests sparingly), `integration`, `smoke`

Inspect `pytest.ini` / `pyproject.toml` pytest config.

Confirm markers including, where present:

`smoke`, `unit`, `integration`, `slow`, `requires_ollama`, `requires_docker`, `requires_network`, `quarantined`

Confirm default `addopts` excludes heavy/quarantined/live-Ollama tests.

⸻

3.3 Quarantined and skipped tests

Identify:

* Quarantined files and reasons
* Skipped-at-collection files (missing modules, obsolete imports, etc.)
* Tests skipped due to removed modules or API changes

Report counts and whether quarantined tests should remain, be updated, or be removed.

Do not re-enable quarantined tests unless updated to current APIs and passing.

⸻

3.4 Coverage and gaps

If coverage is available and reasonable, run:

```bash
pytest --cov=src/transcribe --cov-report=term-missing -q
```

If coverage cannot be run, manually compare `src/transcribe/` packages to `tests/`.

Focus on high-leverage areas:

* Domain objects + schema_version / effective text (`edited_text` vs `raw_text`)
* Ollama provider transport + vision-model discovery (mocked HTTP)
* Ingest ordering (images + PDF page render paths with fixtures)
* Orchestrator resume / cancel / per-page failure isolation
* Persistence load/save round-trips
* Export Markdown / plain text / structured JSON provenance fields
* Provider protocol boundaries (no Streamlit imports in core)

Avoid low-value UI widget tests unless they catch a real regression.

⸻

4. Expansion Phase

4.1 Propose first

Before writing tests, list a short prioritized plan (file targets + cases). Prefer:

* Failing or missing coverage next to recent changes
* Contract/unit tests over broad integration
* Fake/stub `VisionOCRProvider` instead of live Ollama

4.2 Implement

* Add focused tests; keep them deterministic.
* Do not mark new tests `requires_ollama` unless the user asked for a live probe and a fixture model is documented.
* Update fixtures under `tests/fixtures/` (tiny PNG/PDF) rather than copying real notebooks.

4.3 Re-run

```bash
pytest -q
```

Must pass before finishing. Summarize added tests and remaining gaps.

⸻

## Execution rules

- Run from workspace root.
- Backup first (`# backup`).
- Prefer tests-only diffs.
- Default suite stays offline.
- End with: baseline status, what was added, coverage notes, and open risks.
