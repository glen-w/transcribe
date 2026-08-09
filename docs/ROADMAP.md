Type: PRODUCT
Authority: Product roadmap and analysis-porting delivery order. Does not define runtime contracts or shipped schemas. Core-module delivery history (internal slice ids): [analysis_wave1_plan.md](analysis_wave1_plan.md).

# Transcribe roadmap

**Product focus today:** local-first handwritten notebook OCR (import → run → review → export) plus **shipped core notebook analysis**, with active work on **robustness and Analyse UX** for that set. Deferred reinterpretations / `ocr_quality` are not scheduled.

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Core delivery history (internal):** [analysis_wave1_plan.md](analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done · [−] deferred

**Core module set: [x] done** (all 25 Port-early modules; pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md)). Internal delivery slices **1.1 → 1e.2**: [analysis_wave1_plan.md](analysis_wave1_plan.md).

**Current product focus:** deepen **robustness and UX** for the shipped analysis set — not new deferred-reinterpretation modules. Deferred reinterpretations and `ocr_quality` are **deferred** (see below). Later / do-not-port rows stay on the disposition map only.

**Architecture (shipped):** verbatim-ish analytical cores + thin notebook adapters over canonical `AnalysisDocument` units — see [analysis_wave1_plan.md](analysis_wave1_plan.md). Cores do not import `Page` / Streamlit. UI surfaces today: Overview, Themes, Mood & tone, Moments, Summaries, Ask notebook (People & places / Patterns remain read-model feeds without dedicated tabs). Durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)).

**Implementation gate (historical for the core port; still required if deferred rows are reopened):** analysis contracts indexed, `notebook_eligibility_v1` CONTRACT ownership, exact TX pin + semantic class ([analysis_wave1_plan.md §9](analysis_wave1_plan.md#9-implementation-gate), [dev/analysis_port_pins.md](dev/analysis_port_pins.md)).

---

## Now — Core robustness & UX — [~] active

Priority after shipping the 25 Port-early modules. **Do not** schedule deferred-reinterpretation ports while this focus is open.

| Track | Intent |
|-------|--------|
| **Robustness** | Honest capability / cache / parent freshness; crash-reopen and stale-evidence behaviour; offline test coverage for shipped modules; clearer failure and empty-success paths |
| **Analyse UX** | Make Overview / Themes / Mood & tone / Moments / Summaries / Ask notebook clearer and more usable (progress, banners, evidence navigation, run presets) without inventing new module IDs |
| **Payload polish** | Optional dedicated People & places or Patterns tabs, and deliberate keyphrase enrichment for wordclouds/topics, only when they improve the **current** module set — not as a back door for deferred reinterpretations |
| **OCR text quality** | Prefer existing **second-pass LLM OCR cleanup / verification** (and review edits) over a separate `ocr_quality` analysis module |

Infra checklist already landed for the core set: [analysis_wave1_hardening_plan.md](analysis_wave1_hardening_plan.md). Further work stays deepen-in-place on shipped surfaces and contracts.

---

## Core module set — Strong fits (port early) — [x] done

Direct ports of language, topic, emotion, and synthesis modules. Delivered in internal slices **1a–1e** (detail in [analysis_wave1_plan.md](analysis_wave1_plan.md)).

| Slice | Status | Modules | Unlocks |
|----------|--------|---------|---------|
| **1.1** Infra + first metrics | [x] | `stats`, `lexical_diversity`, `understandability` (+ adapter, `analysis/` storage, pins, Overview read-model) | Overview (counts / diversity / readability) |
| **1.2** Wordclouds | [x] | `wordclouds` | Wordcloud viz |
| **1.3** Language foundations | [x] | `ner`, `sentiment`, `epistemic_markers` | Overview entities; sentiment chronology; Mood hedging |
| **1.4** Language dependents | [x] | `entity_sentiment`, `keyphrases` | Themes keyphrases; hard-parent + eligibility (People & places via NER/entity_sentiment payloads) |
| **1b** Language (thematic) | [x] | 1.3 + 1.4 | Overview entities; hedging |
| **1c** Topics & similarity | [x] | `topic_modeling`, `bertopic` (optional), `semantic_similarity`, `topic_shift` | Themes; chronology shifts |
| **1d** Emotion & salience | [x] | `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `moments` | Mood & tone; Moments |
| **1e** Synthesis & LLM | [x] | `highlights`, `summary`, `insights`, `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` | Summaries; Ask notebook |
| **1e.0** LLM prerequisites | [x] | `paragraph_v1` adapter; `notebook_chunks_units_v1`; text Ollama client; `unavailable_model` wiring | Unlocks 1e.1/1e.2 |
| **1e.1** Deterministic synthesis | [x] | `highlights`, `summary`, `insights` (+ 1.4/1c parents) | Summaries offline |
| **1e.2** LLM suite | [x] | `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` | Ask notebook; honesty labels |

LLM modules are **optional at runtime** (local text Ollama); deterministic `highlights` → `summary` → `insights` work offline. `llm_custom_qa` requires grounded unit evidence.

TX hard deps resolved for the core set: `insight_eligibility` → sole policy [`notebook_eligibility_v1`](contracts/notebook-eligibility.md); `momentum` → `moments` notebook salience fork. Outcome/cache/DAG gates: [analysis-result](contracts/analysis-result.md) · [analysis-run-storage](contracts/analysis-run-storage.md). Do not pull deferred reinterpretation modules while the robustness/UX focus is active.

| Module | Slice | Status | Notes |
|--------|----------|--------|-------|
| `stats` | 1.1 | [x] | Unit/notebook distributions |
| `lexical_diversity` | 1.1 | [x] | Vocabulary diversity |
| `understandability` | 1.1 | [x] | Readability / complexity |
| `wordclouds` | 1.2 | [x] | Baseline token cloud from `AnalysisDocument.text`; keyphrase enrichment deferred |
| `ner` | 1.3 | [x] | Entities with `source_ref` evidence; spaCy optional |
| `sentiment` | 1.3 | [x] | Polarity vs page order/date |
| `epistemic_markers` | 1.3 | [x] | Hedging / certainty |
| `entity_sentiment` | 1.4 | [x] | Needs ner + sentiment |
| `keyphrases` | 1.4 | [x] | [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) |
| `topic_modeling` | 1c | [x] | Topics over page corpus |
| `bertopic` | 1c | [x] | Optional extra → `unavailable_extra` when missing |
| `semantic_similarity` | 1c | [x] | No multi-speaker gate |
| `topic_shift` | 1c | [x] | Along order/date, not timestamps |
| `emotion` | 1d | [x] | Emotion on text |
| `contextual_emotion` | 1d | [x] | Neighbouring units |
| `fine_grained_emotion` | 1d | [x] | Optional extra → `unavailable_extra` |
| `affect_tension` | 1d | [x] | Needs emotion + sentiment |
| `moments` | 1d | [x] | Notebook salience fork (no momentum) |
| `highlights` | 1e | [x] | Quote-forward spans |
| `summary` | 1e | [x] | From highlights |
| `insights` | 1e | [x] | Highlights + topics |
| `llm_summary` | 1e | [x] | Optional local LLM |
| `llm_action_items` | 1e | [x] | Tasks / decisions / open questions |
| `llm_custom_qa` | 1e | [x] | Grounded Ask notebook |
| `narrative_summary` | 1e | [x] | From deterministic summary; `unavailable_model` when LLM offline |

---

## Deferred — Reinterpret for notebooks (+ OCR quality) — [−] deferred

**Decision (2026-08-09):** Reinterpretation module work is **deferred**. Product focus is robustness and UX for the shipped core module set (see **Now** above). Need for these notebook reinterpretation outputs is unproven; do not schedule them until that focus closes and product revisits the disposition map.

**`ocr_quality` deferred specifically:** a dedicated OCR-quality analysis module is not scheduled. Prefer improving transcribed text via the existing **second-pass LLM OCR cleanup / verification** path (and human review edits). Revisit only if cleanup + review leave a clear, user-facing quality gap that analysis (not OCR) should own.

Disposition inventory retained for later reopen (not active delivery):

| Module / target | Disposition | Notebook reinterpretation |
|-----------------|-------------|---------------------------|
| `politeness` | Reinterpret | → tone / formality |
| `echoes` | Reinterpret | → repeated ideas/phrases across pages or notebooks |
| `temporal_dynamics` | Reinterpret | → change through notebook chronology |
| `momentum` | Reinterpret | → density / idea-flow (not conversational flow) |
| `transcript_output` | Reinterpret | → clean notebook text / export |
| `simplified_transcript` | Reinterpret | → simplified / cleaned notebook text |
| `chart_descriptions` | Reinterpret | LLM descriptions once notebook charts exist |
| **`ocr_quality`** | **New (special case)** | Notebook analogue of TX `transcript_quality`, **not a port**. Deferred — not a substitute for OCR cleanup/verification. |

---

## Later — Potentially interesting — [ ] planned

Worth considering only after core deepen-in-place and any reopened deferred reinterpretations; several need a content-generic redesign or a new module identity.

| Module / target | Notebook angle |
|-----------------|----------------|
| `tics` | Recurring phrases / habitual wording |
| `insight_eligibility` | Keep if made content-generic |
| `qa_analysis` | Self-posed questions and subsequent answers |
| `acts` | Note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Recurring unresolved themes — implement **separately**; do not pretend it is the same module |

---

## Out of scope — Do not port — [x] documented

Intrinsically transcript-, speaker-, or audio-specific. Documented so they are not accidentally scheduled.

| Module | Why out of scope |
|--------|------------------|
| `interactions` | Speaker turn-taking / equity |
| `pauses` | Timed silence / audio timeline |
| `transcript_quality` | ASR confidence; do not port. A notebook `ocr_quality` analogue remains deferred (prefer OCR cleanup/verification) |
| `llm_speaker_summary` | Speaker-conditioned summary |
| `contagion` | Interpersonal affect (unless deliberately redefined later as a new idea) |
| `voice_features` | Audio features |
| `voice_mismatch` | Voice / speaker-map mismatch |
| `voice_tension` | Voice tension |
| `voice_fingerprint` | Speaker fingerprinting |
| `voice_charts_core` | Voice charts |
| `voice_contours` | Pitch / prosody contours |
| `prosody_dashboard` | Prosody / pitch family |

---

## Outside analysis porting

Still product scope but not part of the TranscriptX analysis-porting programme:

- OCR pipeline, review UX, archive / search, exports (`transcribe.notebook`)
- Runtime / Docker / local Ollama operations — [runtime/docker.md](runtime/docker.md)
- Post–TranscriptX 1.0 import adapter — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)
