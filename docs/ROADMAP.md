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

The roadmap’s analysis surface is largely complete. **Remaining product gaps are primarily notebook-corpus and product-lifecycle concerns** (living with many notebooks over years of models and upgrades), not more analysis capability.

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

**Related product outcome (not just ingestion mechanics):** an **import recovery / inbox** workflow — after dumping a large scan set, show what imported, what failed, what duplicated, what needs review, and let the user continue. This may become the natural corpus home screen.

---

## Next — Preprocessing system — [?] candidate / partial

Two separate lanes. Do not conflate human-facing scan cleanup with OCR input transforms.

| Lane | Audience | Default | Intent |
|------|----------|---------|--------|
| **1. Visual declutter** | Human (reading / review of scans) | **On** for imports; global off-switch in settings | Clean up scanned page images for people. **Shipped (v1):** `remove_scan_borders` (Pillow, deterministic contract). Applies at import only; existing notebooks are not rewritten until explicit re-import/reprocess. Render provenance records state, geometry, and declutter identity. |
| **2. OCR optimisation** | Vision model input | **Off** (`none`); opt-in | Transforms meant to help OCR. Shipped today: optional Pillow **`gentle_contrast`**. Further OCR preprocess profiles are **deferred**. |

**Rules of thumb**

- Visual declutter defaults help the common “dump of scans” path; power users can disable it workspace-wide (`ingest.visual_declutter_enabled`).
- OCR preprocess stays conservative and off-by-default so fingerprints / skip-resume stay predictable; expanding profiles is a deliberate product choice, not creep from declutter work.
- Declutter identity (`enabled` + `DECLUTTER_VERSION` + ordered ops + frozen detection params) is frozen into ingest journal / render provenance; crash recovery never pairs mismatched pixels and metadata. OCR invalidation follows the final active render SHA.
- Re-OCR / reprocessing (lifecycle below) may eventually re-apply either lane with explicit user choice; that does not change the defaults above.

**Later — visual declutter expansion (Pillow-only, uncommitted)**

Stay outside the page: high-confidence, edge-anchored artefacts only — never alter pixels inside the detected page area. That keeps declutter distinct from document restoration (no bleed-through, whitening, stains, ruled lines, hole punching, creases, page-wide shadow fix, or handwritten-margin cleanup).

Suggested sequence after scanner-bed borders: **generic uniform overscan** → **binding gutter** → **edge shadows** → **obvious corner wedges**. Other safe candidates when detection is conservative: scanner lid/background slivers (uniform non-page edge bands), blank overscan margins (strong four-side page/background boundary), punch-hole *margins* (trim blank outer strip only), scanner calibration stripes, and combined page-edge-shadow + exposed-bed as one page-boundary problem rather than stacked aggressive ops.

---

## Next — Corpus & product lifecycle — [?] candidates

Primary post-hardening product direction once corpus contracts activate. Rank after the hardening exit gate; **not ordered; not committed**. These matter more than additional analysis modules as users accumulate notebooks and OCR models improve.

| Outcome | Intent |
|---------|--------|
| **Search (first-class)** | Full-text across notebooks; date / tag / entity filters; jump-to-page; eventually saved searches. With dozens of notebooks this may matter more than Analyse. |
| **Notebook organisation** | Titles, descriptions, tags/collections, archive state, sort order, cover/thumbnail, lightweight notebook metadata — how users live with a multi-notebook corpus. |
| **Re-OCR / reprocessing** | Explicit “rerun this page/notebook with a better model / prompt / cleanup setting”; compare attempts; preserve human edits; safely promote a new result. |
| **Import recovery / inbox** | Continuations of bulk import as a daily workflow (see above), not only the ImportRun machine. |
| **Reading mode** | Clean chronological in-app reading: page image/text pairing, dates, navigation, optional distraction-free layout — distinct from Review, Analyse, and export. |
| **Backup / restore / portability** | Product commitment that the whole corpus can be backed up, moved, restored, and verified without application-specific archaeology. |
| **Data longevity / upgrades** | Notebooks survive Transcribe upgrades: migration UX, pre-upgrade backup, refusal/recovery, and “archive remains readable without Transcribe” where feasible — broader than schema contracts alone. |
| **Model & runtime management** | Comprehensible UX over installed OCR/text models: availability, size, last-used, refresh, health, recommendations. Ollama machinery exists; users need a product abstraction. |
| **Quality / evaluation loop** | Alongside thumbs: sampled OCR accuracy review, cleanup accept/reject, analysis usefulness ratings, local regression fixtures — local evidence that changes improve Transcribe, not analytics telemetry. |
| **Prompt management UI** | Browse/edit versioned OCR and analysis prompts (project `prompts/` reserved); beyond today’s per-job pick + optional override. |
| **Prompt-backed Detection** | Scan notebook pages for built-in or custom phenomena (poetry, lists, etc.); cross-page spans; findings under `detection/` with provenance. See detection contracts. |
| **Quality ratings (thumbs)** | Collect-only local ratings for transcription and analysis outputs; shape/code from TranscriptX LLM feedback v1 — not a substitute for deferred `ocr_quality` analysis. |
| **Review UX** | Faster correction and approval of OCR text and dates. |
| **Export / readability** | Clearer notebooks for reading and sharing outside the app. |
| **Analyse information architecture** | Validate Overview / Themes / Mood / Moments / Summaries / Ask against real use. |
| **OCR cleanup quality** | Improve second-pass cleanup / verification without a separate analysis module. |
| **People & places / Patterns** | Dedicated surfaces only if usage justifies it. |

---

## Next — Release / onboarding / operability — [?] candidates

Small dedicated track so Docker/runtime docs do not stand in for end-user experience:

- Installation and first-run
- First notebook + model setup
- Demo / sample notebook
- Upgrades (paired with data longevity above)
- Diagnostics, doctor, and recovery paths users can follow without digging in contracts

---

## Later candidates — uncommitted — [?]

Worth recording without scheduling:

- Cross-notebook links / related pages
- Corpus-level Analyse / search
- Bookmarks / favourites
- Annotations distinct from OCR corrections
- Batch metadata editing
- Image-only / non-OCR page handling

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

Still the more central product surface than speculative analysis work. Detail and sequencing live in the **corpus / bulk import**, **preprocessing system**, **corpus & product lifecycle**, and **release / onboarding** sections above.

Summary:

- **OCR pipeline** — import, vision OCR, optional second-pass cleanup; eventual re-OCR / reprocessing
- **Preprocessing** — visual declutter (human, on by default at import) vs OCR optimisation (`gentle_contrast` only today, off by default; other OCR profiles deferred) — see **Preprocessing system** above
- **Notebook corpus** — contracts first; bulk import gated; import recovery / inbox as the user-facing continuation
- **Living with notebooks** — organisation metadata, first-class search, reading mode, review UX
- **Longevity** — backup/restore/portability; upgrade/migration story; archive readable without Transcribe where feasible
- **Operability** — model/runtime management UX; release/onboarding/diagnostics; prompt management; local quality/evaluation loop (thumbs + fixtures)
- **Export** — notebook readability and sharing (`transcribe.notebook`)
- **Runtime docs** — Docker / local Ollama — [runtime/docker.md](runtime/docker.md) (supports operability; does not replace it)
- **Future TranscriptX import adapter** — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (not a dependency)

---

## Future metadata

- Page **time-of-day** metadata (from diary stamps like `YYMMDD HHMM` / similar): storage alongside `ApproximateDate`, UI, archive indexing, and analysis policy TBD. Date auto-extraction currently ignores time.
