Type: PRODUCT
Authority: TranscriptX → Transcribe analysis-module porting dispositions and notebook reinterpret notes. Does not define runtime contracts or shipped module IDs. Wave 1 delivery detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

# Analysis module porting (from TranscriptX)

Planning map for which TranscriptX analysis modules to bring into Transcribe, how to adapt them for page/notebook text, and which to leave behind.

Transcribe is page-first OCR text, not timed speaker segments. Modules that assume speakers, turns, audio, prosody, or ASR word confidence do not transfer as-is. See also [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md), [ROADMAP.md](ROADMAP.md), and the detailed [Wave 1 plan](analysis_wave1_plan.md).

**Disposition legend**

| Disposition | Meaning |
|-------------|---------|
| **Port early** | Strong fit; port almost verbatim onto canonical analysis input |
| **Reinterpret** | Useful idea; redesign semantics for notebooks |
| **Later** | Interesting after core analysis exists; may need a new module identity |
| **Do not port** | Intrinsically transcript/audio/interpersonal; out of scope |
| **New (special case)** | Notebook analogue of a TranscriptX idea; implement fresh, do not port the TX code |

**Wave** column matches [ROADMAP.md](ROADMAP.md). Wave 1 splits into sub-waves **1a–1e** in the [Wave 1 plan](analysis_wave1_plan.md).

---

## Architecture (chosen)

Port analytical cores **almost verbatim**. Thin **notebook adapters** own project I/O. Modules must **not** be rewritten to understand notebooks, `Page` objects, or Streamlit state.

**Contracts first:** [analysis-document](contracts/analysis-document.md) · [analysis-result](contracts/analysis-result.md) · [analysis-run-storage](contracts/analysis-run-storage.md) · [notebook-eligibility](contracts/notebook-eligibility.md) · layout [project-on-disk](contracts/project-on-disk.md). Pins: [dev/analysis_port_pins.md](dev/analysis_port_pins.md).

```text
Managed notebook project (ingest copies sources/; external originals untouched)
     ↓
notebook_analysis_adapter (+ notebook_eligibility_v1 when required)
     ↓
AnalysisDocument (contract schema v1)
     ↓
ported TranscriptX module   (exact TX commit/file pin + semantic_class)
     ↓
analysis-result → project-local analysis/ storage (bound to project_id) → Notebook UI
```

| Transcribe owns | Ported core owns |
|-----------------|------------------|
| Managed project identity, page IDs, persistence under `analysis/`, invalidation, locking, UI | Scoring / ranking / clustering / inference on text+units |

- Copy modules with **exact TX pins** and `parity` / `adaptation` / `fork` classification. **Resist** extracting a shared `transcriptx-analysis` library until identical cores are obvious.
- Wave 1 eligibility: sole named policy [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) — no ad-hoc per-module insight_eligibility stubs.
- Small compatibility test corpus for TX ↔ Transcribe diffs (implementation-time).
- Chronology = unit `order` + optional `date` — no synthetic wall-clock or fake speakers.

Full detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

---

## Notebook UI surfaces ↔ Wave 1 modules

| Surface | Wave 1 feeds |
|---------|----------------|
| **Overview** | `stats`, `lexical_diversity`, `ner`, `keyphrases`, `topic_modeling` |
| **Themes** | `keyphrases`, `topic_modeling`, `bertopic`, `topic_shift`, `semantic_similarity` |
| **People & places** | `ner`, `entity_sentiment` |
| **Mood & tone** | `sentiment`, `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `epistemic_markers` |
| **Patterns** (partial) | `keyphrases`, `semantic_similarity`, `topic_shift` — echoes / loops later |
| **Moments** | `moments`, `highlights` |
| **Ask notebook** | `llm_custom_qa` |
| **Summaries** | `summary`, `insights`, `llm_summary`, `narrative_summary`, `llm_action_items`, `understandability`, `wordclouds` |

---

## Porting table

| Module | TX UI group | Disposition | Wave | Notebook notes |
|--------|-------------|-------------|------|----------------|
| `stats` | Foundations | Port early | 1a | Page/notebook length, token counts, distributions over units |
| `lexical_diversity` | Language & Meaning | Port early | 1a | Diversity metrics over notebook vocabulary |
| `understandability` | Language & Meaning | Port early | 1a | Readability / complexity of transcribed text |
| `wordclouds` | Visualisations | Port early | 1a | Wordclouds from effective/edited text |
| `ner` | Language & Meaning | Port early | 1b | Entities across pages; evidence via `source_ref` |
| `sentiment` | Language & Meaning | Port early | 1b | Unit-level polarity; chronology via order/date |
| `entity_sentiment` | Language & Meaning | Port early | 1b | Needs `ner` + `sentiment` |
| `keyphrases` | Language & Meaning | Port early | 1b | Use [`notebook_eligibility_v1`](contracts/notebook-eligibility.md); do not pull TX `insight_eligibility` |
| `epistemic_markers` | Language & Meaning | Port early | 1b | Hedging / certainty markers in handwritten prose |
| `topic_modeling` | Language & Meaning | Port early | 1c | Topics over page corpus; [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) |
| `bertopic` | Language & Meaning | Port early | 1c | Optional BERTopic extra |
| `semantic_similarity` | Language & Meaning | Port early | 1c | Across pages; no multi-speaker gate |
| `topic_shift` | Dynamics & Flow | Port early | 1c | Shifts along page order / dates, not timestamps |
| `emotion` | Language & Meaning | Port early | 1d | Emotion labels on notebook text |
| `contextual_emotion` | Language & Meaning | Port early | 1d | Context = neighbouring units by order |
| `fine_grained_emotion` | Language & Meaning | Port early | 1d | Finer emotion taxonomy |
| `affect_tension` | Dynamics & Flow | Port early | 1d | Needs `emotion` + `sentiment` |
| `moments` | Dynamics & Flow | Port early | 1d | Notebook salience (no TX `momentum`/pauses) |
| `highlights` | Summary & Synthesis | Port early | 1e | Quote-forward spans; [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) |
| `summary` | Summary & Synthesis | Port early | 1e | From highlights |
| `insights` | Summary & Synthesis | Port early | 1e | Needs highlights + topics; `notebook_eligibility_v1` |
| `llm_summary` | Summary & Synthesis | Port early | 1e | Optional local Ollama; honesty label |
| `llm_action_items` | Summary & Synthesis | Port early | 1e | Tasks / decisions / open questions |
| `llm_custom_qa` | Summary & Synthesis | Port early | 1e | Grounded QA with unit evidence |
| `narrative_summary` | Summary & Synthesis | Port early | 1e | LLM narrative from deterministic summary |
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
| Port early (Wave 1 / 1a–1e) | 25 |
| Reinterpret (Wave 2) | 7 |
| New special case (Wave 2) | 1 (`ocr_quality`) |
| Later (Wave 3) | 5 |
| Do not port (Wave 4) | 12 |

---

## Principles

1. **Canonical units, not Page objects** — adapters produce `AnalysisDocument`; cores stay TX-shaped.
2. **Contracts first** — schemas, outcomes/attempts, storage, eligibility, and dependency compatibility are CONTRACT-owned; PRODUCT summarises.
3. **Exact pins + semantic class** — no module lands without a [pin registry](dev/analysis_port_pins.md) row (`parity` / `adaptation` / `fork`).
4. **Managed-project storage** — durable analysis under project `analysis/`; no global analysis authority; no in-place `.transcribe/` layout.
5. **Prefer deepen-in-place** after a module lands; do not invent parallel IDs for the same user-facing object.
6. **Reinterpretations keep the TX name only when semantics stay close**; otherwise introduce a notebook-native id (e.g. `ocr_quality`, and a new id if conversation-loop analogues are rebuilt).
7. **Do not port** voice, prosody, pitch, pauses, interactions, speaker LLM summary, or interpersonal contagion as currently defined.
8. **No TranscriptX runtime dependency** — copy selected modules with exact pins; no imports from the TX package.
9. **Provenance + compatibility corpus** — every port records TX files + external analytical deps; fixtures support TX ↔ Transcribe diffs.
10. **Copy first; shared library later** — extract only when identical cores become obvious.
