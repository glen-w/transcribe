Type: CONTRACT
Authority: self — persisted page results, attempt lifecycle, edits, and fingerprint fields

# Page results and provenance

On-disk location and naming: [project-on-disk.md](project-on-disk.md). Export projection of these fields: [notebook-export.md](notebook-export.md).

## File identity

- Path: `results/<page_id>.json`
- `format` must be `"transcribe.page-result"`
- `schema_version` must be `1`
- Payload `page_id` must match the filename stem

## Attempts

- OCR generations are append-only attempt records (capped retention in implementation)
- Each attempt has a status in `{running, succeeded, failed, cancelled, interrupted}`
- `active_attempt_id` selects the attempt that owns current derived status / raw text
- Interrupted reconciliation: when the job lock is free, `running` attempts become `interrupted`

## Effective text

- `edited_text` is user-owned
- If `edited_text` is not `null`, effective text is the edit
- Otherwise effective text is the active attempt’s `raw_text`
- Re-running OCR must not clear a user edit

## Fingerprints (persisted)

Successful attempts store `input_fingerprint` and a canonical `fingerprint_payload` including provider, model name, model digest, **model identity verification flag**, input image hash (after preprocess), prompt hash, preprocess profile/version, and generation options.

When optional post-OCR cleanup is enabled for the job, the fingerprint also includes a `cleanup` object: mode, cleanup model name/digest/verified flag, cleanup prompt id/version/sha256, and `cleanup_validator_policy_id` / `cleanup_validator_policy_version`. When cleanup is disabled, the `cleanup` key is omitted so fingerprints remain compatible with pre-cleanup attempts.

Skip/resume policy for *jobs* (runtime): a page may be skipped only when the frozen job plan has **verified** model identity and the recomputed fingerprint matches a succeeded active attempt. Unverified model identity is non-cacheable for skip. Job execution freezes plan fields at start; see [ARCHITECTURE.md](../ARCHITECTURE.md) for shape.

## Provenance

Successful attempts carry provenance suitable for audit/export: model identity, prompt text/ids/hashes, preprocess, application version, Ollama host, render id, request id, and allowlisted provider timing/token metadata.

## Optional cleanup record

When a job plan enables cleanup, each succeeded attempt may include a `cleanup` object. Cleanup **never** changes `OCRAttempt.status`, attempt timestamps’ OCR meaning, or page success/failure: vision OCR success still yields `status=succeeded` even if cleanup fails or is rejected.

Fields:

- `execution_status`: `disabled` | `skipped_empty_source` | `provider_ok` | `provider_failed`
- `acceptance_status`: `not_applicable` | `applied` | `unchanged` | `validator_rejected`
- `mode`, `model_name`, `model_digest`, cleanup `prompt_*`, `note` (stable machine code)
- `pre_cleanup_text`: set **only** when `acceptance_status=applied` (immutable audit of vision OCR); otherwise null
- Bounded diagnostics on reject/fail: `original_length`, `candidate_length`, `length_ratio` — **rejected candidate text is not persisted**
- `cleanup_validator_policy_id` / `cleanup_validator_policy_version`

Whitespace-only vision OCR skips the cleanup model (`execution_status=skipped_empty_source`). Plan-time misconfiguration (invalid mode, missing/unsuitable cleanup model, unverified digest) rejects **job start**. Runtime model disappearance or digest drift is page-level fail-soft (`provider_failed`) and keeps vision `raw_text`.

`raw_text` and `cleanup` for a succeeded attempt are committed in one write. Interrupted `running` attempts must not leave cleaned `raw_text` without a complete `cleanup` record.
