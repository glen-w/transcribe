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
                    on-disk project (authority)
                    ├── project.json
                    ├── sources/ + pages/ renders
                    ├── results/<page_id>.json
                    └── analysis/   (optional until first analysis artifact)
                                     │
                     workspace archive.sqlite (cache only)
```

## Ownership boundaries

| Concern | Owner |
|---------|-------|
| Durable notebook state | Project directory — [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| OCR generations + edits | Per-page results — [contracts/page-result.md](contracts/page-result.md) |
| Analysis inputs / results / storage / eligibility | [contracts/analysis-document.md](contracts/analysis-document.md) · [analysis-result.md](contracts/analysis-result.md) · [analysis-run-storage.md](contracts/analysis-run-storage.md) · [notebook-eligibility.md](contracts/notebook-eligibility.md) |
| Portable interchange | Export snapshot — [contracts/notebook-export.md](contracts/notebook-export.md) |
| OCR HTTP | `VisionOCRProvider` (Ollama implementation) |
| UI widgets | `transcribe.ui` only — must not invent OCR/persistence rules |
| Workspace search/timeline | `ArchiveService` over rebuildable SQLite |

## Key runtime objects (shape, not schema)

- **ProjectService** — load/save settings and metadata with load→modify→validate→write under the mutation lock; reconciles interrupted attempts when the job lock is free
- **IngestService** — stages, journals, promotes, then commits the manifest; recovers incomplete journals on open/load
- **JobCoordinator / JobPlan** — freezes model identity, prompt, preprocess, options, targets, provider binding, and optional OCR cleanup identity (mode/model/digest/validator policy) at job start; workers consume the plan, not live UI settings
- **ExportService** — one coherent snapshot, then multi-format promote
- **ArchiveService** — disposable FTS cache with WAL/busy timeout and delete-and-rebuild on corruption; cheap TTL short-circuit uses a workspace mutation-generation token (callers bump after project mutations)
- **DoctorService** — structural integrity (+ optional deep hashing)
- **AnalysisRunner / AnalysisStorage** — project-local core analysis modules over `AnalysisDocument`; publish under `analysis/`; UI freshness via `module_freshness` / `planned_cache_identity` (UI must not hand-build cache identities)
- **Ollama discovery cache** — thread-safe model metadata keyed by normalized base URL + transport timeout; providers stay lightweight execution clients

## Explicit non-goals for the core architecture

- Making SQLite the system of record
- Introducing a task queue or multi-process worker fleet for v1
- Coupling to TranscriptX libraries

Shipped core analysis + deferred / future / out-of-scope dispositions: [ROADMAP.md](ROADMAP.md). Docs authority model: [dev/CONTRIBUTING.md](dev/CONTRIBUTING.md).
