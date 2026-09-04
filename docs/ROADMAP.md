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
**Architecture follow-ups (candidates, not 0.9):** [reviews/architecture_from_evidence.md](reviews/architecture_from_evidence.md) · [Later — Architecture follow-ups](#later--architecture-follow-ups-from-evidence-review--candidates)

> **Status legend:** [ ] planned · [~] in progress · [x] done · [−] deferred · [?] candidate (uncommitted)

## Current state

Transcribe has the complete 25-module core notebook-analysis set (pins in [dev/analysis_port_pins.md](dev/analysis_port_pins.md); slices **1.1 → 1e.2** in [analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md)). The **OCR lifecycle package** (multipass compare, prefer/promote, composite, fine-tune export) is **shipped**. Current work is the **usability wave** ([usability_wave_plan.md](usability_wave_plan.md)): Analyse trust + product UX (**U0–U1**) and daily workbench (**U3**) are **done**; remaining focus is first-run operability (**U2**), with corpus bulk import **supported** after the acceptance gate (**U4** mechanics done; Inbox polish may continue). No additional analysis modules are scheduled. Architecture is verbatim-ish analytical cores plus thin notebook adapters over canonical `AnalysisDocument` units; durable analysis is project-local under optional `analysis/` ([project-on-disk](contracts/project-on-disk.md), [analysis-run-storage](contracts/analysis-run-storage.md)). Historical port implementation gates live in [analysis_wave1_plan.md §9](archive/plans/analysis_wave1_plan.md#9-implementation-gate).

The roadmap’s analysis surface is largely complete. **Remaining product gaps are first-run operability (U2) and optional corpus-lifecycle polish**, not more analysis capability. Sequencing for that focus: [usability_wave_plan.md](usability_wave_plan.md) (tracks **U0–U4**).

**Package is 0.8.7.** Version ladder to autobiography:

```text
0.6.x  →  0.7.0  →  0.8.0  →  0.8.5  →  0.8.6  →  0.8.7 (now)  →  0.9.0 cut  →  0.9-1 unfamiliar testing  →  1.0  →  After 1.0 (1.1–2.0)
              I0–I1     I2–I3     patch     product     patch         U2 + I6          tag + hosted docs      findings → fixes         freeze     autobiography
                                                                      (I5 Pages landed)```

| Label | Meaning |
|-------|---------|
| **0.7.0** | Developer lanes + PR CI honesty gate (**I0–I1**). Makefile, `tests/README.md`, GitHub Actions matrix 3.10–3.12, compose-bind assert. |
| **0.8.0** | Release hygiene + quality gates (**I2–I3**). `scripts/release/*`, `release_governance.md`, coverage fail-under, pre-commit, CI `release-checks`. |
| **0.8.5** | Product patch on 0.8.0: cover-page skip in ink metrics; Analyse batch pick labels show published status. |
| **0.8.6** | Post-U3 product cut: OCR Review workbench, export typography/cover/ignore-pages, Sphinx docs (**I4**), Ask history, Detect → Workflow nav, chart colours, detection tag approval. |
| **0.8.7** | Product patch: names + lexical detectors, Review/Library polish, Detect accept-per-page, circuit CLI honesty, action-link appearance. |
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
| **U3 Daily workbench** | [x] | Review as needs-attention queue, Reading mode, Search/Library filter parity, organisation polish, model/runtime product copy — **without** requiring bulk corpus activation |

**Also landed with U3:** Library activity-bin click filter; Library cover-grid paging (`ui.archive_notebooks_initial`, default show-all); page delete in the viewer; model-information expander wired to live picker selection on Transcribe panels.

**Post-U3 deepen-in-place (shipped, not a new wave track):** OCR hang / model-load fail-fast circuits; Compare OCR attempt previews escape markdown so Prefer/Promote stays readable; Analyse Moments jump-to-page; Overview/Mood this-vs-corpus/period charts (PR #25). **OCR Review workbench:** scan + tabbed review lanes (Transcription / Date / Tags / OCR / Cleanup / Other), disagreement-centric review, merged draft as recommendation not vote ([ocr_review_workbench_plan.md](dev/ocr_review_workbench_plan.md)).

### U4 — Corpus UX — [x] gate green (Inbox polish may continue)

Bulk inbox / import recovery is **supported**. The [corpus-integrity acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is green. See usability-wave **U4** and **Next — Notebook corpus**. Remaining Inbox polish (e.g. richer needs-review taxonomy / `TRANSCRIBE_INBOX_DIR` scan) may continue without reopening the gate.

Near-future deepen-in-place (planned, Reader-facing): **Ignore pages** — let users mark uninteresting pages as ignored so they are omitted from Reader by default. Make this a toggle with configurable default settings (workspace/user), plus an explicit “show ignored” override in Reader UI. **Shipped (export slice):** Workflow → Export → **Exclude ignored pages** (default on) omits `ignored` pages from reading formats (Markdown/HTML/PDF/EPUB/text); JSON export keeps the full notebook. **Future:** include/exclude export pages by tag (AND filter, same semantics as Reading/Library).

**Page scan fullscreen (Reader / Review):** Today uses Streamlit’s built-in `st.image` hover toolbar (**View fullscreen**). **Candidate — click image → black lightbox:** Streamlit has no API for click-to-fullscreen or a black backdrop ([streamlit#8031](https://github.com/streamlit/streamlit/issues/8031)). Revisit when that lands; until then, optional custom JS below (parent-frame overlay, same pattern as Review hotkeys).

<details>
<summary>Custom JS lightbox (safekeeping — not wired in app)</summary>

```javascript
(function () {
  const parent = window.parent;
  if (!parent) return;

  function ensureOverlay() {
    let overlay = parent.document.getElementById("tx-page-lightbox");
    if (overlay) return overlay;
    overlay = parent.document.createElement("div");
    overlay.id = "tx-page-lightbox";
    overlay.style.cssText = [
      "display:none", "position:fixed", "inset:0", "z-index:999999",
      "background:#000", "cursor:zoom-out", "align-items:center",
      "justify-content:center", "padding:1rem", "box-sizing:border-box",
    ].join(";");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Page scan fullscreen");

    const img = parent.document.createElement("img");
    img.id = "tx-page-lightbox-img";
    img.style.cssText = [
      "max-width:100%", "max-height:100%", "object-fit:contain",
      "cursor:default", "user-select:none",
    ].join(";");
    img.addEventListener("click", (e) => e.stopPropagation());

    overlay.appendChild(img);
    overlay.addEventListener("click", () => {
      overlay.style.display = "none";
      img.removeAttribute("src");
    });
    parent.document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay.style.display !== "none") {
        overlay.style.display = "none";
        img.removeAttribute("src");
      }
    });
    parent.document.body.appendChild(overlay);
    return overlay;
  }

  parent.txOpenPageLightbox = function (src) {
    const overlay = ensureOverlay();
    const img = parent.document.getElementById("tx-page-lightbox-img");
    img.src = src;
    overlay.style.display = "flex";
  };
})();

// Per-image bind (inject via components.html after st.image in a keyed container):
// root.querySelector('[data-testid="stImage"] img').addEventListener('click', (e) => {
//   e.preventDefault(); e.stopPropagation();
//   parent.txOpenPageLightbox(img.src);
// });
```

</details>

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

## Next — Detection fine-tune export — [?] candidate

Extend the shipped OCR **fine-tune export** pattern ([finetune-export](contracts/finetune-export.md), [finetune_export.md](finetune_export.md)) to **prompt-backed Detection**: export page images + effective text with **approved / rejected** finding labels as a local dataset for **external** detector fine-tuning (Transcribe does not train in-app).

| Outcome | Intent |
|---------|--------|
| **Review-labelled export** | Turn user review of detection suggestions — e.g. `todo_lists`, `lists`, `poetry`, custom detectors — into positive/negative training pairs. Approved findings = positive examples; rejected = negatives or hard negatives. Unreviewed findings excluded by default. |
| **Finding-aware samples** | Each JSONL row ties image + text window to span boundaries, `finding_type`, detector + prompt provenance, and `review_status` ([detection-finding](contracts/detection-finding.md)). Reuse existing carry-forward semantics so re-runs do not orphan labels. |
| **Per-detector datasets** | Filter by `detector_id` / `finding_type`; optional include neighbouring page context for cross-page spans. Same privacy model as OCR export — user copies the folder; no network upload. |

**Rules of thumb:** Detection export is a deepen-in-place on the evaluation loop, not a new detection runtime. Ship after detection review UX is stable enough to accumulate trustworthy labels. Not on the **0.9.0** path.

---

## Next — Corpus & product lifecycle — [?] candidates (partially pulled)

Primary post-hardening direction for living with many notebooks. **Usability-wave U3** pulls Review UX, reading mode, search deepening, organisation polish, and model/runtime management as committed work on today’s project model (no bulk corpus activation required). **U4** covers import recovery / inbox (gate green; Inbox polish may continue). Remaining rows stay uncommitted candidates.

| Outcome | Intent | Wave |
|---------|--------|------|
| **Search (first-class)** | Full-text across notebooks; date / tag / entity filters; jump-to-page; eventually saved searches. With dozens of notebooks this may matter more than Analyse. | **U3** date/tag/jump done; Moments/chart jump → Reading done; entity filters → After 1.0 **1.1/1.3**; saved searches still candidate |
| **Notebook organisation** | Titles, descriptions, tags/collections, archive state, sort order, cover/thumbnail, lightweight notebook metadata — how users live with a multi-notebook corpus. Library cover-grid paging (`ui.archive_notebooks_initial`) + activity-bin filter + page delete landed. Workspace tag catalogue (labels, colours, rename/merge) + viewer click-to-filter + detection auto-tag: [tag-catalog.md](contracts/tag-catalog.md). | **U3** tag chips + sort polish done; catalogue/filter/auto-tag shipped as deepen-in-place; collections/archive-state candidate |
| **Page reordering & date repair** | Add a drag/drop thumbnail grid to reorder notebook pages after scan upload order errors, plus a “move suspiciously dated page to end of confirmed date cluster” action that updates page-number navigation. See plan: [page reorder plan](../../.cursor/plans/page_reorder_plan_6d561135.plan.md). | candidate |
| **Re-OCR / reprocessing** | **Moved to OCR lifecycle package above** (multipass, compare, prefer/promote, composite, fine-tune export). | **OCR lifecycle** (done) |
| **Import recovery / inbox** | Continuations of bulk import as a daily workflow (see above), not only the ImportRun machine. | **U4** (gate green; polish open) |
| **Reading mode** | Clean chronological in-app reading: page image/text pairing, dates, navigation, optional distraction-free layout — distinct from Review, Analyse, and export. | **U3** (done) |
| **Backup / restore / portability** | Full-workspace ZIP (`transcribe.workspace-backup` v1): create/verify/restore via CLI + Settings → Configuration → Backup; replace-only restore with automatic safety ZIP; corpus-doctor after restore. Contract: [workspace-backup.md](contracts/workspace-backup.md). | **[x] done** |
| **Data longevity / upgrades** | Notebooks survive Transcribe upgrades: migration UX, pre-upgrade backup, refusal/recovery, and “archive remains readable without Transcribe” where feasible — broader than schema contracts alone. | **0.9 path (thin):** pre-upgrade backup + restore verify in first-run/backup docs — [Path to 0.9.0](#path-to-090--09-1--10) foundation checklist. Full “archive readable without Transcribe” remains candidate |
| **Model & runtime management** | Comprehensible UX over installed OCR/text models: availability, size, last-used, refresh, health, recommendations. Ollama machinery exists; users need a product abstraction. Model-information expander follows live Transcribe picker selection. | **U3** (done) |
| **Quality / evaluation loop** | Alongside thumbs: sampled OCR accuracy review, cleanup accept/reject, analysis usefulness ratings, local regression fixtures — local evidence that changes improve Transcribe, not analytics telemetry. | candidate |
| **Detection fine-tune export** | Export approved/rejected detection findings (e.g. to-do list suggestions) as labelled datasets for external detector fine-tuning — same “export only, train elsewhere” model as OCR fine-tune export. | candidate — see **Detection fine-tune export** |
| **Prompt management UI** | **Shipped (Detection wave 2):** Settings → Prompts hub for OCR, cleanup, and detection prompts (browse / override / custom / dry-run). Analysis inline prompts remain module-local. | **shipped** (parallel) |
| **Prompt-backed Detection** | **Shipped (Detection wave 2 +):** Built-ins `poetry`, `todo_lists`, `lists`, `quotations`, `beer_labels`, lexical `first_person` / `swear_words`, `names` (people from NER) + declarative custom detectors; View → Detect; findings under `detection/`. See [detection_wave2_plan.md](archive/plans/detection_wave2_plan.md) + detection contracts. | **shipped** (parallel) |
| **Quality ratings (thumbs)** | Collect-only local ratings for transcription and analysis outputs; shape/code from TranscriptX LLM feedback v1 — not a substitute for deferred `ocr_quality` analysis. | candidate |
| **Review UX** | Faster correction and approval of OCR text and dates. | **U3** (done); OCR Review workbench deepen-in-place shipped |
| **Export / readability** | **Shipped** — EPUB/PDF/HTML, typography options (25 curated free/system body fonts), export profiles, multi-notebook anthology (provenance via U0 #13), **exclude ignored pages** toggle. Further reading-mode polish remains a separate candidate above. **Candidate:** user-uploaded custom fonts; **future:** include/exclude by tag. | **shipped** |
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

**Status:** [~] in progress — authoritative sequencing from package **0.8.7** toward a frozen **1.0** notebook workbench ready for After 1.0. Does not schedule autobiography features. Companion tracks: [usability_wave_plan.md](usability_wave_plan.md) (U2), [infrastructure_wave_0_9_plan.md](infrastructure_wave_0_9_plan.md) (I0–I6), [dev/user_testing_0_9.md](dev/user_testing_0_9.md) (0.9-1).

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
| **I2** Release hygiene + governance | [x] | `scripts/release/*`, secrets/denylist, `release_governance.md`, dependency audit log |
| **I3** Quality gates | [x] | Coverage fail-under, pre-commit, partial CI `release-checks` |
| **I4** Hosted docs | [x] | Sphinx over existing Markdown, `.[docs]`, `.readthedocs.yml` scaffold, CI docs job |
| **I5** Public landing | [x] | Modest `website/` + GitHub Pages assemble; optional workflow screenshot walkthroughs |
| **I6** Sustaining lanes | [ ] | Nightly acceptance/offline heavy, Docker smoke in release-checks, issue templates |

Suggested cut order: **I0+I1** (0.7.0, landed) → **I2+I3** (0.8.0, landed) → **I4** (Sphinx, landed) → **I5** (Pages landing, landed) → **I6**. U2 may parallel throughout; both tracks required for the **0.9.0** package cut.

**Infra exit gate (summary):** green PR CI on the Python matrix; Makefile/CI/`# pre-release` share lane names; tag authority is `docs/dev/release_governance.md` with script-backed evidence; Sphinx builds in CI and Pages (or documented RTD go-live) can publish the guide; coverage + secrets gates enforced; nightly (or equivalent) runs heavier offline suites without live Ollama.

**Already landed (do not rebuild in I0–I6):** offline default pytest suite, acceptance gates, Markdown docs authority/indexes/archive, Docker Compose loopback bind docs, root `SECURITY.md` / `CONTRIBUTING.md` / `CHANGELOG.md`, agent SOPs, **I4 Sphinx / CI docs job**.

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

When **U2 acceptance** and the **I0–I6 exit gate** are both true: bump `pyproject.toml` / `__version__` / CHANGELOG to **0.9.0**. Intermediate cuts landed: **0.7.0** = I0+I1; **0.8.0** = I2+I3; **0.8.5** = product patch; **0.8.6** = post-U3 product cut + **I4** Sphinx/CI docs; **0.8.7** = names/lexical detectors, Review/Library polish, circuit CLI honesty. Remaining infra: **I6** (I5 Pages landing landed).

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
- PageSpec IA, stay-don’t-bounce, jump-to-Reading, and the UI/core Streamlit boundary ([ARCHITECTURE.md](ARCHITECTURE.md) · `test_core_no_streamlit`). Grow Reading / Library / Search. **Working default:** Streamlit through 2.0 — do not assume a new frontend in 1.x. The **host** (Streamlit vs a later native/SPA client) is a reopenable decision, not a scheduled track — [UI host](#ui-host-working-default--reopen-with-evidence).

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

#### Future context import candidates — [?] uncommitted

Worth recording after the committed **1.2–1.6** sequence. Same Family B rules: user-provided **export files only** (no live APIs, scrapers, or OAuth sync); `ContextCollection` + `ContextRecord`; re-import = new snapshot; treat like chats/photos in backup sensitivity.

| Source | Typical export | Evidence role | Notes |
|--------|----------------|---------------|-------|
| **Spotify / Last.fm** | Spotify account data JSON (extended streaming history); Last.fm scrobble CSV or GDPR export | Music listened to near a page date | Timestamps → `TemporalClaim`; artist/track/album as record text. No streaming API or scrobble daemon |
| **Amazon purchases** | Order history CSV (“Download order reports”); GDPR/data-request bundle | Purchases as dated commercial activity | Order date, item title, category; likely extends `tabular_csv` or a thin dedicated adapter; strip or user-control shipping/payment fields |
| **Browser / search history** | Chrome/Firefox/Safari export; Google Takeout (Chrome history, My Activity) | Web pages and queries around dates | High volume — JSONL sharding like WhatsApp; URL, title, visit time, search query; among the most privacy-sensitive imports |
| **Google Maps Timeline** | Google Takeout Location History (JSON) | Visits, stays, movement | Complements NER **Places** (extracted mentions) with GPS-derived places; segment records with start/end; geocode policy unchanged (opt-in) |
| **Calendar** | `.ics` export; Google/Apple/Microsoft Takeout | Scheduled events around pages | Event title, time range, location string, attendees as strings → Person suggestions. **Not** a calendar product — evidence only (see non-goals) |

Evaluate after **1.6** (shared context index + doctor + backup) and **1.8** (Related evidence panel proves cross-source value). One adapter per release; no universal importer framework before three post-1.6 adapters ship.

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

**1.9 — Autobiography:** years → months → weeks → days → pages → evidence. Distinct from Library activity (the **notebook** diary timeline): show **gaps** (chats/photos without a notebook page, or the reverse); notebook activity as the spine; Slices as labeled bands, not calendar events; Evidence vs Interpretation layers. Not a streak calendar.

Stay on Streamlit `PageSpec`s through 2.0. If density becomes a wall, a narrow HTML/JS island is allowed (same pattern as Review hotkeys); a SPA or native rewrite is **post-2.0** unless the [UI host](#ui-host-working-default--reopen-with-evidence) questions are explicitly reopened with 1.8–1.9 evidence.

### UI host (working default — reopen with evidence)

Not a 1.x track. Do not block **1.0** or **1.1–1.7** on a frontend change. Streamlit remains the supported interactive surface ([public_surfaces.md](public_surfaces.md)).

**Working default through 2.0:** Streamlit `PageSpec`s; stay-don’t-bounce; jump-to-Reading; HTML/JS islands when density or interaction APIs fail (Review hotkeys already; page-scan lightbox is a candidate in **Now**). Core packages still must not import Streamlit. A React / Gradio / native rewrite stays in [Explicitly not to build yet](#explicitly-not-to-build-yet).

**Why this is a decision, not a freeze forever:** the GUI is a large Streamlit product on a clean service boundary (UI ~38k LOC, ~2k `st.` calls; services/CLI already share the kernel; `test_core_no_streamlit` holds). A fully custom native interface is **architecturally feasible** and **not a framework swap**: presentation, navigation state (`st.session_state` / rerun), CSS/DOM overlays, iframe hotkeys, and Altair/`st.map`/wordcloud islands would be reimplemented. Highest Streamlit friction today: **Review**, **Reading / page viewer**, **Library**. There is **no HTTP/IPC API** — UI calls services in-process. TranscriptX is also Streamlit; a Transcribe host change diverges presentation unless both products later share a frontend programme.

**Reopen when (any):** 1.8 Related evidence or 1.9 Autobiography is unusable even with an HTML island; Review/Reading interaction debt (keyboard, lightbox, split pane) blocks the autobiography UX; Docker `transcribe-web` and a future desktop shell cannot share one client. Do not reopen because another stack is fashionable.

**If reopened, decide in this order** (defaults until decided): [Open architectural questions](#open-architectural-questions) 8, 11–16. Sketch: evidence first → optional local API/IPC → one heavy surface (Review/Reading) as a strangler → Settings last. Full parity is a multi-year programme, not a release item.

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

**UX:** Reading shows other pages in a date window (this notebook + corpus). Search/Library: tighter range; optional exclude unapproved dates; and a configurable ignore list so extracted dates from pages whose Detect categories match (e.g. label/packaging) are treated as `rejected`/unapproved by default. Add date-window presets (`same day`, `3 days`, `1 week`, `1 month`) and group related pages by temporal proximity (`same day`, `nearby`, `same week`). Allow previous/next **dated** page jumps across the corpus. Show date-source / confidence badges (explicit on page, inherited, manual correction) and a quick exact-only filter chip so inherited or weak dates can be hidden. Page **time-of-day** from diary stamps (`YYMMDD HHMM`) stored alongside `ApproximateDate`. Optional **estimated writing time** per page/notebook from OCR word count and a user-set average words-per-minute; label as approximate and allow workspace/user override. Entity filters on Search only if a cheap NER join exists; otherwise wait for 1.3.

**Architecture:** Additive page time on `PageIndex` (legacy = null). `ArchiveService.related_pages(page_id, window)` plus previous/next dated-page lookups over the same index. Date-source / confidence is a read-model over existing page date state (explicit extraction, inherited notebook date, manual review), not a new autobiography entity. Estimated writing duration is derived, not authored metadata: persist only the configured WPM setting and recompute from approved/current page text. Document ClaimStatus vocabulary in contracts (map existing date/detection/edit states). No `ContextCollection` yet. Relatedness is **computed**, not persisted links.

**Reuse:** `ApproximateDate`, ArchiveService, Reading, `view_jumps`, existing date review state.

**AI:** None. No LLM for relatedness.

**Storage / migration:** Additive `project.json` fields; AnalysisDocument dates stay `YYYY-MM-DD` (do not break fingerprints). Archive indexes rebuildable.

**Risks:** Turning Archive into a calendar. Over-linking inherited dates. Presenting unapproved dates as confirmed. Letting date-source badges imply more certainty than the underlying extraction/review state supports. Treating estimated writing time as exact despite OCR noise, edits, or non-prose pages.

**Exit:** Related-pages panel; window/precision tests; window presets and temporal grouping in Reading/Search; previous/next dated-page jumps; inherited/unapproved/ignored-by-category dates visually distinct with exact-only filter and source badges; estimated writing time clearly marked approximate and derived from configurable WPM; no context schema shipped.

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

**UX:** Person profile: mentions, pages, dates, later photos/chats. Confirm/reject suggestions. Aliases. Merge/split. Privacy hide. Keep People & Places → People as the **extracted mention** layer. Place confirmation if it fits this release; otherwise Person-only and Place later.

**Architecture:** `data/context/entities/people/<id>.json`. Mentions → `page_id` / `record_id` + quote + fingerprint. NER rerun carry-forward (detection-review pattern). Suggested matches `status=suggested`.

**Reuse:** `PersonMention`, NER evidence, `entity_sentiment` as extracted tone, tag merge UX.

**AI:** Optional similarity suggestions. Deterministic exact-alias. User confirms. Never silent merge.

**Risks:** Auto-merge; social-graph product; contact sync; treating FAC as people.

**Exit:** Create person from mention; alias; refuse silent merge; profile → Reading; NER rerun preserves confirmations. Empty entity store = today’s People & Places → People.

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

**Risks:** Clutter; Streamlit rerun lag; replacing the scan. Density here is the first honest test of the Streamlit host — prefer an HTML island over a frontend rewrite ([UI host](#ui-host-working-default--reopen-with-evidence) question 8).

**Exit:** Fixture workspace (notebook + photos + WhatsApp); jumps work; layer honesty.

#### 1.9 — Autobiography view

**Product goal:** Navigate life at year/month/week/day with the notebook as spine, including gaps.

**UX:** New primary nav **Autobiography**. Not an Archive clone. Settings for which layers show.

**Architecture:** Aggregations over archive sqlite. Gap = interval with context but no dated notebook page (or vice versa).

**AI:** None on the canvas. Optional interpreted captions behind a toggle, cited.

**Risks:** Calendar product; streak gamification; hiding notebooks behind chats. Grain navigation may stress Streamlit density the same way 1.8 does — HTML island allowed; do not use 1.9 to justify a SPA.

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
- Streamlit IA: add `PageSpec`s slowly; stay-don’t-bounce preserved. Treat PageSpec, interface-menus, action IDs, and workspace settings as **host-agnostic contracts**; do not encode `st.session_state` keys or CSS `:has()` overlays as product rules. Host change is a reopenable decision — [UI host](#ui-host-working-default--reopen-with-evidence)

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
- React / Gradio / native rewrite as a 1.x or 2.0 delivery item (Streamlit through 2.0 is the working default; reopen only via [UI host](#ui-host-working-default--reopen-with-evidence), not because another stack is fashionable)
- Treating photos/chats as notebook pages
- Porting TX speaker/audio modules (`interactions`, `pauses`, `voice_*`)
- Cloud OCR/sync; multi-user social graph
- Calendar **app** or quantified-self **dashboards** as the product (importing calendar **exports** as dated evidence is a separate candidate — [Future context import candidates](#future-context-import-candidates--uncommitted))
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
8. Streamlit density at 1.8 — HTML island allowed; SPA not. **Reopen after 1.8/1.9** if Related evidence or Autobiography is unusable even with an island. Options then: more islands vs extract a local API + one heavy surface (Review/Reading) vs a host change. SPA remains post-2.0 unless this question is explicitly reopened.
9. Conflicts — show both; supersede, don’t erase.
10. If users dump notebook scans as “photos,” offer **promote photo → notebook page** rather than collapsing models.
11. **Local API / IPC before a second UI?** UI and CLI call services in-process today. A SPA, Tauri, or other out-of-process client needs a contract (notebook/corpus listing, page read/update, job start/stop/progress, analysis health, settings). Default: **no API** until a host change is decided. If extracted, UI and CLI should share it; do not invent OCR/persistence rules in the client.
12. **If a second UI is warranted, which host?** Local web SPA (optional Tauri/Electron shell) vs in-process desktop (Qt/PySide) vs another Python web stack. Gradio is not a workbench replacement. Drivers: Docker `transcribe-web` needs a web client; Qt-only splits desktop vs container; NiceGUI/Flet/Reflex are unlikely to beat Streamlit enough to justify a rewrite. TranscriptX stays Streamlit — a Transcribe host change diverges presentation unless both later share a frontend programme.
13. **Strangler vs cutover.** If migrating, phase by user pain (Review → Reading/page viewer → Library → Transcribe/Analyse launchers + progress → analysis consume → Settings last). Keep Streamlit for Settings/Diagnostics until parity. Do not dual-run two full GUIs without freezing Streamlit feature scope. Full parity is multi-year, not a release row.
14. **Docker `transcribe-web` vs desktop-only.** Streamlit-in-container is the supported web surface. A Qt-only Review tool is a slice, not a replacement, unless a web client exists for Compose.
15. **Host-agnostic vs Streamlit accident.** Portable: PageSpec IA and gating, `interface-menus`, action IDs, workspace settings, tagging kernel, review alignment / composite / places / analysis display helpers. Not portable: scattered `st.session_state` keys, CSS `:has()` cover overlays, iframe parent-document hotkeys, Altair/`st.map` wiring. A second UI must re-specify navigation state (today: `ui_mode`, `root`, page-viewer overlay, review buffers) — there is no central state object.
16. **Are Review/Reading JS islands enough through 2.0?** Prefer islands (lightbox, shortcuts, Related evidence density) over a host change until 1.8 evidence. Click-to-fullscreen is already a **Now** candidate (Streamlit has no API; custom JS safekeeping in this file). Reopen 8 + 16 together if islands accumulate into an unofficial SPA.

---

## Later — Architecture follow-ups from evidence review — [?] candidates

Not on the **0.9.0 / U2** path. Do not schedule these while first-run operability and I5–I6 remain the cut. Evidence, blast radius, and “do not replace JSON-on-disk / add an event bus / split CLI vs UI services” live in [architecture_from_evidence.md](reviews/architecture_from_evidence.md) (2026-09-03).

**Already done from that review (do not re-open as new work):** L1 CLI `transcribe run` exits 1 on `circuit_open` (job record stays `completed`); cancel / “Completed with gaps” chrome; detection `reconcile_interrupted` no-ops while the OCR **or** analysis lock is held; snapshot mappers in `ui/progress_snapshots.py`. Do **not** add a `completed_partial` job status without a schema and test plan — coordinators keep `completed` + `circuit_open`.

| ID | Outcome | Review | Notes |
|----|---------|--------|-------|
| **L2** | `ProjectService.load` is a read by default; reconcile interrupted attempts is an explicit reopen path | P2 #3, L2 **partial** | Detection already skips reconcile when either long lock is held. Changing the load default touches every caller of `load()`. |
| **L3** | Names / people detector consumes **published** NER only — no nested `AnalysisRunner.run_module("ner")` | P2 #4, L3 | Keeps Detect from running Analyse as a side effect. |
| **L4** | One schema registry for every written `format` (including job-record, settings, profiles, interface-menus) | P2 #7, L4 | `persistence.schema.SUPPORTED` is incomplete today. |
| **P1 leftover** | Cleanup LLM failure must not seal cleanup into the OCR skip fingerprint while the page keeps raw text | P1 #2 | Skip/resume can assume cleanup that never applied. |
| **P2 split** | Split `ProjectService` along SoT I/O vs review / dates / declutter / reconcile | P2 #6 | High blast radius; not a Review workbench rewrite and not a database. |
| **Detect cancel** | Detect can be stopped like OCR/Analyse | P3 | Detect is request-synchronous today; Analyse+detect lock behaviour already tightened. |
| **Confirms** | Confirm before Reset whole workspace settings and Re-apply visual declutter | P3 | Reset already copies `settings.reset.{stamp}.json`; declutter margin loss is documented. |
| **Cover Open** | Library cover Open is a visible control | P3 | Opacity-0 overlay today. |
| **Dirty leave** | Review dirty-leave does not require a second Prev/Next to discard | P3 | `rw_force_leave`. |
| **Auto-tag** | Re-running auto-tag does not re-apply slugs the user removed | P3 | Current contract: additive re-add; turn the checkbox off to stop. |
| **Chart palettes** | Config chart-colour defaults do not import `transcribe.ui` | residual | Streamlit no longer loads on `ProjectService.create`; `ChartColorsConfig` still imports `ui.chart_colors`. |

Leave `effective_text()` as the integration bus, session-only routing, and on-disk `completed` + `circuit_open` unless a later review reopens them with evidence.

---

## Later candidates — uncommitted — [?]

Worth recording without scheduling. Rows pulled into [After 1.0](#after-10--notebook-anchored-autobiography-workbench----planned) are marked.

- Cross-notebook links / related pages — **scheduled 1.1** (notebook date windows; computed, not a graph)
- **Context import candidates (post-1.6)** — Spotify/Last.fm exports, Amazon purchase history, browser/search history, Google Maps Timeline, calendar exports — [Future context import candidates](#future-context-import-candidates--uncommitted) in After 1.0
- Corpus-level Analyse / search (cross-notebook products — **not** Bulk Analyse orchestration above). **2.0 reconstruction** is retrieved-evidence QA, not a cross-notebook Analyse runner; a corpus Analyse product remains uncommitted
- Bookmarks / favourites
- Annotations distinct from OCR corrections
- Batch metadata editing
- Image-only / non-OCR page handling
- **Detection fine-tune export** — scheduled as candidate section above (approved/rejected Detect labels → external training datasets)
- **Custom / native UI host** (SPA, Tauri, Qt, …) — uncommitted; not a 1.x track. Working default is Streamlit through 2.0. Reopen only with 1.8–1.9 evidence via [UI host](#ui-host-working-default--reopen-with-evidence); do not schedule a rewrite from this list.

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

- OCR pipeline — import, vision OCR, optional second-pass cleanup; **multipass compare / prefer / promote / composite / fine-tune export** (OCR lifecycle package — shipped); **detection fine-tune export** (candidate — extend export to approved/rejected Detect findings)
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
