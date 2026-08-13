Type: ARCHITECTURE
Authority: system shape and ownership boundaries only — invariants live in CONTRACT docs

# Architecture

Transcribe keeps a small ownership model on purpose.

## Shape

```text
Streamlit UI (8510) ──┐
                      ├──► services (project, ingest, job, export, archive, doctor)
CLI ──────────────────┘              │
                                     ▼
                    workspace (data/)
                    ├── corpus/          # corpus-index + import-runs (bulk import)
                    ├── projects/<…>/    # one managed notebook directory each
                    │     ├── project.json
                    │     ├── sources/ + pages/ renders
                    │     ├── results/<page_id>.json
                    │     ├── analysis/   (optional until first analysis artifact)
                    │     ├── detection/  (optional until first detection artifact)
                    │     └── page_metrics/ (optional until first ink/blankness publish)
                    └── cache/archive.sqlite   (disposable)
```

## Ownership boundaries

| Concern | Owner |
|---------|-------|
| Corpus identity, notebook order, workspace locks | [contracts/notebook-corpus.md](contracts/notebook-corpus.md) |
| Managed originals, fingerprints, duplicates | [contracts/source-asset.md](contracts/source-asset.md) |
| Bulk ImportRun / plan / resume | [contracts/import-run.md](contracts/import-run.md) |
| Corpus/notebook integrity + bulk-import acceptance gate | [contracts/corpus-integrity.md](contracts/corpus-integrity.md) |
| Durable notebook directory layout + per-notebook journal | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| OCR generations + edits | Per-page results — [contracts/page-result.md](contracts/page-result.md) |
| Analysis inputs / results / storage / eligibility | [contracts/analysis-document.md](contracts/analysis-document.md) · [analysis-result.md](contracts/analysis-result.md) · [analysis-run-storage.md](contracts/analysis-run-storage.md) · [notebook-eligibility.md](contracts/notebook-eligibility.md) |
| Prompt definitions / detection findings / detection runs | [contracts/prompt-definition.md](contracts/prompt-definition.md) · [contracts/detection-definition.md](contracts/detection-definition.md) · [contracts/detection-finding.md](contracts/detection-finding.md) · [contracts/detection-run-storage.md](contracts/detection-run-storage.md) |
| Page ink / blankness / hue metrics | [contracts/page-metrics.md](contracts/page-metrics.md) |
| Portable interchange | Export snapshot — [contracts/notebook-export.md](contracts/notebook-export.md) |
| OCR HTTP | `VisionOCRProvider` (Ollama implementation) |
| UI widgets | `transcribe.ui` only — must not invent OCR/persistence rules |
| Workspace search/timeline | `ArchiveService` over rebuildable SQLite |

## Key runtime objects (shape, not schema)

- **ProjectService** — load/save settings and metadata with load→modify→validate→write under the mutation lock; reconciles interrupted attempts when the job lock is free
- **IngestService** — stages, journals, promotes, then commits the manifest; recovers incomplete journals on open/load
- **JobCoordinator / JobPlan** — freezes model identity, prompt, preprocess, options, targets, provider binding, and optional OCR cleanup identity (mode/model/digest/validator policy) at job start; workers consume the plan, not live UI settings. Multipass reuses frozen single-model plans with `activate=false` / `pass_id`, then rank + composite ([contracts/ocr-multipass.md](contracts/ocr-multipass.md)).
- **OcrBatchRun** — durable multi-notebook OCR batch ([contracts/ocr-batch-run.md](contracts/ocr-batch-run.md)); UI Workflow → Transcribe → Batch
- **AnalysisBatchRun** — durable multi-notebook Analyse batch ([contracts/analysis-batch-run.md](contracts/analysis-batch-run.md)); UI Workflow → Analyse → Batch (orchestration only; publish stays per-notebook)
- **ExportService** — one coherent snapshot, then multi-format promote
- **ArchiveService** — disposable FTS cache with WAL/busy timeout and delete-and-rebuild on corruption; cheap TTL short-circuit uses a workspace mutation-generation token (callers bump after project mutations)
- **DoctorService** — structural integrity (+ optional deep hashing); quarantined ingest journals reported as errors
- **CorpusDoctorService / CorpusIndexStore / ImportRunStore** — workspace corpus authority under `data/corpus/` (runtime-normative; see corpus contracts)
- **AnalysisCoordinator / AnalysisRunPlan / AnalysisRunner / AnalysisStorage** — project-scoped async batch runs freeze an `AnalysisRunPlan` (modules, EffectiveConfig, text-model identity) and execute under `.transcribe.analysis.lock`; publish under `analysis/`; UI freshness via `module_freshness` / `planned_cache_identity` (UI must not hand-build cache identities). Mid-run settings apply to the next run only; crash/reopen marks orphaned attempts/runs `interrupted` without clobbering published results
- **DetectionRunner / DetectionStorage / prompt_engine / Prompt Hub** — prompt-backed page/window detectors (`poetry`, `todo_lists`, `lists`, `quotations`, `beer_labels`, custom); publish findings under `detection/`; Settings → Prompts resolves OCR/cleanup/detection definitions with workspace overrides; freshness via `detector_freshness` / planned cache identity
- **PageMetricsService** — Pillow ink coverage / blankness / dominant hue over active renders; publish under `page_metrics/`; cache identity = algorithm version + ordered `(page_id, render_sha256)` (not text Analyse)
- **Visual declutter** — Pillow scanner-border crop at import and via `ProjectService.reapply_visual_declutter` (Settings → Configuration); provenance on renders ([contracts/source-asset.md](contracts/source-asset.md))
- **Ollama discovery cache** — thread-safe model metadata keyed by normalized base URL + transport timeout; providers stay lightweight execution clients

## Explicit non-goals for the core architecture

- Making SQLite the system of record
- Introducing a task queue or multi-process worker fleet for v1
- Coupling to TranscriptX libraries

Shipped core analysis + deferred / future / out-of-scope dispositions: [ROADMAP.md](ROADMAP.md). Docs authority model: [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md).
