# Analysis result

Durable envelope for a single module’s published or historical analysis run. Storage/publish rules: [analysis-run-storage.md](analysis-run-storage.md). Input document: [analysis-document.md](analysis-document.md). Eligibility: [notebook-eligibility.md](notebook-eligibility.md).

Ports supply **payloads** only. They must not invent alternate envelope shapes, identity fields, or outcome enums — adapters wrap core outputs in this contract.

## Identity

- `format` must be `"transcribe.analysis-result"`
- `schema_version` must be `1`
- Unsupported `schema_version` → refuse

This envelope schema is **frozen before module ports land**. Payload schemas may evolve per module behind `module_id` + `module_version`; the envelope does not.

## Envelope (v1) — required fields

Every durable envelope binds:

| Field | Required | Notes |
|-------|----------|-------|
| `format` | yes | `"transcribe.analysis-result"` |
| `schema_version` | yes | `1` |
| `project_id` | yes | Canonical id from `project.json` — not filesystem path |
| `module_id` | yes | Analysis module identity |
| `module_version` | yes | Transcribe module version / code fingerprint |
| `cache_identity` | yes | Full identity per [analysis-run-storage.md](analysis-run-storage.md) |
| `content_fingerprint` | yes | Input document fingerprint from [analysis-document.md](analysis-document.md) (also inside cache identity) |
| `attempt_state` | yes | Execution lifecycle |
| `outcome` | yes | Terminal semantic result (when attempt finished cleanly enough to conclude) |
| `capability` | yes | UI/runtime capability presentation (below) |
| `provenance` | yes | Object with required provenance fields (below) |
| `warnings` | yes | Array (may be empty) of `{code, message}` |
| `parents` | yes | Array (may be empty) of `{module_id, cache_identity, outcome}` actually used |
| `config_fingerprint` | yes | Canonical subset of module configuration |
| `payload` | yes | Module-specific object; empty object allowed for non-success terminals |

Optional when applicable:

| Field | Notes |
|-------|-------|
| `lexicon_or_model` | Package/lexicon/model identities |
| `resolved_model_digest` | When a model was resolved |
| `llm` | Prompt/template version, generation settings, grounding strategy, question text, chunking policy id |
| `evidence` | Array of evidence objects (below) when the payload cites notebook text |
| `partial` | `true` when `outcome == success` but payload is intentionally incomplete (see partial success) |

## Attempt state vs result outcome

These are separate axes. Do not conflate them.

| Concept | Values | Meaning |
|---------|--------|---------|
| **Attempt state** | `running` \| `succeeded` \| `failed` \| `cancelled` \| `interrupted` | Whether execution finished cleanly |
| **Result outcome** | `success` \| `skipped_not_applicable` \| `unavailable_dependency` \| `insufficient_data` \| `failed` | What the module concluded |

Attempt lifecycle aligns with [page-result.md](page-result.md): when the project mutation lock is free, abandoned `running` attempts reconcile to `interrupted`. Reconciliation updates **attempt history** only — it does not clear or overwrite a prior **published reusable** result (see analysis-run-storage).

## Committed reusable artifact

A **published reusable** artifact for `(project_id, module_id)` may be written or updated only when **all** of:

1. `attempt_state == succeeded`
2. `outcome ∈ {success, skipped_not_applicable, unavailable_dependency, insufficient_data}`
3. Envelope includes matching `cache_identity` and binding `project_id`

| Outcome | Durable attempt/history | Cacheable terminal (skip rerun when identity matches) | May become published reusable |
|---------|-------------------------|------------------------------------------------------|-------------------------------|
| `success` | yes | yes | yes (with attempt `succeeded`) |
| `skipped_not_applicable` | yes | yes | yes |
| `unavailable_dependency` | yes | yes | yes |
| `insufficient_data` | yes | yes | yes |
| `failed` | yes (history) | **no** | **no** |

### Publication / non-clobber

- Attempt states `running`, `failed`, `cancelled`, and `interrupted` **must never** replace the last published reusable artifact
- Distinguish **attempt history** (retained runs) from **current published result** (single reusable pointer per module under the project)
- Only `attempt_state == succeeded` combined with a cacheable terminal outcome may update the published pointer

## Capability presentation (UI / optional deps)

`capability` is the **sole** vocabulary for UI and runtime gating of optional dependencies. It is derived from outcome + reason; UIs must not invent parallel enums.

| `capability` | Meaning | Typical `outcome` |
|--------------|---------|-------------------|
| `available` | Module can run or has a reusable success | `success` (or preflight: deps present) |
| `success` | Completed with usable payload | `success` (`partial` false/absent) |
| `partial` | Completed with intentionally incomplete payload; warnings explain gaps | `success` with `partial: true` |
| `unavailable_extra` | Optional Python/extra package not installed (e.g. BERTopic) | `skipped_not_applicable` |
| `unavailable_model` | Required local model/runtime missing (e.g. Ollama model, transformer weights) | `skipped_not_applicable` |
| `skipped_not_applicable` | Policy/corpus gate skipped the module without error (e.g. zero eligible units after `notebook_eligibility_v1`) | `skipped_not_applicable` |
| `invalid_input` | Document failed validation before the core ran | `insufficient_data` |
| `insufficient_data` | Valid document but too little / wrong-shaped corpus for the algorithm | `insufficient_data` |
| `unavailable_dependency` | Hard parent missing, mismatched, or non-acceptable outcome | `unavailable_dependency` |
| `failed` | Execution error | `failed` |

Optional BERTopic, transformer emotion, embeddings, and Ollama **must** degrade to a named capability above — never tracebacks to the UI, never ambiguous empty `success` payloads that look like “no findings”.

## Provenance

Not `"TranscriptX 1.x / <module>"` alone. Required fields under `provenance`:

| Field | Notes |
|-------|-------|
| `ported_from.repo` | Source repository identity |
| `ported_from.commit` | Concrete upstream commit (or tag that resolves to commit) used for the copied core |
| `ported_from.module_id` | Upstream module id |
| `ported_from.files[]` | `{path, sha256}` for each copied TX source file |
| `module_version` | Transcribe module version |
| `adapter_version` | Adapter version that built the `AnalysisDocument` |
| `app_version` | Application version |
| `semantic_class` | `parity` \| `adaptation` \| `fork` |
| `semantic_delta` | Short string when not pure parity |

Pin registry process: [../dev/analysis_port_pins.md](../dev/analysis_port_pins.md). The commit recorded here must match the pin row so later TX diffs are reproducible.

### External analytical dependencies

Model, lexicon, and package identities that affect reproducibility belong in provenance **and** in cache identity even when they are not rows in the TX pin registry:

- package name + version (or equivalent lock)
- lexicon id + version
- model name + resolved digest where applicable
- optional-extra identity (e.g. bertopic stack)

## Semantic class guidance

| Class | Use when |
|-------|----------|
| `parity` | Behaviour expected to match TX on shared fixture shapes |
| `adaptation` | Speaker assumptions removed, eligibility policy substituted, chronology via order/date |
| `fork` | Algorithmic replacement (e.g. `moments` salience without momentum/pauses) |

## Evidence (renderable citations)

Evidence must include enough information to **render and validate** the cited passage — not merely an opaque page back-pointer.

Each evidence item:

| Field | Required | Notes |
|-------|----------|-------|
| `unit_id` | yes | Must exist in the input document used for this `content_fingerprint` |
| `char_start` / `char_end` | when citing a span | Unit-local half-open offsets per [analysis-document.md](analysis-document.md) |
| `quote` | yes when displaying text | Exact substring from the cited unit/page text at record time |
| `content_fingerprint` | yes | Fingerprint of the document the quote was taken from |
| `source_ref` | yes | Validated page or page_span form for navigation |

`source_ref` alone is insufficient when spans exist. Parent artifact refs must include parent `module_id`, parent `cache_identity`, and parent `outcome`.

### Stale citations after text edits

- Evidence is valid only while `evidence[].content_fingerprint` equals the current analysis document fingerprint for the same `split_profile` / `granularity_version`
- After edit / reorder / include-exclude / splitter change, stale evidence **must not** be displayed against newer text (UI shows unavailable/stale — does not highlight mismatched offsets)
- Reuse of a published result after identity change is already forbidden by cache identity; open views must re-resolve evidence before render

## Corpus-size and edge-case degradation

Map to **named outcomes**, not uncaught exceptions. Refusal vs empty-success is contract-owned:

| Situation | Outcome / capability |
|-----------|----------------------|
| Zero units / empty notebook after omission of blank/excluded pages | `insufficient_data` |
| Zero eligible units after `notebook_eligibility_v1` | `skipped_not_applicable` (eligibility) |
| One unit where module requires multi-unit corpus (e.g. topic shift, similarity matrix) | `insufficient_data` |
| Single-unit topic modelling | `insufficient_data` unless the algorithm explicitly defines a one-doc behaviour in module notes; default refuse |
| Tiny vocabulary / no tokens for a lexical metric | Prefer `success` with empty/zero metrics when zeros are well-defined; else `insufficient_data` |
| Very short pages only | Follow eligibility when required; otherwise module notes + table below |
| All-blank OCR (all pages omitted) | `insufficient_data` |
| NER finds no entities | `success` with empty entity list (`capability: success`) |
| Consumer needs entities/topics and parent payload is empty | `insufficient_data` unless parent outcome was non-success → `unavailable_dependency` |
| Optional extra missing (BERTopic, embeddings package, transformer extra) | `skipped_not_applicable` / `unavailable_extra` |
| Ollama or model weights missing | `skipped_not_applicable` / `unavailable_model` |
| Model/algorithm requires more samples than available | `insufficient_data` |
| Execution exception / crash | attempt `failed` or `interrupted`; **never** clobber published reusable |

### Minimum-input defaults (core set)

Shared 1.1 tokenizer for lexical metrics unless a module documents otherwise: maximal runs matching TX `TOKEN_RE` (letters with optional internal `'`/`’`/`-`); casefold for types; sentence splits on `.?!` followed by whitespace or EOS.

Float metrics in canonical payloads round to **6** decimal places for goldens.

### `wordclouds` baseline (`wordclouds_tokens_v1` / `wordclouds_payload_v1`)

Normative for wordclouds baseline mode (`enrichment_mode: "baseline"`). Sole analytical input is `AnalysisDocument.text` (never `units[]` tokenization).

| Rule | Policy |
|------|--------|
| Base tokens | Shared 1.1 `TOKEN_RE` + casefold + min length ≥ 2 |
| Stopwords | Pinned list id `wordclouds_stopwords_v1` (in-repo; digest in config/`lexicon_or_model`) — no runtime download |
| Stem/lemma | None |
| Numbers / punctuation | Not tokens (except internal apostrophe/hyphen inside `TOKEN_RE`) |
| Eligible token | Survives tokenize + stopword filter |
| Success payload | `wordclouds_payload_v1`: `tokens[]` of `{token, count, weight}` — `count` raw int ≥ 1; `weight = count / max_count` over all eligible types before truncation, range `(0, 1]`, 6 dp; emit at most 100 types sorted by `count` desc then `token` asc; empty `tokens` forbidden on `success` |
| Zero eligible tokens | Non-empty `text` that yields zero eligible tokens → `outcome: insufficient_data` (not empty success) |
| Enrichment | Baseline never consumes optional parent `keyphrases`; enrichment requires a deliberate later `enrichment_mode` / `module_version` transition |

Compatibility is judged on **analytical payload semantics**; rendered pixels / PNG bit identity are non-contractual.

| Module | `insufficient_data` when | `success` when | Notes |
|--------|--------------------------|----------------|-------|
| `stats` | zero emitted units | ≥1 unit | zero sub-metric counts allowed |
| `lexical_diversity` | `n_tokens < 1` | `n_tokens ≥ 1` | MTLD only if `n_tokens ≥ 50`; else omit `mtld`, `partial: true`, warning `below_mtld_threshold` |
| `understandability` | `n_words < 3` or `n_sentences < 1` | otherwise | non-finite scores → `failed` |
| `wordclouds` | empty document **or** zero eligible tokens after `wordclouds_tokens_v1` | ≥1 eligible token | baseline only in wordclouds baseline mode; see section above |
| `ner`, `sentiment`, `emotion`, `epistemic_markers` | empty document | possibly empty labels | |
| `entity_sentiment`, `affect_tension` | parents / empty join | per parents | hard parents |
| `keyphrases`, `topic_modeling`, `bertopic`, `highlights`, `insights` | eligibility / algorithm mins | | |

### Language foundations payloads

| Module | Payload id | Notes |
|--------|------------|-------|
| `ner` | `ner_payload_v1` | `entities[]` + `entity_counts` / `label_counts` / per-unit rows; zero entities → `success` + empty lists; missing spaCy → `skipped_not_applicable` + capability `unavailable_extra` |
| `sentiment` | `sentiment_payload_v1` | Per-unit `compound`/`pos`/`neu`/`neg` + `label` ordered by `order` (optional `date`); `global_stats` means + distribution; no speaker keys |
| `epistemic_markers` | `epistemic_markers_payload_v1` | Lexicon `epistemic_markers_en` + `lexicon_markers_v1` matching; `global_stats` / per-unit rates; optional evidence spans for hits |

Chronology for sentiment/NER timelines uses unit `order` (+ optional `date`). Do not invent wall-clock timestamps. Language foundations modules are **ungated** relative to `notebook_eligibility_v1`.

### Topics & similarity payloads

| Module | Payload id | Notes |
|--------|------------|-------|
| `topic_modeling` | `topic_modeling_payload_v1` | Eligibility required; seed-bucket topics; baseline ignores optional `keyphrases` |
| `semantic_similarity` | `semantic_similarity_payload_v1` | Ungated; BoW TF-IDF cosine `matrix` + `motifs[]`; no multi-speaker gate |
| `topic_shift` | `topic_shift_payload_v1` | Ungated; consecutive cosine drops vs unit `order` (+ optional `date`); `shifts[]` |
| `bertopic` | `bertopic_payload_v1` | Eligibility required; optional extra — missing/unconfigured → `skipped_not_applicable` + capability `unavailable_extra` (never silent LDA substitute) |

| Module | `insufficient_data` when | `success` when | Notes |
|--------|--------------------------|----------------|-------|
| `semantic_similarity`, `topic_shift` | `< 2` units | ≥2 units | |
| `moments` | empty document | ranked list (maybe length 1) | |
| LLM suite | empty / unavailable model | abstain rules | see LLM section |

### Emotion & salience payloads

| Module | Payload id | Notes |
|--------|------------|-------|
| `emotion` | `emotion_payload_v1` | Ungated; lexicon `emotion_lexicon_v1`; per-unit scores/distribution/intensity + chronology |
| `contextual_emotion` | `contextual_emotion_payload_v1` | Neighbor window by `order` (config, not a parent module) |
| `fine_grained_emotion` | `fine_grained_emotion_payload_v1` | Optional transformer extra → `unavailable_extra` (never silent lexicon substitute) |
| `affect_tension` | `affect_tension_payload_v1` | Hard parents `emotion`+`sentiment`; tension series vs order |
| `moments` | `moments_payload_v1` | Salience **fork** (no momentum); optional soft `emotion`/`sentiment`/`topic_shift`; prefer `paragraph_v1` |

## LLM evidence, cache identity contribution, and refusal

Applies to `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary`:

- Unsupported answers **abstain** — do not fabricate citations or evidence
- Evidence must resolve to **current** compatible units/spans under the current content fingerprint and split profile
- Stale evidence after relevant text or splitting changes is **not reusable**
- Bounded input: deterministic chunking / section aggregation; forbid dumping an unbounded whole-notebook string when it exceeds the configured max context policy (policy id is part of cache identity)
- **Frozen LLM policy ids:**
  - `chunking_policy_id`: `notebook_chunks_units_v1` (pack units by `order` up to a token budget; oversized units are deterministically sub-split with span provenance; never silently truncated)
  - `reduction_policy_id`: `notebook_map_reduce_v1` (bound total prompt context; map/reduce when chunks exceed total budget)
  - `grounding_strategy_id`: `ground_doc_chunks_v1` (document chunks) or `ground_highlights_summary_v1` (`narrative_summary`)
- Cache identity **must** include (via analysis-run-storage `llm` object): resolved model digest, prompt/template version, generation settings, grounding strategy id, question text when applicable, input/dependency identities, chunking policy id
- Recorded test doubles must exercise the **same** result validation and abstention path as live Ollama (no separate “stub success” shape)

### Synthesis & LLM payloads

| Module | Payload id | Notes |
|--------|------------|-------|
| `keyphrases` | `keyphrases_payload_v1` | Eligibility required |
| `entity_sentiment` | `entity_sentiment_payload_v1` | Hard parents `ner`+`sentiment` |
| `topic_modeling` | `topic_modeling_payload_v1` | Eligibility required; seed-bucket topics (see topics & similarity) |
| `semantic_similarity` | `semantic_similarity_payload_v1` | See topics & similarity |
| `topic_shift` | `topic_shift_payload_v1` | See topics & similarity |
| `bertopic` | `bertopic_payload_v1` | See topics & similarity |
| `highlights` | `highlights_payload_v1` | Eligibility; prefer `paragraph_v1` |
| `summary` | `summary_payload_v1` | Hard parent `highlights` |
| `insights` | `insights_payload_v1` | Hard parents `highlights`+`topic_modeling`; eligibility |
| `llm_summary` | `llm_summary_payload_v1` | Optional Ollama; `honesty_label` |
| `llm_action_items` | `llm_action_items_payload_v1` | Optional Ollama |
| `llm_custom_qa` | `llm_custom_qa_payload_v1` | Grounded `unit_ids`; abstain if ungrounded |
| `narrative_summary` | `narrative_summary_payload_v1` | Hard parent `summary`; `unavailable_model` when Ollama/text model missing |

## Derived Analyse health (non-durable)

`AnalysisHealth` is computed for UI surfaces from published envelopes + planned cache identities + notebook `content_revision`. It is **not** a persisted authority; publish authority remains `published.json` + cache identity.

| Field | Notes |
|-------|-------|
| `content_revision` | Notebook content identity ([project-on-disk.md](project-on-disk.md)) |
| `modules` | Per-module `{freshness, capability, outcome}` from `module_freshness` |
| `aggregate` | `healthy` \| `stale` \| `missing` \| `degraded` \| `failed` \| `running` \| `interrupted` |
| `active_run_status` | Optional batch coordinator status |

**Aggregate order:** running → interrupted → any stale → all unavailable/missing → any failed → any degraded capability (`unavailable_*` / `insufficient_data` / `skipped_not_applicable`) → healthy.

Overview / Themes / Mood / Moments / Summaries **must** answer “is this current and healthy?” from this shared derivation (or a scope of it). Ask notebook is ad-hoc and does **not** update batch health.