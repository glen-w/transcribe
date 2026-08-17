Type: PRODUCT
Authority: Product roadmap and sequencing. Does not define runtime contracts or shipped schemas. This roadmap describes product priorities and sequencing. Completed implementation detail lives in delivery-history documents and is not duplicated here.

# Transcribe roadmap

**Product definition:** [PRODUCT.md](PRODUCT.md)  
**Usability wave (active product focus):** [usability_wave_plan.md](usability_wave_plan.md)  
**0.9 infrastructure wave (in progress):** [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md)  
**Path to 0.9 / 1.0:** [Path to 0.9.0 / 0.9-1 / 1.0](#path-to-090--09-1--10)  
**0.9-1 unfamiliar testing (planned):** [dev/user_testing_0_9.md](dev/user_testing_0_9.md)  
**After 1.0 (planned):** notebook-anchored autobiography workbench (1.1–2.0) — gated on 1.0; see [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned)  
**Analysis porting map:** [dev/analysis_module_porting.md](dev/analysis_module_porting.md)  
**Core delivery history (internal):** [archive/plans/analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md)  
**Future TranscriptX handoff:** [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (post–TX 1.0; not a dependency). Reverse file-import of TX exports is Transcribe **1.6**, not this seam.  
**Indexes:** [USER_INDEX.md](USER_INDEX.md) · [DEV_INDEX.md](DEV_INDEX.md) · [CONTRACT_INDEX.md](CONTRACT_INDEX.md)

> **Status legend:** [ ] planned · [~] in progress · [x] done · [−] deferred · [?] candidate (uncommitted)

## Current state

Transcribe has the complete 25-module core notebook-analysis set (pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md); slices **1.1 → 1e.2** in [analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md)). The **OCR lifecycle package** (multipass compare, prefer/promote, composite, fine-tune export) is **shipped**. Current work is the **usability wave** ([usability_wave_plan.md](usability_wave_plan.md)): Analyse trust + product UX (**U0–U1**) and daily workbench (**U3**) are **done**; remaining focus is first-run operability (**U2**), with corpus bulk import **supported** after the acceptance gate (**U4** mechanics done; Inbox polish may continue). No additional analysis modules are scheduled. Architecture is verbatim-ish analytical cores plus thin notebook adapters over canonical `AnalysisDocument` units; durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)). Historical port implementation gates live in [analysis_wave1_plan.md §9](archive/plans/analysis_wave1_plan.md#9-implementation-gate).

The roadmap’s analysis surface is largely complete. **Remaining product gaps are first-run operability (U2) and optional corpus-lifecycle polish**, not more analysis capability. Sequencing for that focus: [usability_wave_plan.md](usability_wave_plan.md) (tracks **U0–U4**).

**Package is 0.7.0.** Version ladder to autobiography:

```text
0.6.x  →  0.7.0 (now)  →  0.8 (I2–I3)  →  0.9.0 cut  →  0.9-1 unfamiliar testing  →  1.0  →  After 1.0 (1.1–2.0)
              I0–I1                         U2 + I4–I6     tag + hosted docs      findings → fixes         freeze     autobiography
```

| Label | Meaning |
|-------|---------|
| **0.7.0** | Developer lanes + PR CI honesty gate (**I0–I1**). Makefile, `tests/README.md`, GitHub Actions matrix 3.10–3.12, compose-bind assert. |
| **0.8** | Next infra cut: release hygiene + quality gates (**I2–I3**). |
| **0.9.0** | Package/tag when **U2** + **0.9 infrastructure wave (I0–I6)** exit gates are green. Notebook product is first-run capable and maintainer-operable. |
| **0.9-1** | **Unfamiliar-user testing** programme on 0.9.0 (or a 0.9.x patch train). Not a second infrastructure wave. Produces findings, fix PRs, and a go/no-go for **1.0**. Protocol: [dev/user_testing_0_9.md](dev/user_testing_0_9.md). |
| **1.0** | Notebook workbench declared complete for its promise; architecture freeze for additive After 1.0 extension. |
| **After 1.0** | Autobiography programme (1.1–2.0) — [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned). |

A parallel **0.9 infrastructure wave** ([infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md)) brings maintainer CI, release hygiene, and hosted docs to TranscriptX-class maturity. It does not schedule more analysis modules and does not serialize **U2**. Full path: [Path to 0.9.0 / 0.9-1 / 1.0](#path-to-090--09-1--10).

**After 1.0** is planned, not started. Do not schedule context importers, Slices, People-as-identity, reconstruction, or page time-of-day while U2 / I0–I6 / 0.9-1 remain the path to 1.0.

---

## Now — Usability wave — [~] active

Priority after shipping the core module set. **Do not** schedule deferred-reinterpretation ports while this focus is open. Full track plan: [usability_wave_plan.md](usability_wave_plan.md). Detection Prompt Hub / Detect UI is a **shipped parallel track** ([detection_wave2_plan.md](archive/plans/detection_wave2_plan.md); not this wave’s definition of done — avoid calling Detection the product “Wave 2” in usability docs).

### U0–U1 — Product hardening (embedded) — [x] done

Phased checklist (see [product hardening plan](archive/plans/product_hardening_plan.md)): **#10 → #3/#4 → #1/#2 → #5/#6 → #11/#12 → #13 → #7–9**.

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
| **Robustness** | Honest capability / cache / parent freshness; crash-reopen and stale-evidence behaviour; offline test coverage for shipped modules; clearer failure and empty-success paths. **Also landed (OCR deepen-in-place):** consecutive vision **timeout** circuit (skip remaining pages for that model after 3) and fatal **model-load** circuit (skip after the first unrecoverable Ollama loader error, e.g. unsupported architecture) — see [known_limitations.md](known_limitations.md) |
| **Analyse UX** | One batch run action, one freshness model, Ask remains ad-hoc; deepen Overview / Themes / Mood / Moments / Summaries as **product** read-models (not module consoles). **Also landed:** Overview/Mood **corpus / period average** charts ([dev/analysis_visual_compare.md](dev/analysis_visual_compare.md)); Moments / page-series **Jump to page** into Reading; Analyse launcher vs View consume split ([public_surfaces.md](public_surfaces.md)) |
| **Payload polish** | People & places map tab shipped (NER read-model + opt-in geocode). Patterns tab and deliberate keyphrase enrichment for wordclouds/topics remain optional polish — not a back door for deferred reinterpretations |
| **OCR text quality** | Prefer existing **second-pass LLM OCR cleanup / verification** (and review edits) over a separate `ocr_quality` analysis module |

Infra checklist already landed for the core set: [analysis_wave1_hardening_plan.md](archive/plans/analysis_wave1_hardening_plan.md). Further work stays deepen-in-place on shipped surfaces and contracts.

**Hardening exit gate (U0+U1):** Crash/reopen behaviour, stale detection, offline operation, export provenance, and normal Analyse workflows are covered by acceptance tests, and no ordinary user workflow requires understanding module/cache internals. Named suite: [tests/acceptance/hardening/](../tests/acceptance/hardening/).

### U2 — First-run & operability — [ ] planned (not started)

| Track | Status | Intent |
|-------|--------|--------|
| **U2 First-run & operability** | [ ] | Setup checklist, sample notebook, model guidance, doctor/diagnostics in UI, first-run docs path |

### U3 — Daily workbench — [x] done

| Track | Status | Intent |
|-------|--------|--------|
| **U3 Daily workbench** | [x] | Review as needs-attention queue, Reading mode, Search/Archive filter parity, organisation polish, model/runtime product copy — **without** requiring bulk corpus activation |

**Also landed with U3:** Archive activity-bin click filter; Archive notebook-strip paging (`ui.archive_notebooks_initial`, default show-all); page delete in the viewer; model-information expander wired to live picker selection on Transcribe panels.

**Post-U3 deepen-in-place (shipped, not a new wave track):** OCR hang / model-load fail-fast circuits; Compare OCR attempt previews escape markdown so Prefer/Promote stays readable; Analyse Moments jump-to-page; Overview/Mood this-vs-corpus/period charts (PR #25).

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

**Shipped:** corpus index registration + discovery, ImportPlan/ImportRun orchestrator with crash hooks, `skip_existing_v1` / `create_duplicate_v1`, folder adapters, CLI `bulk-import` / `bulk-run` / `corpus-doctor`, **Workflow → Import → Batch** (legacy Inbox alias), **Workflow → Transcribe → Batch** (unified Import/Transcribe target switcher + batch OCR), live progress for import / batch OCR / transcribe jobs, corpus doctor ImportRun ID checks, and the synthetic multi-notebook acceptance suite (crash-injection, idempotency, duplicate policy, index rebuild, deep doctor, fixture coverage).

**Related product outcome:** import recovery / inbox as a daily workflow. Usability-wave **U4** gate mechanics are done; richer outcome taxonomy / inbox-dir scan remain optional polish. Remaining lifecycle candidates (quality thumbs; data longevity / upgrades beyond shipped backup) stay in the corpus & product lifecycle section below.

---

## Next — Preprocessing system — [?] candidate / partial

Two separate lanes. Do not conflate human-facing scan cleanup with OCR input transforms.

| Lane | Audience | Default | Intent |
|------|----------|---------|--------|
| **1. Visual declutter** | Human (reading / review of scans) | **On** for imports; global off-switch in settings | Clean up scanned page images for people. **Shipped:** `remove_scan_borders` + `remove_uniform_overscan` + `remove_corner_wedges` (Pillow, deterministic; grey/light-grey scanner beds, stark-white gutters, residual rounded-corner bed wedges). Applies at **import** and via explicit **Re-apply visual declutter** (Settings → Configuration). Changing the setting alone does not rewrite notebooks. Render provenance records state, geometry, and declutter identity. |
| **2. OCR optimisation** | Vision model input | **Off** (`none`); opt-in | Transforms meant to help OCR. Shipped today: optional Pillow **`gentle_contrast`**. Further OCR preprocess profiles are **deferred**. |

**Rules of thumb**

- Visual declutter defaults help the common “dump of scans” path; power users can disable it workspace-wide (`ingest.visual_declutter_enabled`).
- OCR preprocess stays conservative and off-by-default so fingerprints / skip-resume stay predictable; expanding profiles is a deliberate product choice, not creep from declutter work.
- Declutter identity (`enabled` + `DECLUTTER_VERSION` + ordered ops + frozen detection params) is frozen into ingest journal / render provenance; crash recovery never pairs mismatched pixels and metadata. OCR invalidation follows the final active render SHA.
- Explicit declutter re-apply is shipped; OCR-optimisation reprocess remains opt-in / future. Defaults above are unchanged.

**Later — visual declutter expansion (Pillow-only, uncommitted)**

Stay outside the page: high-confidence, edge-anchored artefacts only — never alter pixels inside the detected page area. That keeps declutter distinct from document restoration (no bleed-through, whitening, stains, ruled lines, hole punching, creases, page-wide shadow fix, or handwritten-margin cleanup).

Suggested sequence after scanner-bed borders + stark-white overscan + corner wedges: **binding gutter** → **edge shadows**. Other safe candidates when detection is conservative: scanner lid/background slivers (non-white/non-grey uniform edge bands), punch-hole *margins* (trim blank outer strip only), scanner calibration stripes, and combined page-edge-shadow + exposed-bed as one page-boundary problem rather than stacked aggressive ops.

---

## Next — OCR lifecycle package — [x] done (shipped)

Ambitious OCR features on the durable attempt model: multipass multi-model runs, compare/prefer/promote, composite candidates, preference stats, fine-tune export. Contracts: [ocr-multipass](contracts/ocr-multipass.md), [ocr-preference](contracts/ocr-preference.md), [finetune-export](contracts/finetune-export.md), extended [page-result](contracts/page-result.md). Outline for external training: [finetune_export.md](finetune_export.md). Shipped via [PR #15](https://github.com/glen-w/transcribe/pull/15).

| Wave | Status | Outcome |
|------|--------|---------|
| **W0** | [x] | Prefer/promote APIs, `activate` flag, prefer modes, settings |
| **W1** | [x] | MultiPass orchestrator + CLI |
| **W2** | [x] | Rank + composite (text model) |
| **W3** | [x] | Compare/Prefer Review GUI + single-page re-run |
| **W4** | [x] | Preference ledger + pre-run hints |
| **W5** | [x] | Fine-tune export + docs |
| **Batch multipass** | [x] | Compare models over OcrBatchRun (UI + `bulk-run` multi `--model`) |
| **OCR fail-fast circuits** | [x] | Timeout circuit (3) + fatal model-load circuit (1) per frozen vision plan; multipass continues with remaining models |

---

## Next — Corpus & product lifecycle — [?] candidates (partially pulled)

Primary post-hardening direction for living with many notebooks. **Usability-wave U3** pulls Review UX, reading mode, search deepening, organisation polish, and model/runtime management as committed work on today’s project model (no bulk corpus activation required). **U4** covers import recovery / inbox (gate green; Inbox polish may continue). Remaining rows stay uncommitted candidates.

| Outcome | Intent | Wave |
|---------|--------|------|
| **Search (first-class)** | Full-text across notebooks; date / tag / entity filters; jump-to-page; eventually saved searches. With dozens of notebooks this may matter more than Analyse. | **U3** date/tag/jump done; Moments/chart jump → Reading done; entity filters → After 1.0 **1.1/1.3**; saved searches still candidate |
| **Notebook organisation** | Titles, descriptions, tags/collections, archive state, sort order, cover/thumbnail, lightweight notebook metadata — how users live with a multi-notebook corpus. Archive strip paging (`ui.archive_notebooks_initial`) + activity-bin filter + page delete landed. Workspace tag catalogue (labels, colours, rename/merge) + viewer click-to-filter + detection auto-tag: [tag-catalog.md](contracts/tag-catalog.md). | **U3** tag chips + sort polish done; catalogue/filter/auto-tag shipped as deepen-in-place; collections/archive-state candidate |
| **Re-OCR / reprocessing** | **Moved to OCR lifecycle package above** (multipass, compare, prefer/promote, composite, fine-tune export). | **OCR lifecycle** (done) |
| **Import recovery / inbox** | Continuations of bulk import as a daily workflow (see above), not only the ImportRun machine. | **U4** (gate green; polish open) |
| **Reading mode** | Clean chronological in-app reading: page image/text pairing, dates, navigation, optional distraction-free layout — distinct from Review, Analyse, and export. | **U3** (done) |
| **Backup / restore / portability** | Full-workspace ZIP (`transcribe.workspace-backup` v1): create/verify/restore via CLI + Settings → Configuration → Backup; replace-only restore with automatic safety ZIP; corpus-doctor after restore. Contract: [workspace-backup.md](contracts/workspace-backup.md). | **[x] done** |
| **Data longevity / upgrades** | Notebooks survive Transcribe upgrades: migration UX, pre-upgrade backup, refusal/recovery, and “archive remains readable without Transcribe” where feasible — broader than schema contracts alone. | **0.9 path (thin):** pre-upgrade backup + restore verify in first-run/backup docs — [Path to 0.9.0](#path-to-090--09-1--10) foundation checklist. Full “archive readable without Transcribe” remains candidate |
| **Model & runtime management** | Comprehensible UX over installed OCR/text models: availability, size, last-used, refresh, health, recommendations. Ollama machinery exists; users need a product abstraction. Model-information expander follows live Transcribe picker selection. | **U3** (done) |
| **Quality / evaluation loop** | Alongside thumbs: sampled OCR accuracy review, cleanup accept/reject, analysis usefulness ratings, local regression fixtures — local evidence that changes improve Transcribe, not analytics telemetry. | candidate |
| **Prompt management UI** | **Shipped (Detection wave 2):** Settings → Prompts hub for OCR, cleanup, and detection prompts (browse / override / custom / dry-run). Analysis inline prompts remain module-local. | **shipped** (parallel) |
| **Prompt-backed Detection** | **Shipped (Detection wave 2 +):** Built-ins `poetry`, `todo_lists`, `lists`, `quotations`, `beer_labels` + declarative custom detectors; View → Detect; findings under `detection/`. See [detection_wave2_plan.md](archive/plans/detection_wave2_plan.md) + detection contracts. | **shipped** (parallel) |
| **Quality ratings (thumbs)** | Collect-only local ratings for transcription and analysis outputs; shape/code from TranscriptX LLM feedback v1 — not a substitute for deferred `ocr_quality` analysis. | candidate |
| **Review UX** | Faster correction and approval of OCR text and dates. | **U3** (done) |
| **Export / readability** | **Shipped** — EPUB/PDF/HTML, typography options, export profiles, multi-notebook anthology (provenance via U0 #13). Further reading-mode polish remains a separate candidate above. | **shipped** |
| **Analyse information architecture** | Validate Overview / Themes / Mood / Summaries / Ask against real use. People/Moments/Ask are in-page sections (not extra sidebar items). Corpus/period compare + Moments/chart jump → Reading, and Analyse launcher vs View consume split, landed as deepen-in-place. | **U1** (done) + GUI alignment |
| **OCR cleanup quality** | Improve second-pass cleanup / verification without a separate analysis module. | candidate |
| **People & places / Patterns** | People & places map surfaces shipped; Patterns tab only if usage justifies it. First-class Person identity is **After 1.0 / 1.3**, not this lifecycle row. | Places shipped; Patterns optional |

---

## Next — Release / onboarding / operability — [ ] planned (via U2)

Committed under [usability_wave_plan.md](usability_wave_plan.md) **U2** — **required for the 0.9.0 cut** ([Path to 0.9.0](#path-to-090--09-1--10)):

- **Shipped (GUI alignment):** Home (Create / Import + one-line Ollama health; no sample wizard) and System → Diagnostics (workspace doctor always; notebook doctor when selected)
- Remaining: first-run install docs path (U2.4), sample notebook (U2.2)

Longevity **minimum for testers** (pre-upgrade backup + restore verify copy) is on the 0.9 path foundation checklist below. Full “archive readable without Transcribe” stays a lifecycle candidate.

---

## Path to 0.9.0 / 0.9-1 / 1.0

**Status:** [~] in progress — authoritative sequencing from package **0.7.0** toward a frozen **1.0** notebook workbench ready for After 1.0. Does not schedule autobiography features. Companion tracks: [usability_wave_plan.md](usability_wave_plan.md) (U2), [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md) (I0–I6), [dev/user_testing_0_9.md](dev/user_testing_0_9.md) (0.9-1).

**Thesis:** Cut an operable **0.9.0**, run **0.9-1** unfamiliar-user testing, then declare **1.0** with an additive-ready foundation. Harden and freeze the existing notebook/OCR/analysis/corpus stack. Do **not** ship After 1.0 features (photos-as-context, WhatsApp, People store, Slices, reconstruction, time-of-day storage) before **1.0**.

```text
U2 (sample + first-run docs)  ─┐
                               ├─► 0.9.0 cut ─► 0.9-1 testing ─► 1.0 freeze ─► After 1.0
I0–I6 (infra wave)           ─┘
```

### Track A — U2 (product; required for 0.9.0)

| Item | Status | Work |
|------|--------|------|
| U2.1 Home | [x] | Create / Import + Ollama health |
| U2.3 Diagnostics | [x] | Workspace / notebook doctor in UI |
| **U2.2 Sample notebook** | [ ] | Fixture under `samples/`; one-click Open sample via existing init/import; offline Analyse Quick without LLM |
| **U2.4 First-run docs** | [ ] | “First notebook in 15 minutes” from README; port **8510**, mounts, Ollama, known first-run bites |

**U2 exit:** sample path smoke; README / user_guide first-run without reading contracts. Detail: [usability_wave_plan.md](usability_wave_plan.md) §6.

### Track B — I0–I6 (infra; required for 0.9.0)

Full track plan: [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md). Does **not** schedule autobiography or write U2 content (may host docs).

| Track | Status | Intent |
|-------|--------|--------|
| **I0** Developer lanes & inventory | [x] | `Makefile` + `tests/README.md` lane vocabulary; marker policy; light docs/script inventory |
| **I1** PR CI honesty gate | [x] | Lint + offline smoke/default suite on Python 3.10–3.12; compose-bind assert |
| **I2** Release hygiene + governance | [ ] | `scripts/release/*`, secrets/denylist, `release_governance.md`, dependency audit log |
| **I3** Quality gates | [ ] | Coverage fail-under, pre-commit, partial CI `release-checks` |
| **I4** Hosted docs | [ ] | Sphinx over existing Markdown, `.[docs]`, `.readthedocs.yml` scaffold, CI docs job |
| **I5** Public landing | [ ] | Modest `website/` + GitHub Pages assemble; optional workflow screenshot walkthroughs |
| **I6** Sustaining lanes | [ ] | Nightly acceptance/offline heavy, Docker smoke in release-checks, issue templates |

Suggested cut order: **I0+I1** (0.7.0, landed) → **I2** → **I3** → **I4+I5** → **I6**. U2 may parallel throughout; both tracks required for the **0.9.0** package cut.

**Infra exit gate (summary):** green PR CI on the Python matrix; Makefile/CI/`# pre-release` share lane names; tag authority is `docs/dev/release_governance.md` with script-backed evidence; Sphinx builds in CI and Pages (or documented RTD go-live) can publish the guide; coverage + secrets gates enforced; nightly (or equivalent) runs heavier offline suites without live Ollama.

**Already landed (do not rebuild in I0–I6):** offline default pytest suite, acceptance gates, Markdown docs authority/indexes/archive, Docker Compose loopback bind docs, root `SECURITY.md` / `CONTRIBUTING.md` / `CHANGELOG.md`, agent SOPs that already *expect* the missing scripts.

### Track C — Foundation readiness for After 1.0 (docs + freeze rules)

No runtime context schema and no `data/context/` tree before **1.0**. Before autobiography implementation starts, all of the following must be true:

| # | Checklist item | Intent |
|-----|----------------|--------|
| 1 | **Notebook core freeze** | `transcribe.project` v1, `page-result` v1, `AnalysisDocument` v1 remain loadable; After 1.0 is **additive-only**; do not generalize `SourceDocument` |
| 2 | **Human metadata vocabulary** | ClaimStatus documented as a map onto existing `date_approved` / detection `review_status` / `edited_text` ([TERMS.md](TERMS.md) · After 1.0 ClaimStatus table). Runtime ClaimStatus schema waits for After 1.0 contracts |
| 3 | **Rebuildability proven** | Archive FTS delete-and-rebuild; backup excludes `data/cache/`; corpus + hardening acceptance suites green on CI (I1/I6) |
| 4 | **Extensibility noted** | Future lock order **corpus → context → notebook**; context trees must be optional (absence = valid 1.0 workspace). See [ARCHITECTURE.md](ARCHITECTURE.md) |
| 5 | **Longevity minimum for testers** | Pre-upgrade backup + restore verify documented in first-run / [backup_and_restore.md](backup_and_restore.md); refuse/recover copy for schema bumps. Full “archive readable without Transcribe” stays candidate |
| 6 | **Known-limitations honesty** | First-run bites, remote Ollama, unapproved dates on timeline, Analyse optional extras — visible to unfamiliar testers |
| 7 | **Explicit non-goals until After 1.0** | No WhatsApp/Telegram/photo-context corpus; no Person store; no Slices; no ReconstructionBundle; no page time-of-day field; no `AnalysisDocument` v1 bump |

Optional U4 Inbox polish may continue but is **not** on the 0.9.0 critical path.

### 0.9.0 cut

When **U2 acceptance** and the **I0–I6 exit gate** are both true: bump `pyproject.toml` / `__version__` / CHANGELOG to **0.9.0**. Intermediate cuts: **0.7.0** = I0+I1 (landed); **0.8** = I2+I3 (next).

### 0.9-1 — Unfamiliar user testing

**Purpose:** Strangers (or deliberately unfamiliar testers) complete install → sample or own scans → OCR → review → Analyse Quick → export → backup using only hosted/README docs — not contracts.

**Inputs:** 0.9.0 build + hosted guide (I4/I5) + sample notebook (U2.2).

**Protocol:** [dev/user_testing_0_9.md](dev/user_testing_0_9.md) — scripted happy path (15–30 min) + free exploration; capture install blockers, model confusion, Review/date honesty, Analyse empty states, backup/restore confidence, and navigation that would block later “life around a page” UX. **No autobiography features in the script.**

**Outputs:** issue list; fix train on 0.9.x; go/no-go note for **1.0**.

**Exit (0.9-1 → 1.0):** critical install/OCR/review/export/backup issues closed or documented as [known_limitations.md](known_limitations.md); foundation checklist signed off; PRODUCT still page-first.

### 1.0 freeze

**1.0** declares the notebook/OCR/analysis workbench complete for its [PRODUCT.md](PRODUCT.md) promise. Architecture freeze for additive After 1.0 extension. Autobiography may then start with ClaimStatus / TemporalClaim / context-index **contracts** (After 1.0 implementation order step 2) — not with importers.

---

## Next — 0.9 Infrastructure wave — [ ] planned (parallel with U2)

Detail lives in [Path to 0.9.0](#path-to-090--09-1--10) Track B and [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md). Wave exit + U2 enable the **0.9.0** cut; unfamiliar testing is **0.9-1**, not an I7 track.

---

## Next — Bulk run analysis (GUI) — [x] done

Multi-notebook **Analyse → Batch**: same Target / selection modes as Transcribe Batch (`pending` | `import_run` | `pick`), one frozen Analyse plan applied sequentially per notebook. Orchestration only — not cross-notebook synthesis.

Delivery plan: [bulk_run_analysis_plan.md](archive/plans/bulk_run_analysis_plan.md). Contract: [contracts/analysis-batch-run.md](contracts/analysis-batch-run.md). Distinct from ROADMAP “Corpus-level Analyse” below.
| Slice | Status | Outcome |
|-------|--------|---------|
| **A0** Plan + pointers | [x] | Delivery plan (selection, dual-bar progress, test matrix, docs checklist) |
| **A1** Persistence + coordinator | [x] | `AnalysisBatchRun` + sequential coordinator + offline unit/selection/progress-mapper tests |
| **A2** GUI Target + live progress | [x] | Analyse This notebook \| Batch; same three sources; dual progress bars + stop + post-run summary |
| **A3** Handoffs + CLI + docs | [x] | CLI `bulk-analyse`; public surfaces / user guide / limitations |
---

## After 1.0 — Notebook-anchored autobiography workbench — [ ] planned

**Status:** planned; **gated on 1.0**. Authority for post-1.0 product sequencing and architecture intent. Does not define shipped schemas — contracts land with each release. Do not implement this programme while [Path to 0.9.0 / 0.9-1 / 1.0](#path-to-090--09-1--10) remains open (U2, I0–I6, unfamiliar testing).

**Thesis:** Handwritten notebooks are the primary source material. Everything else becomes evidence, context, and memory around them. The system helps reconstruct a life from surviving evidence while preserving a clear distinction between what was actually recorded, what was extracted, and what the machine infers.

This is **not** a generic note-taking app, PKM system, or AI journal. The core object remains the scanned handwritten notebook page. The ambition is a **local-first augmented autobiography workbench** around that primary source.

```text
Primary sources (notebooks / pages)
        ↓
contextual sources (photos, chats, audio, mood, text)
        ↓
extracted knowledge (dates, NER, EXIF, people/places)
        ↓
relationships / Slices
        ↓
autobiographical interpretation (cited, never a substitute for the page)
```

**1.0 stays notebook-first.** Finish the [Path to 0.9.0 / 0.9-1 / 1.0](#path-to-090--09-1--10) (U2, I0–I6, unfamiliar testing, foundation checklist). No WhatsApp, photo libraries, Slices, reconstruction, or time-of-day storage in 1.0.

### What to preserve

The current architecture is the right core. Post-1.0 **extends** it; it does not replace it.

- File-shaped system of record: `project.json`, managed `sources/`, renders, `results/<page_id>.json`. SQLite (`archive.sqlite`) stays a **disposable FTS cache** ([ARCHITECTURE.md](ARCHITECTURE.md), `ArchiveService`).
- UUID identities; never reconstruct IDs from paths ([notebook-corpus.md](contracts/notebook-corpus.md)).
- Import copies bytes; external path is provenance only ([source-asset.md](contracts/source-asset.md)).
- OCR attempts append-only; `edited_text` is user-owned ([page-result.md](contracts/page-result.md)).
- `ApproximateDate` plus `date_source` `extracted|inherited` vs `date_approved` ([domain dates](../src/transcribe/domain/dates.py)); human metadata protection in [notebook-corpus.md](contracts/notebook-corpus.md).
- Analysis evidence `{unit_id, quote, source_ref, content_fingerprint}` and stale-citation rules ([analysis-result.md](contracts/analysis-result.md)).
- Frozen `AnalysisDocument` v1 `source_ref` kinds `{page, page_span}` only ([analysis-document.md](contracts/analysis-document.md)). **Do not bump this schema to cite chats.**
- Detection `review_status` `unreviewed|approved|rejected` and review carry-forward ([detection-finding.md](contracts/detection-finding.md)).
- ImportRun `scan → plan → validate → commit` ([import-run.md](contracts/import-run.md)).
- Workspace backup packs authority, excludes `data/cache/` ([workspace-backup.md](contracts/workspace-backup.md)).
- Ask notebook (`llm_custom_qa`): grounded chunks, citations, **abstain** if unsupported.
- Streamlit IA and jump-to-Reading. Grow Reading / Archive / Search; do not assume a new frontend.

**Derived today, not durable domain objects:** People and Places are NER surface-form read-models (`PlacesService`). Mood → **Moments** is the `moments` salience module (quoted pages) — **not** autobiographical episodes. Analysis delivery “slices” in module registry are unrelated. Do not reuse those names for Slices / Person.

### Architectural constraints (do not violate)

- **Do not** extend `SourceDocument` / `PageIndex` to messages, CSV rows, or photos-as-pages. Contextual imports are a **sibling context corpus**, not notebooks.
- **Do not** make SQLite the system of record. Extend `archive.sqlite` as a rebuildable projection over notebooks **and** context records.
- **Do not** introduce a Personal Knowledge Graph database, a vector DB as default retrieval, live messenger APIs, or a generic “document” type.
- **Do not** change `AnalysisDocument` v1. Multi-source reconstruction uses a new `ReconstructionBundle` (name TBD).
- **Do not** rename Mood → Moments. Product **Slice** = confirmed life episode.
- **Do not** call into TranscriptX libraries. 1.6 imports TX **export files** only ([INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)).
- Scale: one JSON file per WhatsApp message is the wrong shape (10^5 messages). Use collection manifests + JSONL shards + FTS. Photos stay file-per-original (like `sources/`).

### Domain model (intent — contracts later)

Absence of all new types remains a valid 1.0 workspace. `transcribe.project` schema_version **1** stays loadable without a context index (same rule as corpus index).

| Concept | Role |
|---------|------|
| **Notebook / Page / SourceAsset / OCRAttempt** | Unchanged primary-source stack |
| **ContextCollection** | One imported bundle (WhatsApp chat, Telegram JSON, photo folder, TX export, CSV). Stable `collection_id`. Not a notebook |
| **ContextRecord** | One message, photo, transcript segment, mood row, or journal entry. Stable `record_id`. Kind-specific raw payload; participants start as **strings** |
| **TemporalClaim** | Wraps `ApproximateDate`; adds instants, ranges, optional time-of-day. Do not replace page `ApproximateDate` |
| **Entity** | Durable Person (then Place): aliases, mentions, merge/split history, privacy. NER remains extracted until confirmed |
| **EvidenceLink** | `{from_ref, to_ref, relation, status, provenance}`. Relations start small: `same_day`, `near_date`, `depicts`, `participant`, `mentions`, `part_of_slice`, `same_bytes`. JSON/JSONL + rebuildable index — not a graph DB |
| **Slice** | User-owned (or user-confirmed) episode with heterogeneous members. Suggested slices never auto-promote |
| **ReconstructionBundle** | Run-scoped pack of cited records for a question. Not stored as autobiography |

**ClaimStatus** (internal; generalizes existing `date_approved` / detection review / `edited_text` — not a new six-layer ontology):

| Status | Existing analogue | Meaning |
|--------|-------------------|---------|
| `recorded` | SourceAsset bytes, export line, EXIF, CSV cell | Directly present in an artefact |
| `transcribed` | OCR `raw_text`, imported transcript | Machine or human rendering into text |
| `corrected` | `edited_text`, human-set dates | User-owned correction |
| `extracted` | NER, EXIF, `date_source: extracted` | Derived metadata |
| `suggested` | unapproved date, unreviewed detection | Machine proposal |
| `confirmed` | `date_approved`, detection `approved` | Explicit user confirmation |
| `rejected` | detection `rejected`, date ignore | Explicit user rejection |
| `interpreted` | LLM insights, reconstruction answers | Model narrative with citations |
| `speculative` | weak support / abstain-adjacent | Interpreted with weak evidence |

**Product chrome uses four layers:** Evidence · Extraction · Confirmation · Interpretation. Never show an interpretation as if it were a notebook page.

Identity: machine may **suggest** that “Anna” and “Anna W” match; only the user **confirms**. Support split after merge. Conflicting claims: store both; UI shows conflict; user may supersede without erasing. Exports are snapshots — re-import is a new collection version, not live sync.

User copy: say **notebook page** vs **imported evidence**. Avoid “Source” in new APIs (`SourceDocument` stays notebook originals).

### Ingestion architecture

Two families share the ImportRun **lifecycle**, not the notebook page schema:

```text
scan → plan → validate → commit
```

- **Family A — Notebook import** (existing): JPEG/PNG/PDF → SourceAsset → pages → renders → OCR.
- **Family B — Context import** (new from 1.2): adapters emit `ContextCollection` + `ContextRecord[]`. Preallocate IDs. Copy originals. Hash. Crash journal. Duplicate taxonomy by bytes (and platform+chat+native id when present).

Adapters land **one family per release**, not a plugin framework in 1.1:

| Adapter | Release | Notes |
|---------|---------|-------|
| `photo_folder` | 1.2 | EXIF dates; SHA-256 vs notebook sources (`same_bytes` link, not merge). No face recognition. Do not OCR via `JobCoordinator` |
| `whatsapp_export` | 1.4 | `_chat.txt` / zip; one collection per conversation; JSONL (+ monthly shards). **No chat-app UI** |
| `tabular_csv` / `plaintext_journal` | 1.5 | User column mapping; no Daylio schema |
| `telegram_json` | 1.6 | Native fields in raw payload. **Do not** coerce to WhatsApp shape. Shared **index projection** only (`kind, t, participants[], text, collection_id`) |
| `transcriptx_bundle` | 1.6 | TX export files: transcript required; audio optional; summary if present; speakers as strings. No ASR re-run, no TX package |

On-disk sketch (absence valid). Recommend bulky originals in `TRANSCRIBE_CONTEXT_DIR` (sibling of projects); indexes under `data/context/`; both packed in backup; cache still excluded:

```text
{TRANSCRIBE_CONTEXT_DIR}/<collection_id>/
  collection.json
  originals/
  records.jsonl          # or monthly shards
data/context/
  context-index.json
  entities/people/
  entities/places/
  slices/
  links.jsonl
data/cache/archive.sqlite   # disposable; new records tables
```

Lock order: **corpus → context → notebook**. Never invert. `context-doctor` analogue of corpus-doctor.

### Retrieval (do not ship “chat with your journal”)

1. Structured filters (date window, notebook, collection kind, entity, Slice, tags) — extend `ArchiveFilters`
2. FTS on page effective text **and** record text (`record_kind` discriminator)
3. Link traversal (confirmed, then suggested `near_date`)
4. Deterministic aggregations (first/last mention, gaps, mood series)
5. Grounded LLM **only** on a ReconstructionBundle from (1–4); same abstain/citation contract as Ask notebook

Embeddings / vector DBs are **not** a 1.x dependency. In-notebook `semantic_similarity` is TF-IDF BoW — not corpus semantic search. Compute `near_date` through 1.6; persist only user-confirmed links and Slice membership.

### Killer UX and Autobiography view

**1.8 — Life around a page:** Reading stays page-central (scan + effective text). A **Related evidence** panel lists same-day / nearby chats, photos, audio, mood, people, places, Slices, other pages. Wander: page → evidence → Slice → person → place → another page. Not a messaging UI. Cap lists (“14 messages” + sample 3). Empty state if no context imported.

**1.9 — Autobiography:** years → months → weeks → days → pages → evidence. Distinct from Archive (Archive remains the **notebook** diary timeline): show **gaps** (chats/photos without a notebook page, or the reverse); notebook activity as the spine; Slices as labeled bands, not calendar events; Evidence vs Interpretation layers. Not a streak calendar.

Stay on Streamlit `PageSpec`s. If density becomes a wall, a narrow HTML component is allowed; a SPA is **post-2.0**.

### Releases (1.1–2.0)

Each release has one product purpose. Do not dump “2.0 everything.”

| Release | Purpose | Status |
|---------|---------|--------|
| **1.0** | Harden notebook/OCR/analysis (U2 + I0–I6 → **0.9.0** → **0.9-1** testing → freeze). No context corpus | [ ] path (current) |
| **1.1** | Time around a page — related notebook pages by date window | [ ] planned |
| **1.2** | Photographs as contextual evidence (proves sibling corpus) | [ ] planned |
| **1.3** | People as confirmed identities (aliases, merge/split, privacy) | [ ] planned |
| **1.4** | WhatsApp export as high-volume context | [ ] planned |
| **1.5** | Mood / flexible CSV / plaintext journals | [ ] planned |
| **1.6** | Telegram JSON + TranscriptX file import | [ ] planned |
| **1.7** | Slices (user objects first; suggestions off by default) | [ ] planned |
| **1.8** | Related-evidence panel on Reading (killer UX) | [ ] planned |
| **1.9** | Autobiography view (grains + gaps) | [ ] planned |
| **2.0** | Historical reconstruction — cited answers over a retrieved bundle | [ ] planned |

#### 1.0 — Harden the notebook workbench (gate, not this programme)

**Product goal:** A trustworthy local notebook/OCR/analysis product a non-expert can install, transcribe, review, search, analyse, export, and back up.

**UX:** Finish U2 (sample notebook, first-run install path). I0–I6 → **0.9.0** cut. **0.9-1** unfamiliar testing ([dev/user_testing_0_9.md](dev/user_testing_0_9.md)). Inbox polish optional.

**Architecture:** No new domain entities. Time-of-day waits for **1.1**. Foundation checklist on [Path to 0.9.0](#path-to-090--09-1--10) signed off.

**Risks:** Starting autobiography before the gate. Do not sneak WhatsApp into 1.0.

**Exit:** U2 acceptance; I0–I6 exit gate; 0.9.0 tagged; 0.9-1 notes + critical fixes; foundation checklist; PRODUCT still page-first; corpus/hardening gates green.

#### 1.1 — Time around a page (notebook-only)

**Product goal:** Answer “what else in my notebooks belongs with this page?” without new importers.

**UX:** Reading shows other pages in a date window (this notebook + corpus). Search/Archive: tighter range; optional exclude unapproved dates. Page **time-of-day** from diary stamps (`YYMMDD HHMM`) stored alongside `ApproximateDate`. Entity filters on Search only if a cheap NER join exists; otherwise wait for 1.3.

**Architecture:** Additive page time on `PageIndex` (legacy = null). `ArchiveService.related_pages(page_id, window)`. Document ClaimStatus vocabulary in contracts (map existing date/detection/edit states). No `ContextCollection` yet. Relatedness is **computed**, not persisted links.

**Reuse:** `ApproximateDate`, ArchiveService, Reading, `view_jumps`.

**AI:** None. No LLM for relatedness.

**Storage / migration:** Additive `project.json` fields; AnalysisDocument dates stay `YYYY-MM-DD` (do not break fingerprints). Archive indexes rebuildable.

**Risks:** Turning Archive into a calendar. Over-linking inherited dates. Presenting unapproved dates as confirmed.

**Exit:** Related-pages panel; window/precision tests; unapproved dates visually distinct; no context schema shipped.

#### 1.2 — Photographs as contextual evidence

**Product goal:** Dated photographs sit **beside** notebooks, not inside them.

**UX:** Import a photo folder (Workflow → Import Context, or a clearly named sibling — not “new notebook”). Reading: photos on/near the page date (EXIF or filename). Open original. Duplicate notice if SHA matches a notebook source. Copy that scans belong in notebook Import.

**Architecture:** `ContextCollection` + `ContextRecord` kind `photo`. `context-index.json`. EXIF → TemporalClaim `extracted`. EvidenceLink `same_bytes` / computed `near_date`. Archive `records` table. Backup packs context. Context lock; order corpus → context → notebook.

**Reuse:** ImportRun lifecycle, SourceAsset copy/hash/duplicate taxonomy.

**AI:** Deterministic EXIF. Optional on-demand VLM caption = `interpreted`. No auto face ID.

**Migration:** Workspaces without `data/context/` remain valid. Old backup ZIPs restore; new members additive.

**Risks:** Dumping notebook scans here. Fake pages. Running photo OCR through JobCoordinator.

**Exit:** Import/roundtrip/doctor; related photos on a dated page; SHA dedup vs notebooks; backup/restore with photos; 1.0 notebooks untouched.

#### 1.3 — People as confirmed identities

**Product goal:** “Anna” in a notebook can become a Person the user owns, without pretending NER was identity.

**UX:** Person profile: mentions, pages, dates, later photos/chats. Confirm/reject suggestions. Aliases. Merge/split. Privacy hide. Keep Themes → People as the **extracted mention** layer. Place confirmation if it fits this release; otherwise Person-only and Place later.

**Architecture:** `data/context/entities/people/<id>.json`. Mentions → `page_id` / `record_id` + quote + fingerprint. NER rerun carry-forward (detection-review pattern). Suggested matches `status=suggested`.

**Reuse:** `PersonMention`, NER evidence, `entity_sentiment` as extracted tone, tag merge UX.

**AI:** Optional similarity suggestions. Deterministic exact-alias. User confirms. Never silent merge.

**Risks:** Auto-merge; social-graph product; contact sync; treating FAC as people.

**Exit:** Create person from mention; alias; refuse silent merge; profile → Reading; NER rerun preserves confirmations. Empty entity store = today’s Themes People.

#### 1.4 — WhatsApp as high-volume context

**Product goal:** Imported chats become dated evidence around notebook pages, not a messaging app.

**UX:** Import WhatsApp zip/folder; pick chats. Evidence counts (“14 messages with X, 11–13 Sep”). Open a **record card** (timestamp, sender, text, attachment name), not a bubble thread. Link senders to People as suggestions.

**Architecture:** `whatsapp_export` adapter. Collection per conversation. `records.jsonl` (+ monthly shards). Shared index projection for future Telegram. Participants as strings until linked.

**Provenance:** source file + byte/line range. Re-import = new snapshot. No live API.

**Storage:** JSONL + FTS. Original zip preserved. Missing attachments are gaps. Scale test: 100k synthetic messages, doctor, FTS rebuild budget.

**Risks:** Chat UI gravity; unifying with Telegram too early; importing into notebooks; backup size (document sensitivity like page images).

**Exit:** Parse fixture; evidence counts; jump to record; FTS; no thread view as primary.

#### 1.5 — Mood, CSV, and miscellaneous personal records

**Product goal:** Longitudinal mood and other dated text become context without a vendor lock-in.

**UX:** CSV import with column mapping (date/time, mood, notes, extras). Optional plaintext journal. Mood sparkline on the evidence panel. Generic records searchable.

**Architecture:** `tabular_csv` + `plaintext_journal`. Mapping stored on the collection; re-parse from original file + mapping. Do **not** auto-Analyse CSV as a notebook. Do not invent mood from handwriting modules here.

**Risks:** Quantified-self product; universal importer framework — these two adapters only.

**Exit:** Mapped CSV roundtrip; mood near a page; bad headers fail validate; original CSV preserved.

#### 1.6 — Telegram and TranscriptX imports

**Product goal:** Second messenger + spoken-life artefacts; adapters may differ internally.

**UX:** Telegram Desktop JSON (selected chats). TranscriptX bundle: transcript required; audio optional; summary if present. Evidence: “Audio, 13 Sep” → transcript card → optional audio file — not a TX clone.

**Architecture:** `telegram.message` keeps native ids, edits, service messages. `transcriptx.segment` (or document + cues). Speakers as strings → Person suggestions. Still no TX runtime. If TX 1.0 export contract is late, pin a frozen fixture adapter.

**AI:** Do not re-transcribe. Optional on-demand summary only if TX summary absent — labeled `interpreted`.

**Risks:** Porting TX speaker/audio modules; audio-first drift; dual-write with live TX.

**Exit:** Telegram fixture ≠ WhatsApp schema; TX import without TX package; speakers suggest people; audio optional; doctor.

#### 1.7 — Slices

**Product goal:** Name a period of life and hang heterogeneous evidence on it.

**UX:** Create Slice “Moving to Paris”; add pages 143–157, chats, photos, people. Slice view = member timeline. From a page: “Add to Slice.” Machine suggestions off by default; never auto-create.

**Architecture:** One JSON per slice under `data/context/slices/`. Links `part_of_slice`. Suggestion job frozen like Analyse; cannot publish without confirm. Do **not** run the 25 notebook modules on a Slice as a fake project.

**Risks:** Auto-biography chapters; PKM maps; renaming Mood → Moments.

**Exit:** CRUD Slice; mixed-kind members; Reading shows Slice chips; suggestions cannot publish without confirm.

#### 1.8 — Life around a page (killer UX)

**Product goal:** Wander a life from a handwritten page using everything ingested so far.

**UX:** Page image + text central; Related evidence beside/under. Honest empty states. Distinguish confirmed vs suggested vs interpreted.

**Architecture:** `EvidencePanelService` read-model over Archive + links. Precomputed `near_date` index in sqlite; bump `archive.generation`. No new system of record.

**AI:** None required. Optional panel summary waits for 2.0.

**Risks:** Clutter; Streamlit rerun lag; replacing the scan.

**Exit:** Fixture workspace (notebook + photos + WhatsApp); jumps work; layer honesty.

#### 1.9 — Autobiography view

**Product goal:** Navigate life at year/month/week/day with the notebook as spine, including gaps.

**UX:** New primary nav **Autobiography**. Not an Archive clone. Settings for which layers show.

**Architecture:** Aggregations over archive sqlite. Gap = interval with context but no dated notebook page (or vice versa).

**AI:** None on the canvas. Optional interpreted captions behind a toggle, cited.

**Risks:** Calendar product; streak gamification; hiding notebooks behind chats.

**Exit:** Grain navigation; gap visibility; click to page/Slice/person; notebooks-only still works (other layers empty).

#### 2.0 — Historical reconstruction

**Product goal:** Ask reconstruction questions and get **cited** answers that lead back to pages, messages, photos, transcripts, mood rows.

**UX:** **Reconstruct** (name TBD) — does **not** replace Ask notebook (single-notebook grounded QA). Question → retrieved bundle → answer with layer tags and clickable citations. Abstain if weak. Show conflicting sources.

Example questions (retrieve evidence, then optionally interpret): What was happening around this entry? When did I first think about moving to Paris? What did I repeatedly worry about? How did my relationship with X change? What themes recur? What changed between 2018 and 2024?

**Architecture:** ReconstructionBundle builder (filters + FTS + links + Slice). LLM answers **only from the bundle**; JSON claims `{text, refs[], status}`. New coordinator; do not clobber notebooks; **do not** change `AnalysisDocument` v1. Hard cap bundle size. No tool-calling over the whole disk.

**Reuse:** `llm_custom_qa` abstain/cite, chunking, AnalysisCoordinator, `OllamaTextClient`.

**Storage:** Reconstruction runs are derived. Default backup: user-confirmed notes only, not raw runs.

**Risks:** Chatbot gravity; hallucinated life; embeddings-as-magic; prompt-stuffing the corpus.

**Exit:** Gold citation fixtures; abstain test; conflict display; Ask notebook still works; AnalysisDocument v1 unchanged; PRODUCT thesis still true.

### Cross-cutting infrastructure

- Format registry: add formats in `src/transcribe/persistence/schema.py` when each release ships
- CLI: `context-import`, `context-doctor`; UI and CLI share services; core still must not import Streamlit
- Privacy: remote-Ollama ack unchanged; geocode stays opt-in; reconstruction sends **retrieved text** to local LLM only; backups containing chats/photos are sensitive (same honesty as page images)
- Reprocessing: parse frozen in collection; re-parse explicit; entity/Slice confirmations carry forward
- IDs: UUID hex; never path-derived
- Export `transcribe.notebook` stays **notebook-only** through 2.0 unless a separate autobiography export is designed later
- Streamlit IA: add `PageSpec`s slowly; stay-don’t-bounce preserved

### Testing strategy

Contracts first, then unit parsers, then acceptance (mirror [tests/acceptance/corpus/](../tests/acceptance/corpus/)).

- **1.1:** date window / precision / unapproved honesty
- **1.2–1.6:** synthetic fixtures (WhatsApp, Telegram JSON, CSV, photo EXIF, fake TX bundle); plan/commit/idempotency/crash
- **Scale:** 100k-message FTS rebuild budget, offline
- **1.3:** merge/split/carry-forward (mirror detection review tests)
- **1.7:** Slice membership; suggestions cannot publish
- **1.8–1.9:** UI contract tests (copy, jumps)
- **2.0:** gold citations + abstain; fake Ollama; stale fingerprint citations

No live WhatsApp/Telegram/Ollama in default CI. Doctor deep-hash originals. Backup gate extended.

### Explicitly not to build yet

- Universal PKM / Zettelkasten / knowledge-graph DB
- Live WhatsApp / Telegram / email APIs or scrapers
- Chat-with-your-life as the home screen
- Face recognition / biometric identity / automatic identity merge
- Vector DB as default retrieval; SQLite as authority; task-queue worker fleet
- React / Gradio rewrite
- Treating photos/chats as notebook pages
- Porting TX speaker/audio modules (`interactions`, `pauses`, `voice_*`)
- Cloud OCR/sync; multi-user social graph
- Calendar or quantified-self dashboards as the product
- Deferred analysis ports (`politeness`, `echoes`, …) disguised as autobiography
- Universal plugin importer before three adapters exist
- Schema bump of `AnalysisDocument` v1 for messages

### Implementation order

1. Finish **1.0** via [Path to 0.9.0 / 0.9-1 / 1.0](#path-to-090--09-1--10). Freeze notebook core.
2. Contracts for ClaimStatus + TemporalClaim + context-index **before** photo code (1.1–1.2).
3. **1.1** related pages → **1.2** photos → **1.3** people → **1.4** WhatsApp → **1.5** CSV/mood → **1.6** Telegram + TX → **1.7** Slices → **1.8** evidence panel → **1.9** Autobiography → **2.0** reconstruction (LLM last).

Do not parallelize 1.2 schema with 1.4 parsers until context-index / doctor / backup exist.

### Open architectural questions

Defaults for implementers; revisit with evidence:

1. Context binaries in `TRANSCRIBE_CONTEXT_DIR` vs under `data/` — recommend sibling + `data/context/` index.
2. Persist `near_date` links vs compute-only — compute through 1.6.
3. Place entities in 1.3 vs later — Person in 1.3; Place if it fits.
4. Thread view — never primary; optional debug expander.
5. Reconstruction runs in backup — confirmed notes only.
6. TX export pin — frozen fixture if TX 1.0 is late.
7. Time-of-day in 1.0 vs 1.1 — **1.1**.
8. Streamlit density at 1.8 — HTML island allowed; SPA not.
9. Conflicts — show both; supersede, don’t erase.
10. If users dump notebook scans as “photos,” offer **promote photo → notebook page** rather than collapsing models.

---

## Later candidates — uncommitted — [?]

Worth recording without scheduling. Rows pulled into [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned) are marked.

- Cross-notebook links / related pages — **scheduled 1.1** (notebook date windows; computed, not a graph)
- Corpus-level Analyse / search (cross-notebook products — **not** Bulk Analyse orchestration above). **2.0 reconstruction** is retrieved-evidence QA, not a cross-notebook Analyse runner; a corpus Analyse product remains uncommitted
- Bookmarks / favourites
- Annotations distinct from OCR corrections
- Batch metadata editing
- Image-only / non-OCR page handling

---

## Shipped capabilities

| Capability | Shipped |
|------------|---------|
| **OCR lifecycle** | multipass compare, prefer/promote, composite, preference hints, fine-tune export; timeout + model-load fail-fast circuits |
| **Notebook metrics** | stats, lexical diversity, understandability |
| **Page ink / blankness** | Pillow coverage %, blankness %, dominant ink hue (Review + Analyse Overview; not a text Analyse module) |
| **Language** | NER, sentiment, epistemic markers, entity sentiment, keyphrases |
| **Themes** | wordclouds, topic modeling, BERTopic, semantic similarity, topic shift |
| **Mood & salience** | emotion family, affect tension, moments |
| **Synthesis** | highlights, summary, insights |
| **Optional local LLM** | summary, action items, Ask notebook, narrative summary |

Exact module IDs, dependency history, slices 1.1–1e.2, TX pins, and implementation gates: [analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md). Disposition and notebook reinterpret notes: [analysis_module_porting.md](dev/analysis_module_porting.md).

LLM modules are optional at runtime (local text Ollama); deterministic `highlights` → `summary` → `insights` work offline.

---

## Deferred analysis candidates — not scheduled — [−]

**Decision (2026-08-09):** Reinterpretation module work is **deferred**. Product focus is robustness and UX for the shipped core set (see **Now**). Need for these notebook reinterpretation outputs is unproven; do not schedule them while the usability wave’s open track (**U2**) is the priority — revisit only when product reopens the disposition map.

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

Intrinsically transcript-, speaker-, or audio-specific. Documented so they are not accidentally scheduled. Exhaustive module list: [analysis_module_porting.md](dev/analysis_module_porting.md).

| Family | Examples |
|--------|----------|
| **Speaker interaction** | `interactions`, `contagion` |
| **Audio / timing** | `pauses`, `voice_*` family, `prosody_dashboard` |
| **ASR-specific** | `transcript_quality` (notebook `ocr_quality` remains deferred above) |
| **Speaker-conditioned synthesis** | `llm_speaker_summary` |

---

## Product scope beyond analysis modules

Still the more central product surface than speculative analysis work. Detail and sequencing for **through 1.0** live in the **corpus / bulk import**, **preprocessing system**, **corpus & product lifecycle**, and **release / onboarding** sections above. Post-1.0 autobiography sequencing lives in [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned).

Summary:

- OCR pipeline — import, vision OCR, optional second-pass cleanup; **multipass compare / prefer / promote / composite / fine-tune export** (OCR lifecycle package — shipped)
- **Preprocessing** — visual declutter (human, on by default at import + explicit re-apply) vs OCR optimisation (`gentle_contrast` only today, off by default; other OCR profiles deferred) — see **Preprocessing system** above
- **Notebook corpus** — contracts runtime-normative; bulk import supported; import recovery / inbox as the user-facing continuation
- **Living with notebooks** — organisation metadata, first-class search, reading mode, review UX
- **Longevity** — **workspace backup/restore shipped**; upgrade/migration story and archive-readable-without-Transcribe remain candidates
- **Operability** — model/runtime management UX; release/onboarding/diagnostics; prompt management; local quality/evaluation loop (thumbs + fixtures)
- **Maintainer infrastructure** — CI, release hygiene, hosted docs — [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md) (**0.9.0** cut with U2; then **0.9-1** testing → **1.0**)
- **Export** — notebook readability and sharing (`transcribe.notebook`)
- **Runtime docs** — Docker / local Ollama — [runtime/docker.md](runtime/docker.md) (supports operability; does not replace it)
- **Future TranscriptX export handoff** — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) (not a dependency)
- **After 1.0 autobiography workbench** — contextual evidence around notebooks, Slices, cited reconstruction — [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned) (gated on 1.0; not current core)

---

## Future metadata

- Page **time-of-day** metadata (from diary stamps like `YYMMDD HHMM` / similar): **scheduled 1.1** (not 1.0). Storage alongside `ApproximateDate`, UI, archive indexing, and analysis policy. Date auto-extraction currently ignores time. AnalysisDocument unit `date` stays `YYYY-MM-DD` so fingerprints do not break.
