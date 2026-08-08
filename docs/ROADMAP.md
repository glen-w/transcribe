Type: PRODUCT
Authority: Product roadmap and analysis-porting delivery waves. Does not define runtime contracts or shipped schemas.

# Transcribe roadmap

**Product focus today:** local-first handwritten notebook OCR (import → run → review → export).

**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)

> **Status legend:** [ ] planned · [~] in progress · [x] done

Analysis modules below are **planned ports / reinterpretations** from TranscriptX ideas. They are not shipped Transcribe features until explicitly implemented. Waves follow the porting dispositions in the map.

---

## Wave 1 — Strong fits (port early)

Direct ports of language, topic, emotion, and synthesis modules that work on notebook text with a page/notebook unit of analysis.

| Module | Notes |
|--------|--------|
| `stats` | Page/notebook distributions |
| `ner` | Entities with page-span evidence |
| `sentiment` | Polarity on notebook text |
| `entity_sentiment` | Sentiment toward entities |
| `keyphrases` | Phrases by page / notebook |
| `epistemic_markers` | Hedging / certainty |
| `understandability` | Readability / complexity |
| `lexical_diversity` | Vocabulary diversity |
| `wordclouds` | From effective/edited text |
| `semantic_similarity` | Across pages or notebooks |
| `topic_modeling` | Topics over page corpus |
| `bertopic` | Optional BERTopic path |
| `topic_shift` | Change along page order |
| `emotion` | Emotion on text |
| `contextual_emotion` | Context over surrounding pages/spans |
| `fine_grained_emotion` | Finer emotion taxonomy |
| `affect_tension` | Along notebook chronology |
| `moments` | Salient pages/spans |
| `highlights` | Highlight extraction |
| `summary` | Deterministic / hybrid summary |
| `insights` | Structured insights |
| `llm_summary` | Optional local LLM summary |
| `llm_action_items` | Tasks / decisions / open questions |
| `llm_custom_qa` | Custom Q&A over notebook text |
| `narrative_summary` | Narrative rollup |

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
