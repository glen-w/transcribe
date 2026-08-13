Type: CONTRACT
Authority: self — workspace AnalysisBatchRun lifecycle for sequential multi-notebook Analyse. Does not replace per-notebook AnalysisCoordinator / analysis-run-storage authority.

# Analysis batch runs

Related: [analysis-run-storage.md](analysis-run-storage.md), [import-run.md](import-run.md), [notebook-corpus.md](notebook-corpus.md), [ocr-batch-run.md](ocr-batch-run.md), [public_surfaces.md](../public_surfaces.md).

## Role

`AnalysisBatchRun` is a **workspace** record of “same Analyse plan template × N notebooks”. It does **not** own published module results. Per-notebook `AnalysisCoordinator` / `AnalysisRunPlan` / `analysis/<module>/published.json` remain execution and publish authority.

Bulk import / OCR never auto-starts Analyse. The UI may offer opt-in CTAs that seed Batch from an ImportRun or notebook id list.

## Storage

- Directory: `{TRANSCRIBE_DATA_DIR}/corpus/analysis-runs/`
- File: `{analysis_batch_id}.json`
- Format: `transcribe.analysis-batch-run`
- `schema_version`: `1`

## Fields

| Field | Rule |
|-------|------|
| `analysis_batch_id` | Stable UUID; filename stem |
| `status` | `pending` \| `running` \| `completed` \| `partial` \| `failed` \| `cancelled` |
| `module_ids` | Ordered modules applied to every notebook (hard parents expanded at create) |
| `question_text` | Optional; same Ask text for every notebook when `llm_custom_qa` is included |
| `effective_config` | Frozen EffectiveConfig snapshot at create |
| `config_fingerprint` | Fingerprint of config + text model + modules + question (template-level) |
| `text_model` | Frozen text-model identity when any LLM module is included; else null/absent |
| `plan_template_hash` | SHA-256 of execution-significant **template** fields (excludes per-notebook `project_id` / `run_id`) |
| `preset_label` / `preset_key` / `preset_content_version` / `preset_policy_fingerprint` | Preset identity when launched from a named preset |
| `import_run_id` | Optional; set when seeded from an ImportRun |
| `items` | Ordered notebooks; unique `notebook_id` |

### Item fields

| Field | Rule |
|-------|------|
| `notebook_id` / `title` / `managed_relpath` | Locator + display |
| `state` | See item states |
| `modules_total` / `modules_completed` / `modules_failed` / `modules_skipped` | Counts from the inner Analyse run |
| `error_message` | Optional |
| `inner_run_id` | Optional; project-local `analysis/runs/<run_id>.json` for that notebook |

### Item states

`pending` \| `running` \| `completed` \| `skipped` \| `failed` \| `cancelled`

- Notebooks with no effective page text are `skipped`.
- A notebook that finishes with mixed module outcomes is `completed` with failed/skipped module counts recorded.
- Crash while `running`: resume resets that item to `pending` (inner cache hits still apply).

## Execution

1. Resolve each item to a managed notebook root (corpus index, else project-folder scan).
2. Build a per-notebook `AnalysisRunPlan` from the frozen template (new `run_id`, that `project_id`, same modules/config/model/preset/question); verify `plan_hash`.
3. `AnalysisCoordinator.run_blocking(plan)` with nested progress forwarded to the workspace progress snapshot.
4. One notebook at a time; per-project `.transcribe.analysis.lock` still applies.
5. Cancel: request cancel on the active inner coordinator; do not start remaining notebooks (`cancelled` items).

## Non-goals

- Parallel notebooks in one process
- Cross-notebook / corpus-level Analyse synthesis
- OCR-style `force` recompute flag
- Auto-start Analyse after import or OCR
- Replacing per-module publish / cache / health semantics
