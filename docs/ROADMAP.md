Type: PRODUCT
Authority: Product roadmap and sequencing. Does not define runtime contracts or shipped schemas. This roadmap describes product priorities and sequencing. Completed implementation detail lives in delivery-history documents and is not duplicated here.

# Transcribe roadmap

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Core delivery history (internal):** [analysis_wave1_plan.md](analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done · [−] deferred · [?] candidate (uncommitted)

## Current state

Transcribe has the complete 25-module core notebook-analysis set (pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md); slices **1.1 → 1e.2** in [analysis_wave1_plan.md](analysis_wave1_plan.md)). Current work is product hardening: durable analysis execution, freshness/health semantics, provenance-aware export, and simplification of Analyse UX. No additional analysis modules are scheduled. Architecture is verbatim-ish analytical cores plus thin notebook adapters over canonical `AnalysisDocument` units; durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)). Historical port implementation gates live in [analysis_wave1_plan.md §9](analysis_wave1_plan.md#9-implementation-gate).

---

## Now — Product hardening — [~] active

Priority after shipping the core module set. **Do not** schedule deferred-reinterpretation ports while this focus is open.

Phased checklist (see product hardening plan): **#10 → #3/#4 → #1/#2 → #5/#6 → #11/#12 → #13 → #7–9**.

| Phase | Status | Outcome |
|-------|--------|---------|
| **1** — #10, #3, #4 | [x] | Analyse has one launcher and one freshness authority |
| **2** — #1, #2 | [ ] | Runs survive UI/process interruption and execute from frozen inputs |
| **3** — #5, #6 | [ ] | Users can trust exactly what a preset will run |
| **4** — #11, #12 | [ ] | Every analysis surface gives the same answer to “is this current and healthy?” |
| **5** — #13 | [ ] | Exports identify exactly which notebook revision produced them |
| **6** — #7–9 | [ ] | Analyse surfaces are simplified around user tasks rather than module mechanics |

| Track | Intent |
|-------|--------|
| **Robustness** | Honest capability / cache / parent freshness; crash-reopen and stale-evidence behaviour; offline test coverage for shipped modules; clearer failure and empty-success paths |
| **Analyse UX** | One batch run action, one freshness model, Ask remains ad-hoc; deepen Overview / Themes / Mood / Moments / Summaries as read-models |
| **Payload polish** | Optional dedicated People & places or Patterns tabs, and deliberate keyphrase enrichment for wordclouds/topics, only when they improve the **current** module set — not as a back door for deferred reinterpretations |
| **OCR text quality** | Prefer existing **second-pass LLM OCR cleanup / verification** (and review edits) over a separate `ocr_quality` analysis module |

Infra checklist already landed for the core set: [analysis_wave1_hardening_plan.md](analysis_wave1_hardening_plan.md). Further work stays deepen-in-place on shipped surfaces and contracts.

**Exit gate:** Hardening closes when crash/reopen behaviour, stale detection, offline operation, export provenance, and normal Analyse workflows are covered by acceptance tests, and no ordinary user workflow requires understanding module/cache internals.

---

## Next — Notebook corpus / bulk import — [ ] planned (contracts first)

Prospective **bulk-import generation** contracts are written; runtime remains `transcribe.project` v1 until the activation gate.

| Gate | Authority |
|------|-----------|
| Corpus identity, index, locks | [contracts/notebook-corpus.md](contracts/notebook-corpus.md) |
| Managed originals / duplicates | [contracts/source-asset.md](contracts/source-asset.md) |
| ImportRun / plan / resume | [contracts/import-run.md](contracts/import-run.md) |
| Doctor + executable acceptance suite | [contracts/corpus-integrity.md](contracts/corpus-integrity.md) |

**Do not** ship bulk-import UI/CLI as supported until the [acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is green (crash-injection, idempotency, duplicate policy, corpus-index recovery, deep doctor on a synthetic multi-notebook corpus).

Suggested implementation order after activation work starts: corpus index → ImportRun/plan → duplicate policy on commit → corpus doctor → synthetic suite → only then bulk UI.

---

## Next — Product workflow improvements

Candidate priorities to rank **after** the hardening exit gate. Not ordered; not committed.

- **Review UX** — faster correction and approval of OCR text and dates
- **Archive / search** — findability across notebooks and timeline
- **Export / readability** — clearer notebooks for reading and sharing
- **Analyse information architecture** — validate that Overview / Themes / Mood / Moments / Summaries / Ask match how people actually use analysis
- **OCR cleanup quality** — improve second-pass cleanup / verification without a separate analysis module
- **People & places / Patterns** — promote to dedicated surfaces only if usage justifies it

---

## Shipped capabilities

| Capability | Shipped |
|------------|---------|
| **Notebook metrics** | stats, lexical diversity, understandability |
| **Language** | NER, sentiment, epistemic markers, entity sentiment, keyphrases |
| **Themes** | wordclouds, topic modeling, BERTopic, semantic similarity, topic shift |
| **Mood & salience** | emotion family, affect tension, moments |
| **Synthesis** | highlights, summary, insights |
| **Optional local LLM** | summary, action items, Ask notebook, narrative summary |

Exact module IDs, dependency history, slices 1.1–1e.2, TX pins, and implementation gates: [analysis_wave1_plan.md](analysis_wave1_plan.md). Disposition and notebook reinterpret notes: [analysis_module_porting.md](analysis_module_porting.md).

LLM modules are optional at runtime (local text Ollama); deterministic `highlights` → `summary` → `insights` work offline.

---

## Deferred analysis candidates — not scheduled — [−]

**Decision (2026-08-09):** Reinterpretation module work is **deferred**. Product focus is robustness and UX for the shipped core set (see **Now**). Need for these notebook reinterpretation outputs is unproven; do not schedule them until hardening closes and product revisits the disposition map.

**`ocr_quality` deferred specifically:** a dedicated OCR-quality analysis module is not scheduled. Prefer improving transcribed text via the existing **second-pass LLM OCR cleanup / verification** path (and human review edits). Revisit only if cleanup + review leave a clear, user-facing quality gap that analysis (not OCR) should own.

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

## Future analysis candidates — uncommitted

Worth considering only after hardening and any deliberate reopen of deferred rows. Several need a content-generic redesign or a new module identity. These are **not** planned work.

| Module / target | Notebook angle |
|-----------------|----------------|
| `tics` | Recurring phrases / habitual wording |
| `insight_eligibility` | Keep if made content-generic |
| `qa_analysis` | Self-posed questions and subsequent answers |
| `acts` | Note-type classification (observation / question / task / reflection) |
| `conversation_loops` | Recurring unresolved themes — implement **separately**; do not pretend it is the same module |

---

## Explicit non-goals / do-not-port

Intrinsically transcript-, speaker-, or audio-specific. Documented so they are not accidentally scheduled. Exhaustive module list: [analysis_module_porting.md](analysis_module_porting.md).

| Family | Examples |
|--------|----------|
| **Speaker interaction** | `interactions`, `contagion` |
| **Audio / timing** | `pauses`, `voice_*` family, `prosody_dashboard` |
| **ASR-specific** | `transcript_quality` (notebook `ocr_quality` remains deferred above) |
| **Speaker-conditioned synthesis** | `llm_speaker_summary` |

---

## Product scope beyond analysis modules

Still active product scope — often more central to Transcribe than speculative analysis work:

- **OCR pipeline** — import, vision OCR, optional second-pass cleanup
- **Notebook corpus / bulk import** — contracts first; activation gated — [notebook-corpus](contracts/notebook-corpus.md) · [corpus-integrity](contracts/corpus-integrity.md)
- **Review UX** — page correction, dates, approval
- **Archive / search** — workspace index and timeline
- **Export** — notebook readability and sharing (`transcribe.notebook`)
- **Runtime** — Docker / local Ollama operations — [runtime/docker.md](runtime/docker.md)
- **Future TranscriptX import adapter** — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (not a dependency)

---

## Future metadata

- Page **time-of-day** metadata (from diary stamps like `YYMMDD HHMM` / similar): storage alongside `ApproximateDate`, UI, archive indexing, and analysis policy TBD. Date auto-extraction currently ignores time.
