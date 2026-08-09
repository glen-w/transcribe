Type: PRODUCT
Authority: TranscriptX → Transcribe analysis-module porting dispositions and notebook reinterpret notes. Does not define runtime contracts or shipped module IDs. Core delivery history (internal slices): [analysis_wave1_plan.md](analysis_wave1_plan.md).

# Analysis module porting (from TranscriptX)

Planning map for which TranscriptX analysis modules to bring into Transcribe, how to adapt them for page/notebook text, and which to leave behind.

**Core module set (Port early) is shipped** — see [ROADMAP.md](ROADMAP.md) and [analysis_wave1_plan.md](analysis_wave1_plan.md). **Deferred reinterpretations and `ocr_quality` are not scheduled**; current product focus is robustness and UX for the shipped modules ([ROADMAP.md](ROADMAP.md) **Now**). This map remains the disposition authority for deferred / later / out-of-scope rows when reopened.

Transcribe is page-first OCR text, not timed speaker segments. Modules that assume speakers, turns, audio, prosody, or ASR word confidence do not transfer as-is. See also [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md).

**Disposition legend**

| Disposition | Meaning |
|-------------|---------|
| **Port early** | Strong fit; port almost verbatim onto canonical analysis input (**core: done**) |
| **Reinterpret** | Useful idea; redesign semantics for notebooks |
| **Later** | Interesting after core analysis exists; may need a new module identity |
| **Do not port** | Intrinsically transcript/audio/interpersonal; out of scope |
| **New (special case)** | Notebook analogue of a TranscriptX idea; implement fresh, do not port the TX code |

**Slice** column uses internal delivery ids from [analysis_wave1_plan.md](analysis_wave1_plan.md). The core set was delivered as slices **1a–1e**. Product sequencing: [ROADMAP.md](ROADMAP.md).

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
- Core eligibility: sole named policy [`notebook_eligibility_v1`](contracts/notebook-eligibility.md) — no ad-hoc per-module insight_eligibility stubs.
- Small compatibility test corpus for TX ↔ Transcribe diffs (implementation-time).
- Chronology = unit `order` + optional `date` — no synthetic wall-clock or fake speakers.

Full detail: [analysis_wave1_plan.md](analysis_wave1_plan.md).

---

## Notebook UI surfaces ↔ core modules

Shipped Workflow tabs are marked **UI**. People & places / Patterns remain payload feeds without dedicated tabs.

| Surface | Status | Core feeds |
|---------|--------|----------------|
| **Overview** | UI | `stats`, `lexical_diversity`, `ner`, `keyphrases`, `topic_modeling`, `wordclouds`, `understandability` |
| **Themes** | UI | `keyphrases`, `topic_modeling`, `bertopic`, `topic_shift`, `semantic_similarity` |
| **People & places** | payload only | `ner`, `entity_sentiment` |
| **Mood & tone** | UI | `sentiment`, `emotion`, `contextual_emotion`, `fine_grained_emotion`, `affect_tension`, `epistemic_markers` |
| **Patterns** (partial) | payload only | `keyphrases`, `semantic_similarity`, `topic_shift` — full echoes / loops deferred with reinterpretation / later rows |
| **Moments** | UI | `moments`, `highlights` |
| **Ask notebook** | UI | `llm_custom_qa` |
| **Summaries** | UI | `summary`, `insights`, `llm_summary`, `narrative_summary`, `llm_action_items` |

---

## Porting table

| Module | TX UI group | Disposition | Slice | Notebook notes |
|--------|-------------|-------------|------|----------------|
| `stats` | Foundations | Port early | 1.1 | Page/notebook length, token counts, distributions over units |
| `lexical_diversity` | Language & Meaning | Port early | 1.1 | Diversity metrics over notebook vocabulary |
| `understandability` | Language & Meaning | Port early | 1.1 | Readability / complexity of transcribed text |
| `wordclouds` | Visualisations | Port early | 1.2 | Baseline token cloud from `AnalysisDocument.text` (`enrichment_mode: baseline`); keyphrase enrichment deferred to deliberate later mode/`module_version` transition |
| `ner` | Language & Meaning | Port early | 1.3 | Entities across pages; evidence via `source_ref`; spaCy optional |
| `sentiment` | Language & Meaning | Port early | 1.3 | Unit-level polarity; chronology via order/date |
| `epistemic_markers` | Language & Meaning | Port early | 1.3 | Hedging / certainty markers in handwritten prose |
| `entity_sentiment` | Language & Meaning | Port early | 1.4 | Needs `ner` + `sentiment` |
| `keyphrases` | Language & Meaning | Port early | 1.4 | Use [`notebook_eligibility_v1`](contracts/notebook-eligibility.md); do not pull TX `insight_eligibility` |
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
| `politeness` | Speakers & Interaction | Reinterpret | 2 (deferred) | → tone / formality of notes (not interpersonal politeness) |
| `echoes` | Speakers & Interaction | Reinterpret | 2 (deferred) | → repeated ideas/phrases across pages or notebooks |
| `temporal_dynamics` | Foundations | Reinterpret | 2 (deferred) | → change through notebook chronology / page order |
| `momentum` | Dynamics & Flow | Reinterpret | 2 (deferred) | → density / idea-flow rather than conversational flow |
| `transcript_output` | Foundations | Reinterpret | 2 (deferred) | → clean notebook text / export surface |
| `simplified_transcript` | Foundations | Reinterpret | 2 (deferred) | → simplified / cleaned notebook text |
| `chart_descriptions` | Summary & Synthesis | Reinterpret | 2 (deferred) | Still applicable once notebook analysis charts exist |
| `ocr_quality` | *(new)* | New (special case) | 2 (deferred) | **Do not port** `transcript_quality`. Deferred: prefer second-pass LLM OCR cleanup/verification over a dedicated quality module. Revisit only if a clear analysis-owned gap remains. |
| `tics` | Foundations | Later | 3 | → recurring phrases / habitual wording in notes |
| `insight_eligibility` | Foundations | Later | 3 | Survive if made content-generic (not transcript-genre gated) |
| `qa_analysis` | Speakers & Interaction | Later | 3 | Self-posed questions and subsequent answers in notes |
| `acts` | Speakers & Interaction | Later | 3 | → note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Speakers & Interaction | Later | 3 | Recurring unresolved themes — prefer a **separate** module rather than pretending it is the same |
| `interactions` | Speakers & Interaction | Do not port | 4 | Speaker turn-taking / equity; no speakers |
| `pauses` | Foundations | Do not port | 4 | Timed silence; no audio timeline |
| `transcript_quality` | Foundations | Do not port | 4 | ASR confidence scorecard; notebook `ocr_quality` analogue remains deferred (prefer OCR cleanup/verification) |
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

| Disposition | Count | Status |
|-------------|------:|--------|
| Port early (core / 1a–1e) | 25 | **shipped** |
| Reinterpret (deferred) | 7 | **deferred** (need unproven; see ROADMAP) |
| New special case (deferred) | 1 (`ocr_quality`) | **deferred** (prefer OCR cleanup/verification) |
| Later | 5 | planned (after deepen-in-place) |
| Do not port | 12 | out of scope |

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
