# TranscriptX assessment (2026-10-23)

Sibling repo: `/Users/89298/Documents/transcriptx`. Package **1.0.1**. Tags **`v1.0.0`** and **`v1.0.1`**. HEAD was about 13 commits past `v1.0.1` (Granite STT + library archive unreleased). Classifier in `pyproject.toml` still said Beta.

This product is a local **audio transcript** analysis workbench. Streamlit default port **8501**. Transcribe must not depend on it.

## Layout (portable vs not)

| Package | Role | Copy into Transcribe? |
|---------|------|------------------------|
| `src/transcriptx/core/` | Engine: pipeline, ~50 analysis modules, domain transcript | Pattern only (adapters / registry) |
| `src/transcriptx/app/` | UI-agnostic controllers | Pattern only |
| `src/transcriptx/web/` | Streamlit shell, settings hub, CCv2 bridges | IA / settings chrome pattern |
| `src/transcriptx/io/` | Import adapters, tag validation | Adapter registry pattern; **not** the tag catalog kernel |
| `src/transcriptx/services/` | Host STT, watcher, speaker studio | **No** (audio) |
| `packages/transcriptx_workspaces/` | Vitest/Vite CCv2 workspaces | **No** for v1 |

## Shipped (audio product)

- BYO import plus in-app STT (WhisperMLX, WhisperX Docker, Granite on HEAD).
- Diarization ladder, Speaker Identification, speaker profiles, Groups.
- Library (including archive flag on HEAD), Search, CCv2 karaoke reader, Corrections Studio.
- Analysis presets Quick / Balanced / Thorough / Custom; large module set including voice/prosody and multi-speaker interaction modules.
- Workspace backup ZIP (`transcriptx.workspace-backup`), Settings hub, Diagnostics, schema-epoch gate.
- Export Overview/Artifacts ZIP, optional EPUB, Library export-by-tag.

## Maintainer infrastructure (1.0 gate shape)

| Piece | TranscriptX |
|-------|-------------|
| PR CI | Blocking: `compose-config`, `lint`, `smoke`. Advisory: NLP/RAG tests, docs, release-checks, workspaces |
| Nightly | `nightly.yml`: contracts + fast + coverage; integration-core |
| Coverage badge | `coverage-badge.yml` |
| Pages | `pages.yml` website + Sphinx |
| Tests | pytest + AppTest GUI acceptance + Playwright + Vitest for CCv2 |
| Release docs | `docs/dev/pre_release_roadmap_1_0.md`, severity triage, release ops, manual acceptance, install/trust/perf matrices |
| Scripts | `scripts/release/*` plus `clean_env_audit.sh`, `image_pip_check.sh`, perf envelope helpers |

Transcribe should steal **nightly offline lanes, issue templates, Docker-in-release-checks, severity/ops/manual-acceptance docs** — not TX’s smoke-only PR policy. Transcribe already runs the full offline matrix on every PR.

## Portable patterns

- Nav groups: primary / Workflow / View / System.
- Settings hub with segmented tabs (content differs by product).
- Workspace backup ZIP with a typed format id and role roots.
- Doctor / Diagnostics page.
- Analysis module registry + presets + result envelopes.
- Hosted docs (Sphinx + modest `website/` + Pages).
- First-run honesty: docs-first; TX **removed** Guided/demo/checklist modes after trying them.

## Do not copy (audio / speakers / timed media)

STT providers, diarization, karaoke timings, voice feature family, Speaker ID workstation, inbox-watch / recordings mounts, interaction/QA/echoes/contagion modules, Compose “engines outside analysis image”, Playwright/Vitest workspace packs, Dashboard Builder as a 1.0 Transcribe requirement.

## Tagging honesty

TX has organisation **string** tags (`io/tag_validation.py`, Library filter/export). It does **not** ship Transcribe’s `personal_corpus.tag-catalog` kernel. “Shared with TX Theme F” in Transcribe contracts is a **future copy boundary**, not current TX code.

## Maturity line

Public 1.0 is tagged. ROADMAP “Current state” still mentioning a 0.9.x track is stale relative to tags. Post-1.0 work continues (ASR ladder, library archive, Theme E/H). PyPI and RTD hostname go-live were not 1.0 blockers.
