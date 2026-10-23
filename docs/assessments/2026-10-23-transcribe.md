# Transcribe assessment (2026-10-23)

Workspace: this repository. Package **0.8.8**. Branch `main`. Latest tag `v0.8.8`.

## Layout

| Area | Role |
|------|------|
| `src/transcribe/domain/` | Notebook / page / OCR attempt models |
| `src/transcribe/services/` | Shared kernel for UI and CLI |
| `src/transcribe/providers/` | Ollama vision and text clients |
| `src/transcribe/ingest/`, `corpus/` | Import and bulk ImportRun |
| `src/transcribe/analysis/` | 25 modules + coordinator |
| `src/transcribe/detection/` | Prompt / lexical / names detectors |
| `src/transcribe/tagging/` | Host-agnostic tag kernel + catalog |
| `src/transcribe/ui/` | Streamlit shell on port **8510** |
| `tests/` | Offline default suite; acceptance under `tests/acceptance/` |
| `scripts/release/` | Hygiene, Sphinx, Pages assemble |
| `docs/` | Markdown authority; Sphinx builds the same tree |

CLI entry: `transcribe` / `python -m transcribe`. UI entry: `transcribe-ui`. Compose service `transcribe-web` binds **8510**. Port **8501** is reserved for TranscriptX.

## Shipped product surfaces

| Surface | Evidence |
|---------|----------|
| OCR multipass, prefer/promote, timeout + model-load circuits | `services/multipass.py`, `services/job.py`, `providers/ollama.py` |
| Review workbench | `ui/review_workbench.py`, `ui/review_queue.py` |
| Reading, Library, Search | `ui/archive_views.py`, `services/archive.py` |
| Organisation tags | `tagging/kernel.py`, `services/tags.py` |
| Export JSON / Markdown / text / HTML / EPUB / PDF | `services/export.py` and `export_*.py` |
| Fine-tune export (OCR; train outside the app) | `services/finetune_export.py` |
| Corpus bulk import / bulk OCR / bulk Analyse | `corpus/`, CLI `bulk-import` / `bulk-run` / `bulk-analyse` |
| 25 analysis modules | `analysis/modules/*.py` `MODULE_ID` |
| Detect (built-ins + custom) | `detection/registry.py` |
| Workspace backup / restore | `services/workspace_backup.py` |
| Doctor + Diagnostics | CLI `doctor` / `corpus-doctor`; `ui/diagnostics.py` |
| Home (Create / Import + Ollama health) | `ui/home.py` |
| Settings hub | `ui/settings_hub.py` |
| Pages + Sphinx (I4–I5) | `docs/conf.py`, `website/`, `.github/workflows/pages.yml` |

CLI commands: `init`, `import`, `models`, `run`, `status`, `multipass`, `export-finetune`, `export`, `doctor`, `detect`, `bulk-import`, `corpus-doctor`, `backup`, `restore`, `bulk-run`, `bulk-analyse`.

Nav groups: unlabeled primary (Home, Library, Search) → Workflow → View → System. Specs in `ui/navigation.py`.

## Analysis modules (25)

`stats`, `lexical_diversity`, `understandability`, `ner`, `sentiment`, `epistemic_markers`, `entity_sentiment`, `keyphrases`, `wordclouds`, `topic_modeling`, `bertopic`, `semantic_similarity`, `topic_shift`, `emotion`, `fine_grained_emotion`, `contextual_emotion`, `affect_tension`, `moments`, `highlights`, `summary`, `insights`, `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary`.

Pins and `semantic_class` (almost all `adaptation`; `moments` is a `fork`): [analysis_port_pins.md](../dev/analysis_port_pins.md). These are notebook adaptations, not TX-depth packages.

## Tests and CI

| Metric (survey) | Value |
|-----------------|--------|
| `test_*.py` files | about 134 |
| `def test_` functions | about 1122 |
| Default pytest | offline; excludes `quarantined`, `requires_*`, `slow`, `integration`, `release_only` |
| PR CI | `compose-config`, `lint`, `tests` (3.10–3.12, coverage on 3.11), `docs`, blocking `release-checks` |

Acceptance gates: `tests/acceptance/hardening/`, `corpus/`, `ocr_lifecycle/`.

## Docs

Indexes: [index.md](../index.md), [USER_INDEX.md](../USER_INDEX.md), [DEV_INDEX.md](../DEV_INDEX.md), [CONTRACT_INDEX.md](../CONTRACT_INDEX.md). Twenty-six contracts under `docs/contracts/`. Sphinx + GitHub Pages landed. RTD hostname remains owner-gated.

## Open for 0.9.0 (own plans)

| ID | Gap |
|----|-----|
| **U2.2** | No `samples/` tree; no Open-sample path. Empty Home stays Create + Import only. |
| **U2.4** | README / install docs are Docker-preferred but the consolidated “first notebook in 15 minutes” acceptance is still open. |
| **I6** | No `.github/workflows/nightly.yml`; no `.github/ISSUE_TEMPLATE/`; Docker image not in `release-checks`. |
| Doc drift | [DEV_INDEX.md](../DEV_INDEX.md) still said I5 was remaining while the infra plan marks I5 done. Fixed in the wave-0 index pass. |

U0–U1, U3, U4 corpus gate, I0–I5 are landed in code and plans.

## Non-goals already written

Autobiography / context importers, cloud OCR, audio / diarization, OpenCV preprocess, in-app training, TranscriptX library coupling, stranger-testing as a release gate. See [PRODUCT.md](../PRODUCT.md) and [ROADMAP.md](../ROADMAP.md) scope lean.

## Boundary checks

- No `import transcriptx` / `from transcriptx` under `src/` or `tests/`.
- `tests/unit/test_core_no_streamlit.py` keeps Streamlit out of the kernel.
- JSON-on-disk is the source of truth; SQLite FTS is disposable.
