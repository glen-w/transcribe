Type: PRODUCT
Authority: Product roadmap and analysis-porting delivery waves. Does not define runtime contracts or shipped schemas. Wave 1 detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

# Transcribe roadmap

**Product focus today:** local-first handwritten notebook OCR (import → run → review → export).

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Wave 1 delivery plan:** [analysis_wave1_plan.md](analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done

Analysis modules below are **planned ports / reinterpretations** from TranscriptX ideas. They are not shipped Transcribe features until explicitly implemented. Waves follow the porting dispositions in the map.

**Architecture (chosen):** verbatim-ish analytical cores + thin notebook adapters over canonical `AnalysisDocument` units — see [analysis_wave1_plan.md](analysis_wave1_plan.md). Do not rewrite modules for `Page` objects; UI is notebook surfaces (Overview, Themes, People & places, Mood & tone, Patterns, Moments, Ask notebook, Summaries), not a TX module-picker clone. Durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)).

**Implementation gate:** no Wave 1 module lands until analysis contracts are indexed, `notebook_eligibility_v1` has CONTRACT ownership, and the module has an exact TX pin + semantic class ([analysis_wave1_plan.md §9](analysis_wave1_plan.md#9-implementation-gate), [dev/analysis_port_pins.md](dev/analysis_port_pins.md)).

---

## Wave 1 — Strong fits (port early)

Direct ports of language, topic, emotion, and synthesis modules. Delivered in sub-waves **1a–1e** (detail + checklists in [analysis_wave1_plan.md](analysis_wave1_plan.md)).

| Sub-wave | Modules | Unlocks |
|----------|---------|---------|
| **1.1** Infra + first metrics | `stats`, `lexical_diversity`, `understandability` (+ adapter, `analysis/` storage, pins, Overview read-model) | Overview (counts / diversity / readability) |
| **1.2** Wordclouds | `wordclouds` | Wordcloud viz |
| **1.3** Language foundations | `ner`, `sentiment`, `epistemic_markers` | Overview entities; sentiment chronology; Mood hedging |
| **1.4** Language dependents | `entity_sentiment`, `keyphrases` | People & places; Themes keyphrases; hard-parent + eligibility |
| **1b** Language (thematic) | 1.3 + 1.4 | People & places; Overview entities; hedging |
| **1c** Topics & similarity | `topic_modeling`, `bertopic` (optional), `semantic_similarity`, `topic_shift` | Themes; chronology shifts; Patterns (partial) |
| **1d** Emotion & salience | `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `moments` | Mood & tone; Moments |
| **1e** Synthesis & LLM | `highlights`, `summary`, `insights`, `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` | Summaries; Ask notebook |
| **1e.0** LLM prerequisites | `paragraph_v1` adapter; `notebook_chunks_units_v1`; text Ollama client; `unavailable_model` wiring | Unlocks 1e.1/1e.2 |
| **1e.1** Deterministic synthesis | `highlights`, `summary`, `insights` (+ 1.4/1c parents) | Summaries offline |
| **1e.2** LLM suite | `llm_summary`, `llm_action_items`, `llm_custom_qa`, `narrative_summary` | Ask notebook; honesty labels |

LLM modules stay in Wave 1 but are **optional at runtime** (local Ollama); deterministic `highlights` → `summary` → `insights` must work offline. `llm_custom_qa` requires grounded unit evidence.

TX hard deps out of Wave 1: `insight_eligibility` → sole policy [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) (no ad-hoc stubs); `momentum` → `moments` notebook salience fork. Do not pull Wave 2–3 modules early. Outcome/cache/DAG gates: [analysis-result](contracts/analysis-result.md) · [analysis-run-storage](contracts/analysis-run-storage.md). Detail: [analysis_wave1_plan.md](analysis_wave1_plan.md). `ocr_quality` stays Wave 2.

| Module | Sub-wave | Notes |
|--------|----------|--------|
| `stats` | 1.1 | Unit/notebook distributions |
| `lexical_diversity` | 1.1 | Vocabulary diversity |
| `understandability` | 1.1 | Readability / complexity |
| `wordclouds` | 1.2 | Baseline token cloud from `AnalysisDocument.text`; keyphrase enrichment deferred |
| `ner` | 1.3 | Entities with `source_ref` evidence; spaCy optional |
| `sentiment` | 1.3 | Polarity vs page order/date |
| `epistemic_markers` | 1.3 | Hedging / certainty |
| `entity_sentiment` | 1.4 | Needs ner + sentiment |
| `keyphrases` | 1.4 | [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) |
| `topic_modeling` | 1c | Topics over page corpus |
| `bertopic` | 1c | Optional extra |
| `semantic_similarity` | 1c | No multi-speaker gate |
| `topic_shift` | 1c | Along order/date, not timestamps |
| `emotion` | 1d | Emotion on text |
| `contextual_emotion` | 1d | Neighbouring units |
| `fine_grained_emotion` | 1d | Finer taxonomy |
| `affect_tension` | 1d | Needs emotion + sentiment |
| `moments` | 1d | Notebook salience (no momentum) |
| `highlights` | 1e | Quote-forward spans |
| `summary` | 1e | From highlights |
| `insights` | 1e | Highlights + topics |
| `llm_summary` | 1e | Optional local LLM |
| `llm_action_items` | 1e | Tasks / decisions / open questions |
| `llm_custom_qa` | 1e | Grounded Ask notebook |
| `narrative_summary` | 1e | From deterministic summary |

---

## Wave 2 — Reinterpret for notebooks (+ OCR quality)

Useful TranscriptX ideas whose semantics must be redesigned for notebooks, plus one **new** foundations module.

| Module / target | Disposition | Notebook reinterpretation |
|-----------------|-------------|---------------------------|
| `politeness` | Reinterpret | → tone / formality |
| `echoes` | Reinterpret | → repeated ideas/phrases across pages or notebooks |
| `temporal_dynamics` | Reinterpret | → change through notebook chronology |
| `momentum` | Reinterpret | → density / idea-flow (not conversational flow) |
| `transcript_output` | Reinterpret | → clean notebook text / export |
| `simplified_transcript` | Reinterpret | → simplified / cleaned notebook text |
| `chart_descriptions` | Reinterpret | LLM descriptions once notebook charts exist |
| **`ocr_quality`** | **New (special case)** | Notebook analogue of TX `transcript_quality`, **not a port**. Base on OCR confidence, uncertain spans, page quality, handwriting legibility, correction rate, etc. |

---

## Wave 3 — Potentially interesting later

Worth considering after Waves 1–2; several need a content-generic redesign or a new module identity.

| Module / target | Notebook angle |
|-----------------|----------------|
| `tics` | Recurring phrases / habitual wording |
| `insight_eligibility` | Keep if made content-generic |
| `qa_analysis` | Self-posed questions and subsequent answers |
| `acts` | Note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Recurring unresolved themes — implement **separately**; do not pretend it is the same module |

---

## Wave 4 — Do not port

Intrinsically transcript-, speaker-, or audio-specific. Documented so they are not accidentally scheduled.

| Module | Why out of scope |
|--------|------------------|
| `interactions` | Speaker turn-taking / equity |
| `pauses` | Timed silence / audio timeline |
| `transcript_quality` | ASR confidence; replaced by new `ocr_quality` in Wave 2 |
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

## Outside analysis waves

Still product scope but not part of the TranscriptX analysis-porting programme:

- OCR pipeline, review UX, archive / search, exports (`transcribe.notebook`)
- Runtime / Docker / local Ollama operations — [runtime/docker.md](runtime/docker.md)
- Post–TranscriptX 1.0 import adapter — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)
