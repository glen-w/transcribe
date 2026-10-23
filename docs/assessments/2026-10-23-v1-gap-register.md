# v1 gap register (2026-10-23)

Execution checklist for a TX-class **notebook freeze**. Close these gaps; do not grow the product into TranscriptX.

Package at survey: **0.8.8**. Target tags: local **`v0.9.0`** then local **`v1.0.0`**. Push of tags is a separate request.

## Locked rules

- One wave, one branch, one PR. Do not merge from this register. Do not edit TranscriptX.
- After each wave: `# light-test` then `# deep-test` (skip nested backup when the first backup in the session succeeded).
- Light-test stays offline: fake vision provider, `tests/fixtures/mini_page.png` only, never port 8501, no full-tree pytest, no Docker install.
- 25 analysis modules stay adaptations/forks. Document honesty; do not rewrite to TX-depth stacks.
- Empty Home stays **Create** + **Import**. Open sample lives on **New notebook**.

## Waves

| Wave | Gap | Exit |
|------|-----|------|
| **0** Assessments | This folder + index links; DEV_INDEX I5 status | Five files exist and are indexed |
| **1** U2.2 | `samples/demo-notebook/` + Open sample via init/import | Offline copy → pages → Analyse Quick (no text LLM) → export |
| **2** U2.4 | README-linked Docker-first ~15 minute path | Happy path does not require contracts |
| **3** I6 nightly + templates | `nightly.yml` (offline acceptance); issue templates | Workflow has no live Ollama / 8501 |
| **4** I6 Docker CI | `docker compose build` + `make docker-smoke` on release-checks; install matrix stub | Skip (not fake-pass) when the runner has no Docker |
| **5** v1 gate docs | Severity, release-ops, manual acceptance, analysis-quality audit, module-id pin test | 0.9.0 still keys off U2+I6; these join the **1.0** checklist |
| **6** Reader ignore-pages | Hide ignored pages by default; show-ignored override | Reader and export agree |
| **7** 0.9.0 cut | Version bump after waves 1–4 | Local tag `v0.9.0` |
| **8** v1.0.0 freeze | Docs consistency + `# tests` after waves 5–7 | Local tag `v1.0.0` |

## Non-goals for this programme

- Editing TranscriptX, copying the tag kernel into TX, or runtime integration.
- Audio, speakers, diarization, voice modules, watcher, Dashboard Builder, CCv2, Playwright/Vitest.
- Rewriting topic models, NER, or wordclouds up to TX package size.
- Autobiography, Telegram import, cloud OCR, in-app training.
- Stranger-testing as a release gate.
- PyPI publish, RTD hostname go-live, optional workflow screenshot gallery.

## Status at survey

| Item | Status |
|------|--------|
| Notebook workbench (OCR, Review, Reading, Library, Analyse×25, Detect, corpus, backup) | landed |
| U2.1 Home / U2.3 Diagnostics | landed |
| U2.2 Sample / U2.4 first-run docs | open |
| I0–I5 | landed |
| I6 | open |
| 1.0 freeze declaration | open |
