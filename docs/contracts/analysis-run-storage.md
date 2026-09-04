# Analysis run storage

Durable analysis artifacts live inside the managed notebook project. Top-level paths are owned solely by [project-on-disk.md](project-on-disk.md). Result envelope semantics: [analysis-result.md](analysis-result.md). Input fingerprint: [analysis-document.md](analysis-document.md). Eligibility contribution: [notebook-eligibility.md](notebook-eligibility.md).

## Ownership

- Transcribe persistence owns writes; analysis cores are pure over canonical I/O
- Authoritative outputs are **project-local** under `analysis/` — never a global per-module analysis tree
- Workspace `archive.sqlite` (and any discovery index) may point at projects but is never analysis authority

## Layout (reference only)

Per [project-on-disk.md](project-on-disk.md):

| Path | Role |
|------|------|
| `analysis/` | Durable analysis artifacts; **optional until first write** |
| `.cache/analysis/` | Disposable acceleration only |

Exact filenames, staging directories, and payload file formats under `analysis/` are implementation-defined but must obey the publish, identity, and atomicity rules below. Illustrative pattern:

```text
analysis/
  runs/<run_id>.json        # batch AnalysisRunPlan + progress (optional)
  <module_id>/
    published.json          # current published reusable artifact (if any)
    attempts/<attempt_id>.json
```

Creating `analysis/` on first write is not a project-layout migration; projects without it remain valid. The `runs/` directory is reserved and is never treated as a module id.

## Project identity binding

Every durable artifact and every cache lookup **must** include the canonical **`project_id` from `project.json`**, not merely the filesystem path.

Lookup key: `(project_id, module_id, cache_identity)`

- Moved projects remain valid when `project_id` is unchanged
- Cross-project reuse is impossible: path coincidence must not produce a cache hit

## Atomicity and locks

**Do not hold `mutation_lock` while running analysis cores.** Long compute must not block unrelated project writes.

Required sequence:

1. Under `mutation_lock` (short): allocate `attempt_id`, persist `attempt_state: running` attempt artifact, record planned `cache_identity` / content fingerprint
2. Release lock; run the module unlocked
3. Persist the terminal attempt artifact atomically (immutable after leaving `running`)
4. Under `mutation_lock` (short): rebuild current document fingerprint / `cache_identity`; if stale vs the attempt’s planned identity → **retain attempt**, do **not** update published; else if outcome is cacheable → atomically replace `published.json`
5. Release lock

Attempt file writes and published-pointer swaps use `write_json_atomic`. Partial writes must not become published.

### Layout

```text
analysis/
  runs/<run_id>.json
  <module_id>/
    published.json
    attempts/<attempt_id>.json
```

Creating `analysis/` on first write is not a layout migration. Skip the reserved `runs/` name when scanning module directories.

### Analysis batch lock

At most one analysis batch run per project across processes, held via `.transcribe.analysis.lock` (see [project-on-disk.md](project-on-disk.md)). Long module compute holds this lock for the run lifetime and must **not** hold `mutation_lock`.

### Frozen AnalysisRunPlan

Batch Analyse launches freeze an immutable **AnalysisRunPlan** before any module runs: ordered module ids, optional detector ids, optional question text, EffectiveConfig snapshot + config fingerprint, text-model identity when LLM modules or detectors are included, and preset identity (`preset_key`, `preset_content_version`, `preset_policy_fingerprint`). Workers consume the plan (bound config + frozen model identity), not live UI/settings. Mid-run settings / text-model / module-list changes apply to the **next** run only. Notebook content edits mid-run still use publish revalidation (`stale_at_publish`) — text is not frozen as execution authority.

#### `plan_hash` (preflight bind)

`plan_hash` is the hex SHA-256 of a canonical JSON object over execution-significant fields. **Exclude** ephemeral `run_id`, `created_at`, and `plan_hash` itself. Required body fields:

| Field | Notes |
|-------|-------|
| `project_id` | from `project.json` |
| `module_ids` | ordered freeze list |
| `detector_ids` | ordered detectors (may be empty); run after modules via DetectionService |
| `question_text` | or null |
| `effective_config` | full EffectiveConfig snapshot |
| `text_model` | frozen model object or null |
| `config_fingerprint` | plan config fingerprint |
| `preset_key` | `quick` / `balanced` / `thorough` / `custom` (or null) |
| `preset_content_version` | integer content generation (Custom may use `0`) |
| `preset_policy_fingerprint` | SHA-256 of policy body (or Custom module/detector-list fingerprint) |

**Preflight bind rule:** the UI freezes the plan at launch confirm and stashes `{plan, plan_hash}`. Start must deserialize that plan and refuse when recomputed `plan_hash` ≠ stored hash. Start **must not** re-snapshot live settings/config. Coordinator start also refuses a tampered or empty `plan_hash`.

Durable run records (`format: transcribe.analysis-run`) live under `analysis/runs/<run_id>.json`. They are history/progress only and never replace module publish authority. Run records include `plan_hash` and preset identity fields alongside the embedded `plan`.

### Reopen reconciliation

When the project is opened/loaded and the **analysis** lock is free: every attempt still `running` becomes `interrupted`, and every non-terminal run record becomes `interrupted`. Reconciliation **must not** clear or rewrite a valid `published.json`. Do **not** gate analysis reconcile on the OCR job lock. Process death does not auto-resume a batch; the user re-launches and published cache hits skip completed modules.

### Cache-hit validation

Matching `cache_identity` is necessary but not sufficient. Refuse reuse when the published envelope fails schema validation, `module_version` disagrees with the requested module pin, the artifact is unparsable/corrupt, or required fields are missing.

## Attempt history vs published result

| Store | Role |
|-------|------|
| Attempt history | Retained execution records (`running` / `succeeded` / `failed` / `cancelled` / `interrupted`) |
| Published result | Single reusable artifact per `(project_id, module_id)` |

Publish rules (normative detail in [analysis-result.md](analysis-result.md)):

- Only `attempt_state == succeeded` with outcome ∈ `{success, skipped_not_applicable, unavailable_dependency, insufficient_data}` may update the published result
- `running` / `failed` / `cancelled` / `interrupted` **must never** replace the last published reusable artifact
- Reconciliation (`running` → `interrupted` when lock free) updates history only

A **cache hit** that skips rerun requires: published artifact present and schema-valid, `project_id` match, `cache_identity` match, `module_version` match, and outcome in the cacheable terminal set above.

**Forbidden:** cache keys of only `(project_id, module_id)`, filesystem path, or raw text hash without the full `cache_identity` object.

## Cache identity

`cache_identity` is the hex SHA-256 of a canonical JSON object (`cache_identity_version: 1`) with sorted keys and compact UTF-8 JSON (same serialization discipline as the analysis-document content fingerprint). Required fields:

| Field | Source |
|-------|--------|
| `cache_identity_version` | `1` |
| `project_id` | `project.json` |
| `module_id` | module |
| `content_fingerprint` | [analysis-document.md](analysis-document.md) algorithm |
| `content_fingerprint_version` | `1` |
| `module_version` | Transcribe module version / code fingerprint |
| `adapter_version` | adapter |
| `granularity_version` | document |
| `split_profile` | document |
| `config_fingerprint` | relevant module configuration (canonical subset) |
| `eligibility_policy_id` | e.g. `notebook_eligibility_v1` when used; else null |
| `eligibility_policy_version` | when used; else null |
| `eligibility_fingerprint` | hash of eligibility output when policy used; else null |
| `parents` | sorted array of `{module_id, cache_identity, outcome}` for required **and** optional parents actually consumed |
| `lexicon_or_model` | package/lexicon/model identities affecting reproducibility |
| `resolved_model_digest` | when applicable; else null |
| `llm` | when applicable (below); else null |

Identity therefore varies with text/order/included pages **and** adapter granularity/splitting, module configuration, dependency outputs, algorithm/schema version, lexicon/model version or digest, and relevant prompt/runtime parameters — not content alone.

### LLM `llm` object (when module uses a generative model)

| Field | Required |
|-------|----------|
| `prompt_or_template_version` | yes |
| `generation_settings` | yes (canonical subset: temperature, max tokens, etc.) |
| `grounding_strategy_id` | yes |
| `chunking_policy_id` | yes |
| `reduction_policy_id` | yes (`notebook_map_reduce_v1` for LLM modules) |
| `token_estimator_id` | yes (`whitespace_tokens_v1` for LLM modules) |
| `question_text` | yes for `llm_custom_qa`; else null |
| `resolved_model_digest` | yes when model resolved; else null (preflight → unavailable_model) |
| `input_fingerprint` | yes (excerpts actually supplied / reduction fingerprint — not whole-document dump) |

**Frozen LLM policy ids** (must match [analysis-result.md](analysis-result.md)):

| Field | Allowed LLM policy values |
|-------|------------------------|
| `chunking_policy_id` | `notebook_chunks_units_v1` (token budget; sub-split oversized units) |
| `reduction_policy_id` | `notebook_map_reduce_v1` |
| `token_estimator_id` | `whitespace_tokens_v1` |
| `grounding_strategy_id` | `ground_doc_chunks_v1` \| `ground_highlights_summary_v1` |

## Dependency compatibility (sole normative hard DAG)

PRODUCT docs may list human-readable relationships including soft enrichments. **This contract owns hard-parent compatibility.** Consumers must not silently reuse stale or differently configured parents.

### Required (hard) parents (core set)

| Consumer | Required parents | Acceptable parent outcomes |
|----------|------------------|----------------------------|
| `entity_sentiment` | `ner`, `sentiment` | `success` |
| `affect_tension` | `emotion`, `sentiment` | `success` |
| `summary` | `highlights` | `success` |
| `insights` | `highlights`, `topic_modeling` | `success` |
| `narrative_summary` | `summary` | `success` |

For each required parent, the consumer must verify:

1. Published parent exists for the same `project_id`
2. Parent `outcome` is in the acceptable set
3. Parent `cache_identity` equals the identity recorded in the consumer’s planned `parents` list (content/config/eligibility alignment)

On failure → commit reusable terminal with `outcome: unavailable_dependency` when attempt completes cleanly; never run the consumer core against mismatched parents.

### Optional enrichments (non-blocking)

These parents **enrich** payloads when present and compatible; absence must not fail the consumer. When consumed, their `{module_id, cache_identity, outcome}` enter `parents` and thus cache identity. When absent, the consumer runs its documented baseline path (never an ad-hoc stub).

Optional-parent **resolution must precede** `cache_identity` construction and cache lookup. Only parents **actually consumed** enter `parents`. Baseline wordclouds mode locks `wordclouds` to `enrichment_mode: "baseline"`: `keyphrases` is never consumed even when a compatible published `success` exists (absent / incompatible / failed / non-success / success → all ignored). Enrichment requires a deliberate later mode/`module_version` transition so enabling enrichment cannot silently change baseline identity or outputs.

| Consumer | Optional parent | Baseline when absent |
|----------|-----------------|----------------------|
| `wordclouds` | `keyphrases` | Token/frequency cloud from document text only (`enrichment_mode: "baseline"` in baseline wordclouds always takes this path) |
| `topic_modeling` | `keyphrases` | Model without keyphrase prior/seed enrichment |
| `bertopic` | `keyphrases` | BERTopic without keyphrase enrichment |
| `contextual_emotion` | neighbouring-unit window only | N/A (no parent module; window is config) |
| `moments` | `emotion`, `sentiment`, `topic_shift` (soft features) | Notebook salience features still computed; missing soft signals → lower feature set + warning, not hard fail |
| `insights` | — | Hard parents only; no TX `insight_eligibility` |
| `llm_*` / `narrative_summary` | deterministic `summary` / `highlights` as grounding context | `narrative_summary` still hard-deps `summary`; other LLM modules may ground on document text alone per module notes |

### Fallbacks (core set)

| Situation | Behaviour |
|-----------|-----------|
| TX `insight_eligibility` | **Not ported.** Sole substitute: [`notebook_eligibility_v1`](notebook-eligibility.md) for the modules listed there |
| TX `momentum` (for `moments`) | **Not ported.** `moments` is `fork` / notebook salience — not a soft import of momentum |
| BERTopic extra missing | `skipped_not_applicable` / capability `unavailable_extra` — do not fall back to silently pretending LDA is BERTopic |
| Transformer emotion missing | lexicon/`emotion` path remains; heavy modules → `unavailable_extra` or `unavailable_model` |
| Ollama missing | LLM modules → `unavailable_model`; deterministic synthesis path unaffected |

Modules not listed under **Required (hard) parents** have **no** hard parent dependencies under this contract version.
## Non-goals

- Redefining top-level project layout (owned by project-on-disk)
- Global authoritative analysis storage
- Cache hits keyed only by filesystem path
