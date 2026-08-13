Type: CONTRACT
Authority: self — workspace OcrBatchRun lifecycle for sequential multi-notebook OCR. Does not replace per-notebook JobCoordinator / page-result authority.

# OCR batch runs

Related: [page-result.md](page-result.md), [import-run.md](import-run.md), [notebook-corpus.md](notebook-corpus.md), [public_surfaces.md](../public_surfaces.md).

## Role

`OcrBatchRun` is a **workspace** record of “same OCR settings × N notebooks”. It does **not** preallocate page IDs and does **not** own transcription text. Per-page results remain `transcribe.page-result` under each notebook. Per-notebook `JobCoordinator` (fingerprint skip, job lock, cancel-after-current-page) is the execution engine.

Bulk import never auto-starts OCR. After an ImportRun commits, the UI may offer **Transcribe imported notebooks**, which seeds a batch from that run’s committed `notebook_id`s.

## Storage

- Directory: `{TRANSCRIBE_DATA_DIR}/corpus/ocr-runs/`
- File: `{ocr_run_id}.json`
- Format: `transcribe.ocr-batch-run`
- `schema_version`: `1`

## Fields

| Field | Rule |
|-------|------|
| `ocr_run_id` | Stable UUID; filename stem |
| `status` | `pending` \| `running` \| `completed` \| `partial` \| `failed` \| `cancelled` |
| `force` | When true, inner jobs ignore matching fingerprints |
| `settings` | Frozen `OCRSettings.as_dict()` applied to each notebook at item start |
| `settings_fingerprint` | SHA-256 of canonical `{settings, force}` |
| `import_run_id` | Optional; set when the batch was seeded from an ImportRun |
| `items` | Ordered notebooks; unique `notebook_id` |

### Item states

`pending` \| `running` \| `completed` \| `skipped` \| `failed` \| `cancelled`

- Empty notebooks are `skipped`.
- A notebook that finishes with a mix of succeeded and failed pages is `completed` with `pages_failed` recorded (retry those pages later).
- Crash while `running`: resume resets that item to `pending`; fingerprint skip avoids redoing succeeded pages.

## Execution

1. Resolve each item to a managed notebook root (corpus index, else project-folder scan).
2. Write frozen settings onto that notebook, then `JobCoordinator.run_blocking`.
3. One notebook at a time (Ollama is the bottleneck; per-project job lock still applies).
4. Cancel: stop after the current page, do not start remaining notebooks (`cancelled` items).

## Non-goals

- Multipass / compare-models over a batch
- Parallel notebooks in one process
- Reopening the corpus-integrity acceptance gate
