Type: PRODUCT
Authority: TranscriptX → Transcribe analysis-module porting dispositions and notebook reinterpret notes. Does not define runtime contracts or shipped module IDs.

# Analysis module porting (from TranscriptX)

Planning map for which TranscriptX analysis modules to bring into Transcribe, how to adapt them for page/notebook text, and which to leave behind.

Transcribe is page-first OCR text, not timed speaker segments. Modules that assume speakers, turns, audio, prosody, or ASR word confidence do not transfer as-is. See also [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) and [ROADMAP.md](ROADMAP.md).

**Disposition legend**

| Disposition | Meaning |
|-------------|---------|
| **Port early** | Strong fit; port with page/notebook unit of analysis |
| **Reinterpret** | Useful idea; redesign semantics for notebooks |
| **Later** | Interesting after core analysis exists; may need a new module identity |
| **Do not port** | Intrinsically transcript/audio/interpersonal; out of scope |
| **New (special case)** | Notebook analogue of a TranscriptX idea; implement fresh, do not port the TX code |

**Wave** column matches [ROADMAP.md](ROADMAP.md) delivery waves.

---

## Porting table

| Module | TX UI group | Disposition | Wave | Notebook notes |
|--------|-------------|-------------|------|----------------|
| `stats` | Foundations | Port early | 1 | Page/notebook length, token counts, distributions over pages |
| `ner` | Language & Meaning | Port early | 1 | Entities across pages; page-span evidence |
| `sentiment` | Language & Meaning | Port early | 1 | Page- or span-level polarity on notebook text |
| `entity_sentiment` | Language & Meaning | Port early | 1 | Sentiment toward entities in notes |
| `keyphrases` | Language & Meaning | Port early | 1 | Keyphrases pooled by page / notebook |
| `epistemic_markers` | Language & Meaning | Port early | 1 | Hedging / certainty markers in handwritten prose |
| `understandability` | Language & Meaning | Port early | 1 | Readability / complexity of transcribed text |
| `lexical_diversity` | Language & Meaning | Port early | 1 | Diversity metrics over notebook vocabulary |
| `wordclouds` | Visualisations | Port early | 1 | Wordclouds from effective/edited text |
| `semantic_similarity` | Language & Meaning | Port early | 1 | Similarity across pages or notebooks |
| `topic_modeling` | Language & Meaning | Port early | 1 | Topics over page corpus |
| `bertopic` | Language & Meaning | Port early | 1 | Optional BERTopic path over pages |
| `topic_shift` | Dynamics & Flow | Port early | 1 | Topic change along page order / chronology |
| `emotion` | Language & Meaning | Port early | 1 | Emotion labels on notebook text |
| `contextual_emotion` | Language & Meaning | Port early | 1 | Context-aware emotion over surrounding pages/spans |
| `fine_grained_emotion` | Language & Meaning | Port early | 1 | Finer emotion taxonomy on text |
| `affect_tension` | Dynamics & Flow | Port early | 1 | Affect tension along notebook chronology |
| `moments` | Dynamics & Flow | Port early | 1 | Salient moments as pages/spans, not timed turns |
| `highlights` | Summary & Synthesis | Port early | 1 | Highlight extraction from notebook text |
| `summary` | Summary & Synthesis | Port early | 1 | Deterministic / hybrid notebook summary |
| `insights` | Summary & Synthesis | Port early | 1 | Structured insights from module outputs |
| `llm_summary` | Summary & Synthesis | Port early | 1 | Local LLM notebook summary (optional) |
| `llm_action_items` | Summary & Synthesis | Port early | 1 | Tasks / decisions / open questions from notes |
| `llm_custom_qa` | Summary & Synthesis | Port early | 1 | User questions answered against notebook text |
| `narrative_summary` | Summary & Synthesis | Port early | 1 | Narrative rollup of notebook content |
| `politeness` | Speakers & Interaction | Reinterpret | 2 | → tone / formality of notes (not interpersonal politeness) |
| `echoes` | Speakers & Interaction | Reinterpret | 2 | → repeated ideas/phrases across pages or notebooks |
| `temporal_dynamics` | Foundations | Reinterpret | 2 | → change through notebook chronology / page order |
| `momentum` | Dynamics & Flow | Reinterpret | 2 | → density / idea-flow rather than conversational flow |
| `transcript_output` | Foundations | Reinterpret | 2 | → clean notebook text / export surface |
| `simplified_transcript` | Foundations | Reinterpret | 2 | → simplified / cleaned notebook text |
| `chart_descriptions` | Summary & Synthesis | Reinterpret | 2 | Still applicable once notebook analysis charts exist |
| `ocr_quality` | *(new)* | New (special case) | 2 | **Do not port** `transcript_quality`. New module from OCR confidence, uncertain spans, page quality, handwriting legibility, correction rate, etc. |
| `tics` | Foundations | Later | 3 | → recurring phrases / habitual wording in notes |
| `insight_eligibility` | Foundations | Later | 3 | Survive if made content-generic (not transcript-genre gated) |
| `qa_analysis` | Speakers & Interaction | Later | 3 | Self-posed questions and subsequent answers in notes |
| `acts` | Speakers & Interaction | Later | 3 | → note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Speakers & Interaction | Later | 3 | Recurring unresolved themes — prefer a **separate** module rather than pretending it is the same |
| `interactions` | Speakers & Interaction | Do not port | 4 | Speaker turn-taking / equity; no speakers |
| `pauses` | Foundations | Do not port | 4 | Timed silence; no audio timeline |
| `transcript_quality` | Foundations | Do not port | 4 | ASR confidence scorecard; replace with new `ocr_quality` (Wave 2) |
| `llm_speaker_summary` | Summary & Synthesis | Do not port | 4 | Speaker-conditioned LLM summary |
| `contagion` | Speakers & Interaction | Do not port | 4 | Interpersonal affect contagion unless deliberately redefined later |
| `voice_features` | Voice & Audio | Do not port | 4 | Audio feature extraction |
| `voice_mismatch` | Voice & Audio | Do not port | 4 | Voice / speaker-map mismatch |
| `voice_tension` | Voice & Audio | Do not port | 4 | Voice tension overlays |
| `voice_fingerprint` | Voice & Audio | Do not port | 4 | Speaker voice fingerprinting |
| `voice_charts_core` | Voice & Audio | Do not port | 4 | Voice chart gallery |
| `voice_contours` | Voice & Audio | Do not port | 4 | Pitch/prosody contours |
| `prosody_dashboard` | Voice & Audio | Do not port | 4 | Prosody / pitch family dashboard |

---

## Summary counts

| Disposition | Count |
|-------------|------:|
| Port early (Wave 1) | 25 |
| Reinterpret (Wave 2) | 7 |
| New special case (Wave 2) | 1 (`ocr_quality`) |
| Later (Wave 3) | 5 |
| Do not port (Wave 4) | 12 |

---

## Principles

1. **Page / notebook is the unit of analysis** — not speakers, turns, or wall-clock time.
2. **Prefer deepen-in-place** after a module lands; do not invent parallel IDs for the same user-facing object.
3. **Reinterpretations keep the TX name only when semantics stay close**; otherwise introduce a notebook-native id (e.g. `ocr_quality`, and a new id if conversation-loop analogues are rebuilt).
4. **Do not port** voice, prosody, pitch, pauses, interactions, speaker LLM summary, or interpersonal contagion as currently defined.
5. **No TranscriptX runtime dependency** — ports are conceptual / algorithmic reuse inside Transcribe, not imports from the TX package.
