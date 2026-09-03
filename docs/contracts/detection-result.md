Type: CONTRACT
Authority: self — durable detection result envelope, attempt vs outcome separation, and capability presentation

# Detection result

Durable envelope for a detector run (published or historical). Storage rules: [detection-run-storage.md](detection-run-storage.md). Findings: [detection-finding.md](detection-finding.md).

## Identity

- `format` must be `"transcribe.detection-result"`
- `schema_version` must be `1`
- Unsupported `schema_version` → refuse

## Envelope (v1) — required fields

| Field | Required | Notes |
|-------|----------|-------|
| `format` | yes | `"transcribe.detection-result"` |
| `schema_version` | yes | `1` |
| `notebook_id` | yes | Canonical `project.id` |
| `detector_id` | yes | Detector identity |
| `detector_version` | yes | Detector version |
| `cache_identity` | yes | Full identity per detection-run-storage |
| `scope_fingerprint` | yes | Input scope hash |
| `attempt_state` | yes | `running` \| `succeeded` \| `failed` \| `cancelled` \| `interrupted` |
| `outcome` | yes | `success` \| `skipped_not_applicable` \| `unavailable_dependency` \| `insufficient_data` \| `failed` |
| `capability` | yes | UI capability (mirrors analysis vocabulary) |
| `provenance` | yes | App version, detector version |
| `warnings` | yes | Array of `{code, message}` |
| `config_fingerprint` | yes | Detector configuration subset |
| `findings` | yes | Array of DetectionFinding objects (may be empty) |
| `pages_scanned` | yes | Page IDs processed |
| `windows_scanned` | yes | Count of windows evaluated |

Optional when applicable:

| Field | Notes |
|-------|-------|
| `attempt_id` | Run attempt identifier |
| `published` | Whether this artifact is the published pointer |
| `partial` | `true` when some windows failed but others succeeded |
| `prompt_provenance` | `{prompt_id, version}` |
| `model_provenance` | `{model_name, model_digest, input_mode}` |
| `generation_settings` | Frozen inference parameters |
| `stale_at_publish` | Set when cache identity drifted at publish gate |
| `page_counts` | Lexical counters: `[{page_id, count}, …]` for every scanned page (including zeros) |

## Attempt state vs outcome

Same separation as [analysis-result.md](analysis-result.md). Malformed model responses produce warnings (`abstain_unparseable`) and must not corrupt persisted findings.

## Cacheable outcomes

`success`, `skipped_not_applicable`, `unavailable_dependency`, `insufficient_data` may become published when attempt succeeded.

`failed` attempts are history only.
