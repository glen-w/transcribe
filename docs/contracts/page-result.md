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

Skip/resume policy for *jobs* (runtime): a page may be skipped only when the frozen job plan has **verified** model identity and the recomputed fingerprint matches a succeeded active attempt. Unverified model identity is non-cacheable for skip. Job execution freezes plan fields at start; see [ARCHITECTURE.md](../ARCHITECTURE.md) for shape.

## Provenance

Successful attempts carry provenance suitable for audit/export: model identity, prompt text/ids/hashes, preprocess, application version, Ollama host, render id, request id, and allowlisted provider timing/token metadata.
