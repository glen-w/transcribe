# Deep Test / Harden After Plan (# deep-test)

Probe and harden after a plan has been implemented. Verify the plan landed end-to-end, deepen tests, exercise real OCR workloads (fixture page / multi-page / resume), then finish with a pre-release gate.

Execute from the workspace root.

This command is **mutating when fixing issues**: fix plan gaps, test failures, and runtime errors found during OCR probes. Prefer minimal, targeted fixes. Do not expand scope into unrelated refactors or new features.

Do not publish, push, tag, or deploy unless explicitly instructed.

Do **not** modify TranscriptX. This project stays independent until a later explicit integration effort.

---

## Inputs (resolve before starting)

1. **Plan** (required): the plan just implemented — attached Cursor plan, linked plan file under `.cursor/plans/` / `docs/`, or a path the user names. If none is clear, ask once, then stop.
2. **Small page fixture** (default preference order):
   - `tests/fixtures/mini_page.png` (or `.jpg`)
   - A tiny handwritten/sample page under `tests/fixtures/`
   - If none exists, create a minimal fixture (or stop and ask) — do not pull large personal notebooks into the repo
3. **Multi-page source** (default preference order):
   - Path the user names
   - A small multi-page PDF fixture under `tests/fixtures/`
   - If none is usable, stop and ask — do not invent “large” by duplicating one page dozens of times unless the plan explicitly needs scale
4. **Ollama**: host default `http://localhost:11434`; a vision-capable model must be installed for live probes. If Ollama/model unavailable, run offline/mocked probes only and mark live steps **`skipped`**.

---

## 0. Run backup first (mandatory)

Before doing anything else, run the **backup** custom command (`# backup`). Wait for it to complete, then proceed.

When later executing `# tests` and `# pre-release`, **skip their nested backup steps** if backup already succeeded in this deep-test run (note that in the summary).

---

## 1. Plan landing review (mandatory) — fix gaps

Compare the implementation to the plan. Do not treat “mostly done” as done.

### 1.1 Checklist against the plan

For every plan phase / todo / acceptance criterion:

| Check | Action |
|-------|--------|
| Code landed | Locate symbols/files named in the plan; confirm behavior matches the written decision |
| Tests landed | Confirm planned tests exist and cover the stated cases |
| Docs landed | Confirm planned doc updates exist and match code |
| Docs + backup/restore | Any **new feature, output artifact, or setting** must be documented and covered by backup/restore (see §1.1a) |
| Explicit non-goals | Confirm out-of-scope items were not accidentally implemented |
| Contracts / schemas | Confirm versioned project artifacts, provenance fields, and invariants match the plan |

Use `git status`, `git diff`, and targeted searches. Prefer reading the plan’s todo list and marking each item `landed` / `partial` / `missing`.

### 1.1a Docs + backup/restore coverage (mandatory when the plan adds surfaces)

For every new or changed **feature**, **output**, or **setting** introduced by the plan:

| Surface | Must verify |
|---------|-------------|
| Documentation | User/dev guides and contracts mention it where appropriate; indexes (`USER_INDEX` / `DEV_INDEX` / `docs/index.md`) link it; no silent undocumented knobs or exports |
| `# backup` include/exclude | Code, config, schemas, and docs for the surface are included by `# backup`; generated/runtime data dirs are explicitly excluded so restore stays lean and correct |
| Product portability | If the surface persists under `projects/`, workspace settings, or export packages, confirm restore/reopen still finds it (schema/version fields, defaulting, migration notes). If product backup/restore is still a candidate, document the gap as residual risk — do not invent a product backup API |

Treat missing docs or backup-path drift as a **plan gap** and fix before §2 (or waive with user confirmation).

### 1.2 Fix issues

- **Missing or partial plan items:** implement the minimum fix to land them.
- **Drift from plan decisions:** correct code/docs/tests to match the plan (or stop and ask if the plan itself is wrong).
- **Broken imports, schema mismatches, obvious regressions:** fix immediately.
- Re-run focused tests for anything you change in this phase before moving on.

### 1.3 Gate

Do not proceed to §2 until every **required** plan item is landed or explicitly waived by the user. Record waived items in the final summary.

---

## 2. Run `# tests` — expand and deepen (mandatory)

Execute the **tests** custom command (`# tests`) in full (except skip backup if already done in §0).

Deep-test-specific emphasis on top of `# tests`:

- Prefer expansion around **code touched by the plan** (providers, ingest, orchestrator, persistence, export).
- Add or deepen unit/contract tests for any gap found in §1.
- Keep default suite fast/offline; do not re-enable quarantined tests without justification.
- Baseline must be green (or failures classified) before expansion; after expansion, `pytest -q` must pass.

If `# tests` surfaces production bugs related to the plan, fix them, then continue.

---

## 3. Small-page OCR probe — Python (mandatory when Ollama available)

Goal: prove the happy path on a tiny fixture via services/API (not ad-hoc Streamlit widgets). Watch logs; fix failures.

Prefer the public service/orchestrator API, for example:

```python
from pathlib import Path
# Adjust imports to the landed package API
from transcribe.services.project import ProjectService
from transcribe.services.transcription import TranscriptionOrchestrator

project_dir = Path(".test_outputs/_deep_test_mini")
# create/open project, ingest mini fixture, run transcription on pending pages
```

**Watch for:** traceback, per-page `failed` without retriable classification, missing provenance fields, persistence not updated after each page, Streamlit imports leaking into core.

**On failure:** diagnose, fix, re-run until green (or classify as environmental skip — e.g. no vision model — with user confirmation).

If Ollama is unavailable: run the same flow with a fake `VisionOCRProvider` returning canned text and note **`skipped` (live Ollama)**.

---

## 4. Multi-page / resume probe

- Ingest a small multi-page PDF or several images.
- Run transcription; interrupt/cancel once if cancel is in scope; confirm resume skips succeeded pages and retries failed/pending.
- Confirm export Markdown + structured JSON include page order and provenance.
- Prefer writing under `.test_outputs/_deep_test_*` — never into the user’s personal `projects/` tree unless they ask.

---

## 5. UI smoke (optional but preferred)

- Run `# streamlit` (or start the UI entrypoint on **port 8510**).
- **Never kill or bind port 8501** (TranscriptX). Transcribe UI is always on 8510.
- Open/create a throwaway project, import the mini fixture, run, open Review, export.
- Watch terminal logs for ERROR / Traceback.
- Do not leave long-running jobs attached to personal notebooks.

---

## 6. Run `# pre-release` (mandatory)

Execute `# pre-release` (skip nested backup if §0 already succeeded). Fix **failure** outcomes that are in scope for the plan; report warnings.

---

## Final summary

Report:

- Plan landing table (`landed` / `partial` / `missing` / `waived`)
- Docs + backup/restore coverage for new features / outputs / settings
- Tests: baseline → after expansion
- Live OCR probes: pass / fail / skipped (Ollama/model)
- Resume/cancel/export notes
- Pre-release confidence line
- Residual risks

Do not claim release approval.
