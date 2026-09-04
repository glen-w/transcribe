# Detection run storage

Durable detection artifacts live inside the managed notebook project. Top-level paths: [project-on-disk.md](project-on-disk.md). Envelope: [detection-result.md](detection-result.md). Finding shape: [detection-finding.md](detection-finding.md).

## Ownership

- Transcribe persistence owns writes; detection runners produce envelopes + findings.
- Authoritative outputs are **project-local** under `detection/` — never a global store.
- Archive SQLite may index findings later but is never detection authority.

## Layout

| Path | Role |
|------|------|
| `detection/` | Durable detection artifacts; **optional until first write** |
| `detection/<detector_id>/published.json` | Current finding index + envelope metadata |
| `detection/<detector_id>/attempts/<attempt_id>.json` | Attempt history |
| `detection/custom/<custom_detector_id>.json` | Optional project-local custom definition snapshot |

Workspace custom detector **definitions**: `data/config/detection/custom/<id>.json`.

Creating `detection/` on first write is not a layout migration.

## Project identity binding

Every durable artifact must include canonical **`notebook_id` / `project_id` from `project.json`**, not filesystem path.

Lookup key: `(notebook_id, detector_id, cache_identity)`

## Atomicity and locks

Same sequence as [analysis-run-storage.md](analysis-run-storage.md):

1. Under `mutation_lock` (short): allocate `attempt_id`, persist `attempt_state: running`, record planned `cache_identity`
2. Release lock; run detection unlocked
3. Persist terminal attempt atomically
4. Under `mutation_lock` (short): rebuild current `cache_identity`; if stale → retain attempt, set `stale_at_publish`, do **not** update `published.json`; else if cacheable → atomically replace `published.json`

Long compute must not hold `mutation_lock`.

### Reopen reconciliation

When project is opened and **both** the OCR job lock and the analysis lock are free: `running` attempts → `interrupted`. Reconciliation must not clear valid `published.json`. Skip reconcile while either long lock is held so a live OCR job or Analyse+detect run is not false-interrupted by `ProjectService.load(reconcile=True)`.

Mid-run project loads during an active detection attempt **must** use `reconcile=False` so the in-flight attempt is not marked `interrupted` before the terminal write. Reopen reconciliation remains the path that cleans orphaned `running` attempts after process death.

## Cache identity

`cache_identity` is hex SHA-256 of canonical JSON (`cache_identity_version: 1`) with sorted keys. Required fields:

| Field | Source |
|-------|--------|
| `cache_identity_version` | `1` |
| `notebook_id` | `project.id` |
| `detector_id`, `detector_version` | DetectorDefinition |
| `prompt_id`, `prompt_version` | Resolved prompt (`lexical:<matcher>` for lexical counters; `ner:people` for names) |
| `config_fingerprint` | Threshold, window params, candidate strategy, model_mode |
| `model_digest` | Resolved text or vision model |
| `scope_fingerprint` | Sorted target page IDs + per-page input fingerprints |
| `generation_settings` | Frozen LLM options |
| `ner` | Names detector only: live NER `cache_config` (model + algorithm) |

### Per-page input fingerprint

Each page in scope contributes:

- `page_id`
- `effective_text_sha256` (edited text ?? active OCR)
- `active_render_id`
- `rendered_image_sha256`
- `page_order_index`

Invalidation triggers: OCR/edit revision, render change, detector/prompt/model/config change, page reorder.

## Cross-window aggregation

For `page_window` / notebook adjacent detection:

1. Generate sliding windows (default size 3, overlap 1).
2. Collect raw window detections with continuation flags.
3. **Deterministically merge** overlapping/adjacent spans of same `finding_type`.
4. Dedupe when Jaccard page-set overlap ≥ 0.5 (keep higher confidence).
5. Assign new `finding_id` per merged span at publish time.

## Publish rules

- Only `attempt_state == succeeded` with outcome ∈ `{success, skipped_not_applicable, unavailable_dependency, insufficient_data}` may update published.
- `failed` / `cancelled` / `interrupted` must never replace published.
- Partial runs (`partial: true`) may publish successful findings when outcome is `success`.

## Stale results policy

Results from old detector/prompt versions remain in attempt history with full provenance. Published pointer updates only on successful rerun with matching cache identity. UI marks stale via freshness comparison — never silent upgrade.
