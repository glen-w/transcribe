Type: PRODUCT
Authority: Wave 1 analysis-port delivery plan (architecture, sub-waves, dependency map, checklists, test intent, exit criteria). Does **not** define runtime contracts, schemas, storage rules, cache identity, refusal/outcome enums, or atomicity. Those live only in CONTRACT docs — this plan must not silently become a second authority. Disposition table: [analysis_module_porting.md](analysis_module_porting.md); waves: [ROADMAP.md](ROADMAP.md).

# Wave 1 plan — TranscriptX analysis ports

Detailed delivery plan for the 25 **Port early** modules. Companion to the disposition map and roadmap.

**Governing contracts (sole normative authority):**

| Concern | Contract |
|---------|----------|
| Managed project layout (`analysis/` optional) | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Frozen `AnalysisDocument` schema v1 (ordering, uniqueness, `source_ref`, dates, empty/excluded/blank OCR, split profiles) | [contracts/analysis-document.md](contracts/analysis-document.md) |
| Result envelope v1 (payloads vs envelope, provenance, evidence, capability, min-input, LLM refusal) | [contracts/analysis-result.md](contracts/analysis-result.md) |
| Storage, `project_id` lookup, cache identity, hard/optional parents, atomic publish | [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) |
| Sole Wave-1 eligibility policy (`notebook_eligibility_v1`) | [contracts/notebook-eligibility.md](contracts/notebook-eligibility.md) |
| TX pin rows + concrete upstream commit | [dev/analysis_port_pins.md](dev/analysis_port_pins.md) |

When this plan and a contract disagree, **the contract wins**. Do not restate cache-identity formulas, outcome enums, or publish/atomicity rules here — link only.

---

## 1. Architecture

### Chosen approach

Port deterministic / content-analysis modules **almost verbatim**. Wrap them with thin **notebook-specific adapters** for inputs and outputs. Do **not** rewrite modules to understand notebooks, pages, Streamlit state, or filesystem identity.

Canonical input and result shapes are frozen in contracts **before** ports:

- Input: [analysis-document.md](contracts/analysis-document.md) (`format: "transcribe.analysis-document"`, schema v1)
- Output envelope: [analysis-result.md](contracts/analysis-result.md) — cores supply **payloads**; adapters emit the envelope

Summary shape (non-normative reminder — full field rules in the contract):

```text
AnalysisDocument
  document_id (== project_id)
  text                         # canonical document string
  granularity_version / split_profile   # page | paragraph_v1
  units[]  (sorted; unique unit_id; validated source_ref; date null|YYYY-MM-DD)
```

| Domain | Typical unit |
|--------|----------------|
| TranscriptX | segment / utterance |
| Transcribe | page (`page` profile) or paragraph/span (`paragraph_v1`) |

Algorithms see **text + ordered units + metadata** only — never `Page` objects or UI state.

### Pipeline

```text
External originals (untouched)
     ↓ ingest / copy
Managed notebook project  (project.json, sources/, pages/, results/, analysis/, …)
     ↓
notebook_analysis_adapter (+ notebook_eligibility_v1 when required)
     ↓
canonical AnalysisDocument
     ↓
ported TranscriptX module  (exact TX pin + semantic_class)
     ↓
analysis-result envelope (contract) + module payload
     ↓
project-local analysis/ storage  (rules in analysis-run-storage)
     ↓
Notebook UI (capability vocabulary from analysis-result)
```

### Ownership boundaries

| Owns | Does not own |
|------|----------------|
| **Ported core** — scoring, ranking, clustering, lexicon/model inference, **payload** close to TX | Envelope fields, page IDs, locking, OCR provenance, Streamlit, archive SQLite, cache identity |
| **Transcribe adapters** — project → `AnalysisDocument`, eligibility invocation, payload → envelope + durable store, UI | Analytical algorithms (keep TX-recognisable) |

Layout, storage binding, invalidation, attempt/crash non-clobber, and atomicity: **[project-on-disk](contracts/project-on-disk.md)** + **[analysis-run-storage](contracts/analysis-run-storage.md)** + **[analysis-result](contracts/analysis-result.md)** — not this plan.

### Provenance (delivery requirement)

Every port fills [analysis_port_pins.md](dev/analysis_port_pins.md) with the **concrete** upstream commit/tag and per-file hashes **before** implementation is marked done. Envelope provenance fields are owned by [analysis-result.md](contracts/analysis-result.md) (not a bare `ported_from = "TranscriptX 1.x / <module>"`). Classify each module `parity` | `adaptation` | `fork`.

### Copy, don't extract (yet)

- Copy selected modules with attribution; keep structure close to TX.
- Small compatibility layer (`AnalysisDocument` ↔ TX-shaped segment list if needed).
- **Resist** a shared `transcriptx-analysis` package until identical cores are obvious after several ports.

### Unit granularity (delivery defaults)

| Default profile | When |
|-----------------|------|
| **`page` / `page_v1`** | Overview metrics, NER/sentiment timelines, topic shift, most Wave 1 modules |
| **`paragraph_v1`** | Moments, highlights, fine-grained emotion, QA evidence — when page text is long |
| **Document-level `text`** | Whole-notebook summaries, wordclouds, lexical diversity rollups |

Splitter rules and stable derived-unit IDs are **frozen in** [analysis-document.md](contracts/analysis-document.md). **`paragraph_v1` must be implemented and tested before Waves 1d/1e** modules that emit span evidence. Cores stay unit-agnostic.

### Chronology (no TX timing machinery)

Notebook chronology = unit `order` (page/span order) plus optional **`date`** on units — representation in the analysis-document contract. Do **not** invent synthetic wall-clock timestamps or fake speakers.

Wave 1 modules that benefit: `topic_shift`, `sentiment`, `emotion` / family, `ner`, `semantic_similarity`, `affect_tension`.

### Analysis / cache identity (link only)

Results must vary with content **and** adapter granularity/splitting, module configuration, dependency outputs, algorithm/schema version, lexicon/model digest, eligibility output when used, and LLM prompt/runtime parameters. **Formula and field list:** [analysis-run-storage.md](contracts/analysis-run-storage.md) (composes [analysis-document](contracts/analysis-document.md) content fingerprint). This plan does not restate the hash.

### Eligibility (named policy only)

**Sole Wave-1 compatibility policy:** [`notebook_eligibility_v1`](contracts/notebook-eligibility.md). Replaces TX `insight_eligibility` for the modules listed there. No per-module soften/bypass/stub. Explicit ungated modules and `wordclouds` keyphrase enrichment are resolved in that contract (+ optional-parent table in analysis-run-storage).

---

## 2. Dependency DAG (all 25 modules)

**Hard-parent compatibility** (acceptable outcomes, cache_identity match) is owned solely by [analysis-run-storage.md](contracts/analysis-run-storage.md). The tables below are the delivery map: hard vs optional enrichment vs fallback. Do not implement against a different parent set without a contract change.

### Hard dependencies

| Consumer | Hard parents | Notes |
|----------|--------------|-------|
| `entity_sentiment` | `ner`, `sentiment` | 1b; both must be compatible `success` |
| `affect_tension` | `emotion`, `sentiment` | 1d; `sentiment` from 1b |
| `summary` | `highlights` | 1e |
| `insights` | `highlights`, `topic_modeling` | 1e; topics from 1c |
| `narrative_summary` | `summary` | 1e; may also use LLM runtime |

### Optional enrichments (non-blocking)

| Consumer | Optional parent / signal | Baseline when absent |
|----------|--------------------------|----------------------|
| `wordclouds` | `keyphrases` | Text-only cloud (1a ships baseline; enrichment after 1b) |
| `topic_modeling` / `bertopic` | `keyphrases` | Unenriched topic path |
| `moments` | soft features from `emotion` / `sentiment` / `topic_shift` | Salience fork still runs; reduced feature set + warnings |
| LLM modules | grounding context from `highlights` / `summary` | Ground on document per module notes; `narrative_summary` still hard-deps `summary` |

### Fallbacks / TX deps not in Wave 1

| TX dependency | Wave 1 resolution |
|---------------|-------------------|
| `insight_eligibility` | **`notebook_eligibility_v1` only** ([notebook-eligibility](contracts/notebook-eligibility.md)) — never ad-hoc stubs |
| `momentum` (for `moments`) | **Not ported** — `moments` = notebook salience `fork` |
| BERTopic / embeddings / transformer extras | Named capability `unavailable_extra` / `unavailable_model` — no silent substitute algorithm under the same module_id |
| Ollama | `unavailable_model`; deterministic `highlights` → `summary` → `insights` remains |

### No hard parents (standalone in Wave 1)

`stats`, `lexical_diversity`, `understandability`, `wordclouds` (baseline), `ner`, `sentiment`, `keyphrases`, `epistemic_markers`, `topic_modeling`, `bertopic`, `semantic_similarity`, `topic_shift`, `emotion`, `contextual_emotion`, `fine_grained_emotion`, `moments`, `highlights`, `llm_summary`, `llm_action_items`, `llm_custom_qa`

(Eligibility-required modules still depend on `notebook_eligibility_v1` **policy**, not a parent module artifact.)

```text
1a: stats, lexical_diversity, understandability, wordclouds
1b: ner, sentiment → entity_sentiment
    keyphrases (eligibility)
    epistemic_markers
1c: topic_modeling, bertopic (opt extra), semantic_similarity, topic_shift
1d: emotion, contextual_emotion, fine_grained_emotion
    emotion + sentiment → affect_tension
    moments (fork; soft signals optional)
1e: highlights (eligibility) → summary → narrative_summary
    highlights + topic_modeling → insights
    llm_summary, llm_action_items, llm_custom_qa (optional Ollama)
```

---

## 3. Product surfaces unlocked by Wave 1

Notebook UI is **not** a TX module picker clone. Target surfaces:

| Surface | Role | Primary Wave 1 feeds |
|---------|------|----------------------|
| **Overview** | Word count, pages, dates, lexical diversity, major entities, top themes | `stats`, `lexical_diversity`, `ner`, `keyphrases`, `topic_modeling` |
| **Themes** | Keyphrases, topics, clusters, shifts, recurring themes | `keyphrases`, `topic_modeling`, `bertopic`, `topic_shift`, `semantic_similarity` |
| **People & places** | NER, entity frequency over time, entity sentiment, co-occurrence | `ner`, `entity_sentiment` |
| **Mood & tone** | Sentiment/emotions over chronology, affect tension, certainty/hedging | `sentiment`, `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `epistemic_markers` |
| **Patterns** *(partial in W1)* | Repeated phrases, semantic echoes, recurring ideas | `keyphrases`, `semantic_similarity`, `topic_shift` — full echoes / loops → Wave 2–3 |
| **Moments** | Unusual / emotionally strong / high-information passages | `moments`, `highlights` |
| **Ask notebook** | Grounded custom QA | `llm_custom_qa` |
| **Summaries** | Notebook / month / section summaries, narrative, action items | `summary`, `insights`, `llm_summary`, `narrative_summary`, `llm_action_items`, `understandability`, `wordclouds` |

UI must distinguish capability states from [analysis-result.md](contracts/analysis-result.md): `success` / `partial` / `unavailable_extra` / `unavailable_model` / `insufficient_data` / `unavailable_dependency` / `failed` / empty findings vs true failure — never collapse these into one spinner or blank panel.

---

## 4. Phased delivery (sub-waves)

Ship in ordered decimal slices under thematic groups 1a–1e. **No next slice starts while unresolved architectural exceptions remain** (see [§10 exit criteria](#10-per-slice-exit-criteria)).

### Wave 1.1 — Infrastructure + first three modules (ship first)

| | |
|--|--|
| **Modules** | `stats`, `lexical_diversity`, `understandability` |
| **Also ship** | `page_v1` adapter, result envelope, project-local `analysis/` storage (lock-free compute + atomic publish), reopen reconcile, cache validation, `notebook_eligibility_v1` library (**not** on these modules’ runtime path), pin rows, compat fixtures, minimal Overview read-model |
| **Out** | `wordclouds` → **1.2**; `paragraph_v1`; eligibility-gated modules |
| **Unlocks** | Overview counts / diversity / readability |
| **Exit** | §10 + Wave 1.1 plan locks (stale publish, batch isolation, crash-boundary, ungated regression) |

### Wave 1.2 — Wordclouds (remainder of 1a)

| | |
|--|--|
| **Modules** | `wordclouds` locked to `enrichment_mode: "baseline"` (keyphrase enrichment only after deliberate 1b+ transition) |
| **Depends on** | 1.1 infra (runner/storage/envelope/Overview); mechanical pytest gate before coding |
| **Input** | Solely `AnalysisDocument.text` via `wordclouds_tokens_v1` (shared `TOKEN_RE` + pinned `wordclouds_stopwords_v1`) |
| **Payload** | `wordclouds_payload_v1` token weights; zero eligible tokens → `insufficient_data` |
| **Also ship** | Registry extension beyond `get_wave11_modules`; resolve-parents-before-identity (baseline → empty); Overview token-weight chart/table (PNG optional presentation only); pin row + provenance match |
| **Exit** | §10 + baseline ignore-matrix + 1.1 three-module non-regression + reopen/corrupt Overview bars |

### Wave 1.3 — Language foundations (start of 1b)

| | |
|--|--|
| **Modules** | `ner`, `sentiment`, `epistemic_markers` (ungated; no hard parents) |
| **Depends on** | 1.2 exit; `page_v1` chronology via unit `order` / optional `date` |
| **Payloads** | `ner_payload_v1`, `sentiment_payload_v1`, `epistemic_markers_payload_v1` |
| **Also ship** | NER → envelope `evidence[]`; spaCy optional → `unavailable_extra`; Overview entity + sentiment + hedging strips; pin rows; ungated regression |
| **Out** | `entity_sentiment`, `keyphrases` → **1.4**; `paragraph_v1`; Themes / full People & places |
| **Exit** | §10 + evidence/stale + 1.1/1.2 non-regression + no eligibility/hard-parent runtime path |

### Wave 1.4 — Language dependents (remainder of 1b)

| | |
|--|--|
| **Modules** | `entity_sentiment` (hard parents `ner`+`sentiment`), `keyphrases` (`notebook_eligibility_v1`) |
| **Depends on** | 1.3 exit; hard-parent resolver before identity |

### Wave 1c — Topics & similarity (completion)

| | |
|--|--|
| **Modules** | `topic_modeling` (may already be present), `semantic_similarity`, `topic_shift`, `bertopic` (optional extra) |
| **Depends on** | 1.4 exit; unit `order` chronology; eligibility for `topic_modeling` / `bertopic` |
| **Payloads** | `topic_modeling_payload_v1`, `semantic_similarity_payload_v1`, `topic_shift_payload_v1`, `bertopic_payload_v1` |
| **Also ship** | Themes surface; baseline ignore-matrix for optional `keyphrases` on topics/BERTopic; pin rows; `unavailable_extra` honesty for missing BERTopic |
| **Out** | Emotion family / moments → **1d**; silent BERTopic substitutes |
| **Exit** | §10 + ≥2-unit gates + 1.3/1.4 non-regression + Themes capability banners |

### Wave 1a — Foundations (thematic; delivered as 1.1 + 1.2)

Former umbrella for adapter + stats/lex/readability/clouds. Prefer decimal slices above for delivery tracking.

**Before 1.1 coding:** contracts indexed and frozen for document + envelope + storage + eligibility ([§9](#9-implementation-gate)).

**Before 1d/1e coding:** `paragraph_v1` splitter + stable span IDs proven ([analysis-document](contracts/analysis-document.md)); evidence render/stale rules exercised.

**Before 1e coding:** bounded-context / chunking policy ids defined for LLM modules ([analysis-result](contracts/analysis-result.md) + cache `llm` object in [analysis-run-storage](contracts/analysis-run-storage.md)); Ollama capability degradation wired.

### Wave 1b — Language

| | |
|--|--|
| **Modules** | `ner`, `sentiment`, `entity_sentiment`, `keyphrases`, `epistemic_markers` |
| **Depends on** | 1a adapter; `entity_sentiment` hard-deps `ner` + `sentiment` |
| **Unlocks** | **People & places**; Overview entities/themes; Mood hedging strip; Themes keyphrases |
| **Risk** | Medium — spaCy/NLP extras; OCR noise hurts NER/keyphrases (honest capability/warnings in UI) |
| **TX note** | `keyphrases` uses **`notebook_eligibility_v1`** (not TX eligibility / `tics`) |
| **Semantic class** | `adaptation` for eligibility substitution / speaker strip; `parity` only where fixtures justify it |

### Wave 1c — Topics & similarity

| | |
|--|--|
| **Modules** | `topic_modeling`, `bertopic`, `semantic_similarity`, `topic_shift` |
| **Depends on** | 1a units with stable `order` (+ optional `date`); optional keyphrases enrichment from 1b |
| **Unlocks** | **Themes**; chronology topic-shift strip; Patterns (partial) |
| **Risk** | High for `bertopic` / embeddings (optional extras). Mark BERTopic optional → `unavailable_extra` when missing |
| **TX note** | Eligibility via `notebook_eligibility_v1` for topic modules that require it. `semantic_similarity` must not require multiple speakers. `topic_shift` uses unit order, not segment timestamps |
| **Determinism** | Fixed seeds where feasible. Prefer shape/invariant assertions for BERTopic; exact goldens only for stable lexical paths. Pin dependency/model versions when exactness is claimed |

### Wave 1d — Emotion & salience

| | |
|--|--|
| **Modules** | `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `moments` |
| **Depends on** | `paragraph_v1` available if span evidence needed; `affect_tension` → `emotion` + `sentiment`; optional soft signals for `moments` |
| **Unlocks** | **Mood & tone**; **Moments** |
| **Risk** | Medium–high — model extras; OCR text quality |
| **TX note** | `moments` does **not** pull `momentum`. Notebook salience fork — recorded as `fork` / `adaptation` with `semantic_delta`, not an eligibility stub |
| **Semantic class** | `moments` = `fork` (or `adaptation`); emotion family typically `adaptation` if speaker assumptions removed |

### Wave 1e — Synthesis & LLM

| | |
|--|--|
| **Modules** | `highlights`, `summary`, `insights`, `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` |
| **Depends on** | Hard DAG above; LLMs → local Ollama capability; **bounded chunking policy** before implementation |
| **Unlocks** | **Summaries**; **Ask notebook**; richer Moments via highlights |
| **Risk** | LLM flakiness / groundedness; keep deterministic path offline |
| **TX note** | `highlights` / `insights` use `notebook_eligibility_v1`. LLM modules optional behind capability checks |
| **LLM delivery rules** | Follow [analysis-result](contracts/analysis-result.md) abstention/evidence/stale rules and [analysis-run-storage](contracts/analysis-run-storage.md) `llm` cache fields; recorded doubles use the same validation path as live Ollama |
| **Decimals** | **1e.0** `paragraph_v1` + `notebook_chunks_units_v1` + text Ollama; **1e.1** deterministic synthesis (+ 1.4/`topic_modeling` parents); **1e.2** LLM suite |

### Suggested ship order (summary)

```text
1.1 infra + stats/lex/readability
 → 1.2 wordclouds
 → 1.3 ner/sentiment/epistemic_markers
 → 1.4 entity_sentiment/keyphrases
 → 1c topics/similarity/shift
 → 1d emotion family + affect_tension + moments
 → 1e highlights/summary/insights + LLM suite
```

---

## 5. Per-slice checklists

Common port checklist (every module):

- [ ] Contracts + pin gate satisfied ([§9](#9-implementation-gate))
- [ ] Copy TX core with attribution; keep structure recognisable
- [ ] Exact TX pin row (concrete commit + file sha256) + `semantic_class` in [analysis_port_pins.md](dev/analysis_port_pins.md)
- [ ] Accept `AnalysisDocument` (or thin segment-shaped view produced by adapter)
- [ ] Emit **payload only**; adapter wraps [analysis-result](contracts/analysis-result.md) envelope
- [ ] No imports of Transcribe `Page` / Streamlit / project paths in core
- [ ] Durable write via analysis-run-storage rules (link — do not invent identity)
- [ ] Edge cases map to named outcomes/capabilities ([analysis-result](contracts/analysis-result.md))
- [ ] Minimum-input behaviour covered by fixtures (one-page, empty, short, all-blank as relevant)
- [ ] Compatibility fixtures: exact / tolerance / shape as appropriate ([§8](#8-compatibility-corpus-and-acceptance-tests))
- [ ] UI wires to the surface in §3 and distinguishes capability states

### 1a — Foundations

| Module | Port strategy | Units | Payload notes | Compat corpus |
|--------|---------------|-------|---------------|---------------|
| `stats` | Verbatim metrics; strip speaker rollups | page | counts, length dists | short 3-page notebook |
| `lexical_diversity` | Verbatim | page + doc aggregate | TTR / MTLD-style; refuse vs zero per contract | same + tiny-vocab case |
| `understandability` | Verbatim readability | page + doc | complexity scores; short-text path | same |
| `wordclouds` | Verbatim generation; keyphrase overlay **optional later** | doc | token weights from effective text | same |

### 1b — Language

| Module | Port strategy | Units | Payload notes | Compat corpus |
|--------|---------------|-------|---------------|---------------|
| `ner` | Verbatim; map spans → validated evidence | page (para if long) | entities + renderable evidence | entity-rich + OCR-noise |
| `sentiment` | Verbatim | page | polarity vs `order`/`date` | mixed-tone |
| `entity_sentiment` | Verbatim; hard parents | page | entity → sentiment | same |
| `keyphrases` | Verbatim ranking; **`notebook_eligibility_v1`** | page + doc | phrases + scores | thematic + empty-eligible |
| `epistemic_markers` | Verbatim lexicon/rules | page | hedge/certainty rates | hedging-heavy |

### 1c — Topics & similarity

| Module | Port strategy | Units | Payload notes | Compat corpus |
|--------|---------------|-------|---------------|---------------|
| `topic_modeling` | Verbatim LDA/NMF; eligibility | page as “doc” | topics + loadings; fixed seeds | multi-theme; single-page → insufficient |
| `bertopic` | Optional extra; same eligibility | page | shape/invariant tests; `unavailable_extra` if missing | same |
| `semantic_similarity` | Verbatim; **drop** multi-speaker gate | page | matrix / motifs; ≥2 units | near-duplicate; one-page refuse |
| `topic_shift` | Detector over **order** | page | shift boundaries; ≥2 units | ordered theme-change |

### 1d — Emotion & salience

| Module | Port strategy | Units | Payload notes | Compat corpus |
|--------|---------------|-------|---------------|---------------|
| `emotion` | Verbatim lexicon path | page | label dists; model/lexicon in provenance | affective |
| `contextual_emotion` | Verbatim; optional heavy | page ± neighbors | window = order neighbors | same |
| `fine_grained_emotion` | Verbatim; optional heavy | page / para | multi-label; capability on missing extra | same |
| `affect_tension` | Verbatim; hard-dep emotion+sentiment | page | tension vs order | conflicting-tone |
| `moments` | **Fork**: notebook salience (no momentum) | page or `paragraph_v1` | ranked unit ids + scores + evidence | spike fixture |

### 1e — Synthesis & LLM

| Module | Port strategy | Units | Payload notes | Compat corpus |
|--------|---------------|-------|---------------|---------------|
| `highlights` | Verbatim quote-forward; eligibility | `paragraph_v1` preferred | quotes + renderable evidence | highlight-rich |
| `summary` | Verbatim from highlights | doc | executive brief | same |
| `insights` | Verbatim assembly; hard parents | doc | structured insights | same |
| `llm_summary` | Port prompts/flow; Ollama optional | doc / chunks | abstractive + digest; abstain rules; bounded context | offline / recorded double |
| `llm_action_items` | Same | doc / chunks | tasks / decisions / open questions | same |
| `llm_custom_qa` | Grounded path; citations required | user Q + chunks | answers + evidence; refuse unsupported | grounded QA |
| `narrative_summary` | Port; hard-dep `summary` | doc | narrative rollup | same |

---

## 6. LLM modules (in Wave 1, optional at runtime)

Keep `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` in Wave 1 so Summaries / Ask notebook are first-class — but:

| Rule | Detail |
|------|--------|
| **Optional Ollama** | Deterministic synthesis (`highlights` → `summary` → `insights`) must work with LLM offline |
| **Honesty labeling** | UI marks LLM outputs; capability `unavailable_model` when runtime missing |
| **Contract-owned** | Abstention, stale evidence, bounded chunking, and `llm` cache-identity fields — [analysis-result](contracts/analysis-result.md), [analysis-run-storage](contracts/analysis-run-storage.md) |
| **Test doubles** | Recorded responses must hit the same validation/abstention path as live Ollama |
| **No speaker LLM** | `llm_speaker_summary` stays Wave 4 (do not port) |
| **Large notebooks** | Define and pin chunking/reduction policy ids **before** 1e implementation — do not assume the full notebook fits the model context window |

---

## 7. Explicit non-goals for Wave 1

- No shared `transcriptx-analysis` library extraction
- No voice / speaker / pause / interaction / contagion ports
- No rewriting cores to import Transcribe `Page` objects or Streamlit state
- No Wave 2 reinterpretations (`politeness`, `echoes`, `temporal_dynamics`, `momentum`, clean-text exports, `chart_descriptions`)
- No new `ocr_quality` (Wave 2 special case; not a TX port)
- No synthetic timestamps or fake speakers to appease TX APIs
- No documenting analysis as shipped until modules are implemented
- No in-place external-notebook / JPEGs-at-root / `.transcribe/` derived-state layout
- No global authoritative analysis store
- No treating `analysis/` introduction as a project-layout migration
- No second PRODUCT copy of storage / cache-identity / outcome / atomicity rules
- No ad-hoc per-module `insight_eligibility` stubs

---

## 8. Compatibility corpus and acceptance tests

Maintain a small fixture set under Transcribe tests (exact path chosen at implementation):

| Fixture | Purpose |
|---------|---------|
| Minimal 3-page notebook | smoke all 1a metrics |
| One-page / empty / all-blank OCR | minimum-input + refusal vs empty-success |
| Very short pages / OCR noise | eligibility + NER/keyphrase honesty |
| Entity / theme-rich | NER, keyphrases, topics |
| Chronology shift | topic_shift + sentiment/emotion series |
| Affective / tension | emotion family + affect_tension |
| Malformed / empty units (adapter-level) | validation refusals |
| Grounded QA | llm_custom_qa evidence paths (recorded or live-optional) |

**Test layers (keep separate):**

| Layer | Use when |
|-------|----------|
| **Exact deterministic goldens** | Stable lexical/rule paths; pin dependency versions |
| **Tolerance-based statistical/model tests** | Embeddings, stochastic topic models with seeds; assert bounds not bit-identity |
| **Shape / invariant only** | BERTopic, heavy transformers when exactness is not promised |
| **TX ↔ Transcribe parity** | Only for behaviour **intentionally** preserved (`semantic_class: parity`); do not fail adaptations/forks against TX goldens |

**Required acceptance coverage** (specified now; implemented with each slice):

- Provenance pins present (concrete TX commit + file hashes); external dep identities when relevant
- Invalidation / cache reuse per analysis-run-storage (edit, reorder, include-exclude, config, parents, eligibility, model digest)
- Dependency parent mismatch → `unavailable_dependency`; no silent stale reuse
- Crash/reopen through Transcribe storage: interrupted attempts do not clobber published reusable results
- Optional-extra / model absence → named capability (`unavailable_extra` / `unavailable_model`), not tracebacks or ambiguous empty success
- Evidence round-trip: renderable quote + stale citation not shown against newer text
- E2E managed project → edit/reorder → rerun → stable unit ids where text+splitter unchanged; UI navigation via validated evidence / `source_ref`
- `notebook_eligibility_v1` policy tests ([notebook-eligibility](contracts/notebook-eligibility.md))

---

## 9. Implementation gate

No Wave 1 module may land until:

1. analysis-document, analysis-result, analysis-run-storage, and notebook-eligibility are written and indexed in [CONTRACT_INDEX.md](CONTRACT_INDEX.md)
2. [project-on-disk.md](contracts/project-on-disk.md) is reconciled (`analysis/` optional; sole layout authority)
3. `notebook_eligibility_v1` is the named sole Wave-1 eligibility policy in CONTRACT
4. AnalysisDocument schema v1 is treated as frozen (including split profiles, blank/excluded OCR membership, uniqueness/ordering)
5. Result envelope v1 is treated as frozen (ports supply payloads only)
6. The module has an exact TX pin row (concrete commit) and semantic classification in [analysis_port_pins.md](dev/analysis_port_pins.md)
7. Slice-specific prerequisites hold (`paragraph_v1` before 1d/1e span evidence; LLM chunking policy before 1e)
8. Acceptance tests required above exist for that module’s claims

---

## 10. Per-slice exit criteria

A sub-wave is **done** only when all of the following hold. The next slice must not start with open architectural exceptions.

| Criterion | Evidence |
|-----------|----------|
| **Contract coverage** | Slice modules’ I/O, parents, eligibility, and min-input map to existing CONTRACT sections (gaps fixed in contracts first, not in ad-hoc code) |
| **Dependency / capability tests** | Hard parents, optional enrichments, and unavailable-extra/model paths pass |
| **Crash / reopen** | Interrupted attempt + process reopen proven through Transcribe `analysis/` storage (published artifact preserved) |
| **Compatibility fixtures** | Exact / tolerance / shape layers pass for modules in the slice |
| **UI honesty** | Surfaces distinguish unavailable / failed / empty-success / success / partial |
| **Pins** | Every landed module has concrete TX commit + file hashes + `semantic_class` |
| **No silent authority drift** | No new storage/cache/outcome rules introduced only in PRODUCT or code comments |

---

## 11. Decisions (residuals)

**Resolved in contracts / this plan (not free at coding time):**

- Adapter architecture + frozen `AnalysisDocument` v1
- Canonical effective-text representation + document concatenation
- `page` / `paragraph_v1` split profiles and derived-unit identity
- Managed-library boundary + project-local `analysis/`
- Result envelope v1; ports supply payloads
- Cache identity dimensions (formula in analysis-run-storage)
- Hard DAG + optional enrichments + eligibility policy
- Outcomes, capability vocabulary, refusal vs empty-success
- Evidence renderability + stale citation behaviour
- Sub-wave order 1a→1e; `ocr_quality` remains Wave 2
- Concrete TX commit provenance (not slogan-only `ported_from`)

**Still free (implementation detail only — must not affect durable identity):**

- Exact filenames / staging names under `analysis/` (illustrative pattern in analysis-run-storage)
- Which Overview widgets ship visually with 1a vs wait for 1b entities
- Non-identity UX copy and chart aesthetics
