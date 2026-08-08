Type: CONTRACT
Authority: self — analysis persistence, publish/cache rules, cache identity composition, and dependency compatibility. References project layout; does not redefine it.

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
  <module_id>/
    published.json          # current published reusable artifact (if any)
    attempts/<attempt_id>.json
```

Creating `analysis/` on first write is not a project-layout migration; projects without it remain valid.

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
analysis/<module_id>/
  published.json
  attempts/<attempt_id>.json
```

Creating `analysis/` on first write is not a layout migration.

### Reopen reconciliation

When the project is opened/loaded and the analysis mutation path is free: every attempt still `running` becomes `interrupted`. Reconciliation **must not** clear or rewrite a valid `published.json`.

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
| `question_text` | yes for `llm_custom_qa`; else null |
| `resolved_model_digest` | yes when model resolved; else null (preflight → unavailable_model) |
| `input_fingerprint` | yes (document content fingerprint or explicit reduction fingerprint) |

## Dependency compatibility (sole normative hard DAG)

PRODUCT docs may list human-readable relationships including soft enrichments. **This contract owns hard-parent compatibility.** Consumers must not silently reuse stale or differently configured parents.

### Required (hard) parents (Wave 1)

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

| Consumer | Optional parent | Baseline when absent |
|----------|-----------------|----------------------|
| `wordclouds` | `keyphrases` | Token/frequency cloud from document text only |
| `topic_modeling` | `keyphrases` | Model without keyphrase prior/seed enrichment |
| `bertopic` | `keyphrases` | BERTopic without keyphrase enrichment |
| `contextual_emotion` | neighbouring-unit window only | N/A (no parent module; window is config) |
| `moments` | `emotion`, `sentiment`, `topic_shift` (soft features) | Notebook salience features still computed; missing soft signals → lower feature set + warning, not hard fail |
| `insights` | — | Hard parents only; no TX `insight_eligibility` |
| `llm_*` / `narrative_summary` | deterministic `summary` / `highlights` as grounding context | `narrative_summary` still hard-deps `summary`; other LLM modules may ground on document text alone per module notes |

### Fallbacks (Wave 1)

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
