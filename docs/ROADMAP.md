Type: PRODUCT
Authority: Product roadmap and sequencing. Does not define runtime contracts or shipped schemas. This roadmap describes product priorities and sequencing. Completed implementation detail lives in delivery-history documents and is not duplicated here.

# Transcribe roadmap

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Usability wave (active focus):** [usability_wave_plan.md](usability_wave_plan.md)  
**Analysis porting map:** [analysis_module_porting.md](analysis_module_porting.md)  
**Core delivery history (internal):** [analysis_wave1_plan.md](analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency)  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done · [−] deferred · [?] candidate (uncommitted)

## Current state

Transcribe has the complete 25-module core notebook-analysis set (pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md); slices **1.1 → 1e.2** in [analysis_wave1_plan.md](analysis_wave1_plan.md)). Current work is the **usability wave** ([usability_wave_plan.md](usability_wave_plan.md)): Analyse trust + product UX (**U0–U1**) are **done** (hardening exit gate); remaining focus is first-run operability and daily workbench (**U2–U3**), with corpus bulk import **supported** after the acceptance gate (**U4** mechanics done; Inbox polish may continue). No additional analysis modules are scheduled. Architecture is verbatim-ish analytical cores plus thin notebook adapters over canonical `AnalysisDocument` units; durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)). Historical port implementation gates live in [analysis_wave1_plan.md §9](analysis_wave1_plan.md#9-implementation-gate).

The roadmap’s analysis surface is largely complete. **Remaining product gaps are usability and corpus-lifecycle concerns** (first-run operability, daily Review/reading/search, then living with many notebooks), not more analysis capability. Sequencing for that focus: [usability_wave_plan.md](usability_wave_plan.md) (tracks **U0–U4**).

---

## Now — Usability wave — [~] active

Priority after shipping the core module set. **Do not** schedule deferred-reinterpretation ports while this focus is open. Full track plan: [usability_wave_plan.md](usability_wave_plan.md). Detection Prompt Hub / Detect UI is a **shipped parallel track** ([detection_wave2_plan.md](detection_wave2_plan.md); not this wave’s definition of done — avoid calling Detection the product “Wave 2” in usability docs).

### U0–U1 — Product hardening (embedded) — [x] done

Phased checklist (see [product hardening plan](product_hardening_plan.md)): **#10 → #3/#4 → #1/#2 → #5/#6 → #11/#12 → #13 → #7–9**.

| Phase | Status | Outcome | Wave track |
|-------|--------|---------|------------|
| **1** — #10, #3, #4 | [x] | Analyse has one launcher and one freshness authority | done |
| **2** — #1, #2 | [x] | Runs survive UI/process interruption and execute from frozen inputs | done |
| **3** — #5, #6 | [x] | Users can trust exactly what a preset will run | **U0** (done) |
| **4** — #11, #12 | [x] | Every analysis surface gives the same answer to “is this current and healthy?” | **U0** (done) |
| **5** — #13 | [x] | Exports identify exactly which notebook revision produced them | **U0** (done) |
| **6** — #7, #8, #9 | [x] | Analyse surfaces are simplified around user tasks rather than module mechanics | **U1** (done) |

| Track | Intent |
|-------|--------|
| **Robustness** | Honest capability / cache / parent freshness; crash-reopen and stale-evidence behaviour; offline test coverage for shipped modules; clearer failure and empty-success paths |
| **Analyse UX** | One batch run action, one freshness model, Ask remains ad-hoc; deepen Overview / Themes / Mood / Moments / Summaries as **product** read-models (not module consoles) |
| **Payload polish** | People & places map tab shipped (NER read-model + opt-in geocode). Patterns tab and deliberate keyphrase enrichment for wordclouds/topics remain optional polish — not a back door for deferred reinterpretations |
| **OCR text quality** | Prefer existing **second-pass LLM OCR cleanup / verification** (and review edits) over a separate `ocr_quality` analysis module |

Infra checklist already landed for the core set: [analysis_wave1_hardening_plan.md](analysis_wave1_hardening_plan.md). Further work stays deepen-in-place on shipped surfaces and contracts.

**Hardening exit gate (U0+U1):** Crash/reopen behaviour, stale detection, offline operation, export provenance, and normal Analyse workflows are covered by acceptance tests, and no ordinary user workflow requires understanding module/cache internals. Named suite: [tests/acceptance/hardening/](../tests/acceptance/hardening/).

### U2–U3 — Operability & daily workbench

Committed usability-wave outcomes (detail and acceptance in [usability_wave_plan.md](usability_wave_plan.md)):

| Track | Intent |
|-------|--------|
| **U2 First-run & operability** | Setup checklist, sample notebook, model guidance, doctor/diagnostics in UI, first-run docs path |
| **U3 Daily workbench** | Review as needs-attention queue, reading mode, search/Archive filter parity, organisation polish, model/runtime product copy — **without** requiring bulk corpus activation |

### U4 — Corpus UX — [x] gate green (Inbox polish may continue)

Bulk inbox / import recovery is **supported**. The [corpus-integrity acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is green. See usability-wave **U4** and **Next — Notebook corpus**. Remaining Inbox polish (e.g. richer needs-review taxonomy / `TRANSCRIBE_INBOX_DIR` scan) may continue without reopening the gate.

---

## Next — Notebook corpus / bulk import — [x] done (shipped slice)

**Bulk-import generation** is **runtime-normative**: corpus index, ImportPlan/ImportRun, duplicate policy, orchestrator, doctor, CLI, and Inbox UI. Runtime stays compatible with `transcribe.project` v1 notebooks that lack corpus registration. Acceptance suite: [tests/acceptance/corpus/](../tests/acceptance/corpus/).

| Gate | Authority |
|------|-----------|
| Corpus identity, index, locks | [contracts/notebook-corpus.md](contracts/notebook-corpus.md) |
| Managed originals / duplicates | [contracts/source-asset.md](contracts/source-asset.md) |
| ImportRun / plan / resume | [contracts/import-run.md](contracts/import-run.md) |
| Doctor + executable acceptance suite | [contracts/corpus-integrity.md](contracts/corpus-integrity.md) |

**Shipped:** corpus index registration + discovery, ImportPlan/ImportRun orchestrator with crash hooks, `skip_existing_v1` / `create_duplicate_v1`, folder adapters, CLI `bulk-import` / `corpus-doctor`, **Notebooks → Inbox**, corpus doctor ImportRun ID checks, and the synthetic multi-notebook acceptance suite (crash-injection, idempotency, duplicate policy, index rebuild, deep doctor, fixture coverage).

**Related product outcome:** import recovery / inbox as a daily workflow. Usability-wave **U4** gate mechanics are done; richer outcome taxonomy / inbox-dir scan remain optional polish. Remaining lifecycle candidates (re-OCR compare/promote, backup/restore productization) stay in the corpus & product lifecycle section below.

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

## Next — OCR lifecycle package — [~] active

Ambitious OCR features on the durable attempt model: multipass multi-model runs, compare/prefer/promote, composite candidates, preference stats, fine-tune export. Contracts: [ocr-multipass](contracts/ocr-multipass.md), [ocr-preference](contracts/ocr-preference.md), [finetune-export](contracts/finetune-export.md), extended [page-result](contracts/page-result.md). Outline for external training: [finetune_export.md](finetune_export.md).

| Wave | Status | Outcome |
|------|--------|---------|
| **W0** | [x] | Prefer/promote APIs, `activate` flag, prefer modes, settings |
| **W1** | [x] | MultiPass orchestrator + CLI |
| **W2** | [x] | Rank + composite (text model) |
| **W3** | [x] | Compare/Prefer Review GUI + single-page re-run |
| **W4** | [x] | Preference ledger + pre-run hints |
| **W5** | [x] | Fine-tune export + docs |

---

## Next — Corpus & product lifecycle — [?] candidates (partially pulled)

Primary post-hardening direction for living with many notebooks. **Usability-wave U3** pulls Review UX, reading mode, search deepening, organisation polish, and model/runtime management as committed work on today’s project model (no bulk corpus activation required). **U4** covers import recovery / inbox (gate green; Inbox polish may continue). Remaining rows stay uncommitted candidates.

| Outcome | Intent | Wave |
|---------|--------|------|
| **Search (first-class)** | Full-text across notebooks; date / tag / entity filters; jump-to-page; eventually saved searches. With dozens of notebooks this may matter more than Analyse. | **U3** date/tag/jump polish; entity/saved searches still candidate |
| **Notebook organisation** | Titles, descriptions, tags/collections, archive state, sort order, cover/thumbnail, lightweight notebook metadata — how users live with a multi-notebook corpus. | **U3** polish on existing fields; collections/archive-state candidate |
| **Re-OCR / reprocessing** | **Moved to OCR lifecycle package above** (multipass, compare, prefer/promote, composite, fine-tune export). | **OCR lifecycle** (active) |
| **Import recovery / inbox** | Continuations of bulk import as a daily workflow (see above), not only the ImportRun machine. | **U4** (gate green; polish open) |
| **Reading mode** | Clean chronological in-app reading: page image/text pairing, dates, navigation, optional distraction-free layout — distinct from Review, Analyse, and export. | **U3** |
| **Backup / restore / portability** | Product commitment that the whole corpus can be backed up, moved, restored, and verified without application-specific archaeology. | candidate |
| **Data longevity / upgrades** | Notebooks survive Transcribe upgrades: migration UX, pre-upgrade backup, refusal/recovery, and “archive remains readable without Transcribe” where feasible — broader than schema contracts alone. | candidate |
| **Model & runtime management** | Comprehensible UX over installed OCR/text models: availability, size, last-used, refresh, health, recommendations. Ollama machinery exists; users need a product abstraction. | **U3** |
| **Quality / evaluation loop** | Alongside thumbs: sampled OCR accuracy review, cleanup accept/reject, analysis usefulness ratings, local regression fixtures — local evidence that changes improve Transcribe, not analytics telemetry. | candidate |
| **Prompt management UI** | **Shipped (Detection wave 2):** Settings → Prompts hub for OCR, cleanup, and detection prompts (browse / override / custom / dry-run). Analysis inline prompts remain module-local. | **shipped** (parallel) |
| **Prompt-backed Detection** | **Shipped (Detection wave 2 +):** Built-ins `poetry`, `todo_lists`, `lists`, `quotations`, `beer_labels` + declarative custom detectors; Analyse → Detect; findings under `detection/`. See [detection_wave2_plan.md](detection_wave2_plan.md) + detection contracts. | **shipped** (parallel) |
| **Quality ratings (thumbs)** | Collect-only local ratings for transcription and analysis outputs; shape/code from TranscriptX LLM feedback v1 — not a substitute for deferred `ocr_quality` analysis. | candidate |
| **Review UX** | Faster correction and approval of OCR text and dates. | **U3** |
| **Export / readability** | **Shipped** — EPUB/PDF/HTML, typography options, export profiles, multi-notebook anthology (provenance via U0 #13). Further reading-mode polish remains a separate candidate above. | **shipped** |
| **Analyse information architecture** | Validate Overview / Themes / Mood / Moments / Summaries / Ask against real use. | **U1** (done) |
| **OCR cleanup quality** | Improve second-pass cleanup / verification without a separate analysis module. | candidate |
| **People & places / Patterns** | People & places map surfaces shipped; Patterns tab only if usage justifies it. | Places shipped; Patterns optional |

---

## Next — Release / onboarding / operability — [~] pulled into usability wave U2

Committed under [usability_wave_plan.md](usability_wave_plan.md) **U2** (no longer uncommitted candidates):

- Installation and first-run checklist
- First notebook + model setup guidance
- Demo / sample notebook
- Diagnostics, doctor, and recovery paths users can follow without digging in contracts

Upgrades / data longevity remain paired with the lifecycle candidates below.

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
| **Page ink / blankness** | Pillow coverage %, blankness %, dominant ink hue (Review + Analyse Overview; not a text Analyse module) |
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

- OCR pipeline — import, vision OCR, optional second-pass cleanup; **multipass compare / prefer / promote / composite / fine-tune export** (OCR lifecycle package)
- **Preprocessing** — visual declutter (human, on by default at import) vs OCR optimisation (`gentle_contrast` only today, off by default; other OCR profiles deferred) — see **Preprocessing system** above
- **Notebook corpus** — contracts runtime-normative; bulk import supported; import recovery / inbox as the user-facing continuation
- **Living with notebooks** — organisation metadata, first-class search, reading mode, review UX
- **Longevity** — backup/restore/portability; upgrade/migration story; archive readable without Transcribe where feasible
- **Operability** — model/runtime management UX; release/onboarding/diagnostics; prompt management; local quality/evaluation loop (thumbs + fixtures)
- **Export** — notebook readability and sharing (`transcribe.notebook`)
- **Runtime docs** — Docker / local Ollama — [runtime/docker.md](runtime/docker.md) (supports operability; does not replace it)
- **Future TranscriptX import adapter** — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (not a dependency)

---

## Future metadata

- Page **time-of-day** metadata (from diary stamps like `YYMMDD HHMM` / similar): storage alongside `ApproximateDate`, UI, archive indexing, and analysis policy TBD. Date auto-extraction currently ignores time.
