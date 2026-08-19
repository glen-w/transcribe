Type: CONTRACT
Authority: self — persisted page results, attempt lifecycle, edits, fingerprints, preference, and multipass comparison

# Page results and provenance

On-disk location and naming: [project-on-disk.md](project-on-disk.md). Export projection of these fields: [notebook-export.md](notebook-export.md). Multipass orchestration: [ocr-multipass.md](ocr-multipass.md). Preference ledger: [ocr-preference.md](ocr-preference.md).

## File identity

- Path: `results/<page_id>.json`
- `format` must be `"transcribe.page-result"`
- `schema_version` must be `1`
- Payload `page_id` must match the filename stem
- Additive fields (`preferred_attempt_id`, `comparison`, attempt `attempt_kind` / `pass_id` / `source_attempt_ids`) are optional on older files; readers treat missing as defaults

## Attempts

- OCR generations are append-only attempt records (capped retention in implementation; default cap **40**)
- Each attempt has a status in `{running, succeeded, failed, cancelled, interrupted}`
- `attempt_kind`: `vision` (default) | `composite`
- `pass_id` (optional) ties attempts from one multipass run
- Composite attempts carry `source_attempt_ids` (vision attempt ids used as merge inputs) and optional `composite_note`
- `active_attempt_id` selects the attempt that owns current derived status / raw text
- `preferred_attempt_id` (optional) records user preference; may differ from active under `prefer_only` mode
- Interrupted reconciliation: when the job lock is free, `running` attempts become `interrupted`
- Retention must never drop `active`, `preferred`, the latest succeeded attempt per `(model_name, digest)`, or the latest composite for the current `pass_id` when possible within the cap

## Effective text

- `edited_text` is user-owned
- If `edited_text` is not `null`, effective text is the edit
- Otherwise effective text is the active attempt’s `raw_text`
- Re-running OCR must not clear a user edit
- Promoting / preferring an attempt must not clear `edited_text` unless the user explicitly chooses adopt-new under `prefer_promote_with_edit_gate`

Optional additive page-level provenance (not per-token):

- `effective_text_origin`: `ocr_attempt` \| `composite` \| `human_selected` \| `human_corrected` — how the current effective text was established. Absent on legacy files.
- `reviewed_text_fingerprint` / `reviewed_evidence_fingerprint` — identity of effective text and OCR evidence (merge-input vision attempt ids + current composite id) when the page was marked **reviewed**. Required for a valid `reviewed` status on `PageIndex.review_status`.
- `source_disagreement_count` / `agreement_ratio` — optional cached **source-only** alignment signals (raw vision attempts; never counting composite or the editor as votes)

A stored `reviewed` is valid only while both fingerprints match. Central invalidation on write (and a load-time repair) moves `reviewed` → `needs_attention` when effective text, `active_attempt_id`, current merged draft, or newly available source OCR evidence changes. Skip is sticky; reviewed is not.

## Composite / merged draft

Composite attempts (`attempt_kind=composite`) are an LLM reconciliation of independent vision attempts, not another OCR vote. `source_attempt_ids` lists the vision attempts consumed. A composite is **current** iff that set equals the latest succeeded vision attempt per `(model_name, digest)` that would feed a new merge; otherwise it is **stale**. Stale composites are retained (append-only). At most one current composite is the live merged draft. User-facing name: **Merged draft**. Rank lists never include composites.

## Prefer / promote

Prefer modes (workspace default + per-notebook OCR override). User-facing guide: [runtime/ocr.md](../runtime/ocr.md#notebook-ocr-settings).

| Mode | Review UI label | Prefer behaviour |
|------|-----------------|------------------|
| `prefer_is_promote` (default) | Notebook default = current text | Sets `preferred_attempt_id` and `active_attempt_id` |
| `prefer_only` | Notebook default only (stats / fine-tune) | Sets `preferred_attempt_id` only |
| `prefer_promote_with_edit_gate` | Notebook default + current, with edit gate | Sets preferred and active; if `edited_text` is set, require `keep_edit` or `adopt_new` before applying |

Promote (`set_active_attempt`) always sets `active_attempt_id` to a succeeded attempt and does not clear edits.

When `auto_activate_composite` is true (default), multipass sets active (and preferred under `prefer_is_promote`) from a succeeded merged draft and seeds Transcription — see [ocr-multipass.md](ocr-multipass.md) activation phase.

## Comparison record

Optional `comparison` on the page (last successful multipass rank):

- `pass_id`, `ranked_attempt_ids` (vision only, best-first), optional per-entry score/rationale
- Ranker model / prompt provenance
- Composite attempts must **never** appear in `ranked_attempt_ids`

## Fingerprints (persisted)

Successful attempts store `input_fingerprint` and a canonical `fingerprint_payload` including provider, model name, model digest, **model identity verification flag**, input image hash (after preprocess), prompt hash, preprocess profile/version, and generation options.

Vision generate always sends a `num_predict` cap (default 4096). The **default** cap is omitted from hashed `generation_options` so skip/resume stays compatible with attempts that only stored `temperature`. A non-default `num_predict` is included and changes the fingerprint.

When optional post-OCR cleanup is enabled for the job, the fingerprint also includes a `cleanup` object: mode, cleanup model name/digest/verified flag, cleanup prompt id/version/sha256, and `cleanup_validator_policy_id` / `cleanup_validator_policy_version`. When cleanup is disabled, the `cleanup` key is omitted so fingerprints remain compatible with pre-cleanup attempts.

Skip/resume policy for *single-model jobs* (runtime): a page may be skipped only when the frozen job plan has **verified** model identity and the recomputed fingerprint matches a succeeded **active** attempt. Unverified model identity is non-cacheable for skip.

Skip/resume for *multipass* vision phases: skip when verified identity matches **any** succeeded vision attempt fingerprint on the page (not only active), so rematching models stay cacheable while accumulating candidates.

Job execution freezes plan fields at start; see [ARCHITECTURE.md](../ARCHITECTURE.md) for shape. Generation writes may pass `activate=false` so multipass does not flip active until promotion / auto-composite policy.

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
