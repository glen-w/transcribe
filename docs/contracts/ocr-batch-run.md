Type: CONTRACT
Authority: self — workspace OcrBatchRun lifecycle for sequential multi-notebook OCR. Does not replace per-notebook JobCoordinator / page-result authority.

# OCR batch runs

Related: [page-result.md](page-result.md), [import-run.md](import-run.md), [notebook-corpus.md](notebook-corpus.md), [ocr-multipass.md](ocr-multipass.md), [public_surfaces.md](../public_surfaces.md).

## Role

`OcrBatchRun` is a **workspace** record of “same OCR plan × N notebooks”. The plan is either **single-model** or **multipass** (compare models). It does **not** preallocate page IDs and does **not** own transcription text. Per-page results remain `transcribe.page-result` under each notebook. Per-notebook `JobCoordinator` / `MultiPassCoordinator` (fingerprint skip, job lock, cancel-after-current-page) are the execution engines.

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
| `mode` | `single` \| `multipass` (default `single` when absent — legacy runs) |
| `vision_model_names` | Ordered vision models; required length ≥2 when `mode=multipass`; ignored/empty for single |
| `multipass_cleanup_enabled` | Vision-phase cleanup during multipass (default `false`) |
| `settings` | Frozen `OCRSettings.as_dict()` applied to each notebook at item start. For multipass, `model_name` is the first vision model (compatibility). Text/cleanup models, prefer mode, and `auto_activate_composite` come from settings. |
| `settings_fingerprint` | SHA-256 of canonical `{settings, force, mode, vision_model_names, multipass_cleanup_enabled}` |
| `import_run_id` | Optional; set when the batch was seeded from an ImportRun |
| `items` | Ordered notebooks; unique `notebook_id` |

### Item fields

| Field | Rule |
|-------|------|
| `notebook_id` / `title` / `managed_relpath` | Locator + display |
| `state` | See item states |
| `pages_*` | Counts from the inner job / multipass vision progress |
| `error_message` | Optional |
| `pass_id` | Optional; set when a multipass item starts so resume can continue that notebook’s multipass job record |

### Item states

`pending` \| `running` \| `completed` \| `skipped` \| `failed` \| `cancelled`

- Empty notebooks are `skipped`.
- A notebook that finishes with a mix of succeeded and failed pages is `completed` with `pages_failed` recorded (retry those pages later).
- Crash while `running`: resume resets that item to `pending`; for multipass, if `pass_id` is set and the job record is incomplete, resume that pass; otherwise start a new pass (fingerprint skip still applies to vision phases).

## Execution

1. Resolve each item to a managed notebook root (corpus index, else project-folder scan).
2. Write frozen settings onto that notebook.
3. **Single:** `JobCoordinator.run_blocking`. **Multipass:** `MultiPassCoordinator.run_blocking` (or `resume_blocking` when resuming an incomplete `pass_id`) with the frozen `vision_model_names` / cleanup / auto-activate flags. Per-notebook multipass job records remain under that notebook’s `jobs/`.
4. One notebook at a time (Ollama is the bottleneck; per-project job lock still applies).
5. Cancel: stop after the current page (and for multipass, do not start remaining models on that notebook), do not start remaining notebooks (`cancelled` items).

## Non-goals

- Parallel notebooks in one process
- Reopening the corpus-integrity acceptance gate
- Auto-multipass on import
