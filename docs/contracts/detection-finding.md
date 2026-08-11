Type: CONTRACT
Authority: self — persisted detection finding shape and review semantics

# Detection finding

A **DetectionFinding** is derived state referencing stable notebook/page IDs. Findings may span consecutive pages (e.g. a poem continuing across pages).

## Finding object (v1)

| Field | Required | Notes |
|-------|----------|-------|
| `finding_id` | yes | UUID hex; stable across review edits |
| `detector_id` | yes | Detector identity |
| `detector_version` | yes | Detector version at detection time |
| `notebook_id` | yes | Canonical `project.id` |
| `start_page_id` | yes | Inclusive; `project.pages` order |
| `end_page_id` | yes | Inclusive |
| `finding_type` | yes | e.g. `poetry`, `custom:dreams` |
| `confidence` | yes | 0–1 |
| `evidence` | yes | `{reason, snippets[]}`; optional bounded `window_raw` |
| `detector_data` | no | Schema-specific (e.g. optional `title`) |
| `start_boundary` | no | `{page_id, char_start?, char_end?, line_hint?}` |
| `end_boundary` | no | Same shape as start_boundary |
| `prompt_provenance` | yes | `{prompt_id, version}` |
| `model_provenance` | yes | `{model_name, model_digest, input_mode}` |
| `input_fingerprint` | yes | Hash of inputs used |
| `created_at` | yes | ISO-8601 UTC |
| `updated_at` | yes | ISO-8601 UTC |
| `review_status` | yes | `unreviewed` \| `approved` \| `rejected` |

## Index

The published artifact for `(notebook_id, detector_id)` contains a `findings[]` array. Individual findings are not separate authoritative files in v1.

## Cross-page spans

- One finding may have `start_page_id != end_page_id`.
- Partial-page boundaries are optional hints for human review.
- Aggregation merges overlapping window observations deterministically (see [detection-run-storage.md](detection-run-storage.md)).

## Identity rules

- Use `page_id`, `notebook_id`, `finding_id` — never filesystem paths or filenames as identity.

## Review carry-forward

On a successful republish for the same detector, preserve `approved` / `rejected` when the new finding matches a prior published finding on span identity `(finding_type, start_page_id, end_page_id)`. Unmatched new findings start as `unreviewed`. Prior reviews without a match are dropped with the old published set.
