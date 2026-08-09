Type: PRODUCT
Authority: Product roadmap and analysis-porting delivery waves. Does not define runtime contracts or shipped schemas. Wave 1 detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

# Transcribe roadmap

**Product focus today:** local-first handwritten notebook OCR (import → run → review → export) plus **Wave 1 notebook analysis** on transcribed text.

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Wave 1 delivery plan:** [analysis_wave1_plan.md](analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done

**Wave 1 status: [x] done** (all 25 Port-early modules through 1e.2; pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md)). Waves 2–4 remain planned. Delivery detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

**Architecture (shipped):** verbatim-ish analytical cores + thin notebook adapters over canonical `AnalysisDocument` units — see [analysis_wave1_plan.md](analysis_wave1_plan.md). Cores do not import `Page` / Streamlit. UI surfaces today: Overview, Themes, Mood & tone, Moments, Summaries, Ask notebook (People & places / Patterns remain read-model feeds without dedicated tabs). Durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)).

**Implementation gate (historical for Wave 1; still required for later waves):** analysis contracts indexed, `notebook_eligibility_v1` CONTRACT ownership, exact TX pin + semantic class ([analysis_wave1_plan.md §9](analysis_wave1_plan.md#9-implementation-gate), [dev/analysis_port_pins.md](dev/analysis_port_pins.md)).

---

## Wave 1 — Strong fits (port early) — [x] done

Direct ports of language, topic, emotion, and synthesis modules. Delivered in sub-waves **1a–1e** (detail in [analysis_wave1_plan.md](analysis_wave1_plan.md)).

| Sub-wave | Status | Modules | Unlocks |
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

TX hard deps resolved for Wave 1: `insight_eligibility` → sole policy [`notebook_eligibility_v1`](contracts/notebook-eligibility.md); `momentum` → `moments` notebook salience fork. Do not pull Wave 2–3 modules early. Outcome/cache/DAG gates: [analysis-result](contracts/analysis-result.md) · [analysis-run-storage](contracts/analysis-run-storage.md). `ocr_quality` stays Wave 2.

| Module | Sub-wave | Status | Notes |
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

## Wave 2 — Reinterpret for notebooks (+ OCR quality) — [ ] planned

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

## Wave 3 — Potentially interesting later — [ ] planned

Worth considering after Waves 1–2; several need a content-generic redesign or a new module identity.

| Module / target | Notebook angle |
|-----------------|----------------|
| `tics` | Recurring phrases / habitual wording |
| `insight_eligibility` | Keep if made content-generic |
| `qa_analysis` | Self-posed questions and subsequent answers |
| `acts` | Note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Recurring unresolved themes — implement **separately**; do not pretend it is the same module |

---

## Wave 4 — Do not port — [x] documented (out of scope)

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
