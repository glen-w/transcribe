Type: PRODUCT
Authority: Usability-wave delivery plan (sequencing, tracks, acceptance criteria, exit gates). Does not define runtime schemas or contracts — those stay in CONTRACT docs. Companion to [ROADMAP.md](ROADMAP.md) and [product_hardening_plan.md](product_hardening_plan.md). Product language: **usability wave** (not “Wave 2” — Detection already uses that label).

# Usability wave plan

**Status:** [~] active — authoritative sequencing for the current product focus (ROADMAP **Now — Usability wave**). Hardening Phases 1–6 (**U0–U1**) are **done**; **U3** daily workbench is **done**; open track is **U2** (Home and Diagnostics shipped; sample notebook and first-run install docs remain); **U4** acceptance gate is **green** (Inbox polish may continue). Post-U3 deepen-in-place (OCR fail-fast circuits, Moments/chart jump → Reading, Overview/Mood corpus/period charts, Analyse launcher vs View consume split) is **shipped** — not a new wave track.

**Thesis:** Transcribe already has a complete core analysis set and durable OCR/analysis execution. Ordinary users still meet module-mechanics chrome, thin first-run guidance, and weak daily-workflow surfaces. This wave makes the workbench **trustworthy and usable end-to-end** — from install to export — without scheduling new analysis modules or deferred reinterpretations.

```text
Trust foundation          Daily workbench              Living corpus
(phases 3–6)       →      (onboard · review · read)  →  (inbox · bulk · search+)
```

Detection Prompt Hub / Detect UI is a **shipped parallel track** ([detection_wave2_plan.md](detection_wave2_plan.md) via [PR #6](https://github.com/glen-w/transcribe/pull/6)). It is not the centerpiece of this wave and must not steal naming (“Wave 2”).

---

## 1. Goals and non-goals

### Goals

1. **Trust without literacy** — Ordinary Analyse / Export workflows never require understanding module ids, cache identity, plan hashes, or capability enums.
2. **Honest health** — Every analysis surface answers the same question: “is this current and healthy?”
3. **Provenance** — Exports identify the notebook revision that produced them.
4. **First successful notebook** — A new user can install, pull a model, import, OCR, review, and export without reading contracts.
5. **Daily correction loop** — Review is a queue of work (dates, edits), not only a page browser.
6. **Living with notebooks** — Search, organisation, and reading improve on today’s project model; bulk inbox is supported after the corpus acceptance gate.

### Non-goals (explicit)

| Out of scope | Why |
|--------------|-----|
| New analysis modules / deferred reinterpretations / `ocr_quality` | [ROADMAP.md](ROADMAP.md) deferral stands |
| OpenCV preprocess pipelines | Pillow-only policy |
| Cloud OCR providers | Product boundary |
| Treating Detection Wave 2 as this wave’s definition of done | Parallel track (shipped) |
| Shipping supported bulk-import UI/CLI before the [corpus-integrity acceptance gate](contracts/corpus-integrity.md#acceptance-gate) | Contracts-first rule (gate now green; keep suite green) |
| Corpus-level Analyse / cross-notebook links / bookmarks | Later candidates — light **this vs corpus/period average** charts on Overview/Mood are shipped as product read-models over published metrics ([dev/analysis_visual_compare.md](dev/analysis_visual_compare.md)); not a corpus Analyse runner |

### Naming

| Say | Do not say |
|-----|------------|
| Usability wave, tracks **U0–U4** | Wave 2 (reserved for Detection drafts) |
| Core modules | Wave 1 (internal history only — [analysis_wave1_plan.md](analysis_wave1_plan.md)) |
| Product views / status strip | “Module console”, “payload dump” as primary UI |

---

## 2. Relationship to existing work

| Artifact | Role in this wave |
|----------|-------------------|
| [product_hardening_plan.md](product_hardening_plan.md) Phases **3–5** (#5/#6/#11/#12/#13) | **U0** — **done** on `main` ([PR #5](https://github.com/glen-w/transcribe/pull/5)) |
| Hardening Phase **6** (#7–9) | **U1** — **done** (product views, status strip, OCR Advanced) |
| [analysis_wave1_hardening_plan.md](analysis_wave1_hardening_plan.md) | Done infra; do not reopen as UI work |
| Detection wave 2 ([PR #6](https://github.com/glen-w/transcribe/pull/6)) | **Shipped** parallel track; coordinate only where Prompt Hub / page-viewer findings share chrome |
| Corpus contracts | **U4** acceptance gate green; bulk-import UI/CLI supported; Inbox polish may continue |

**Dependency rule:** U1 consumes `AnalysisHealth` / `content_revision` from U0 (both landed). Do not invent a second freshness model.

```mermaid
flowchart LR
  U0[U0 Trust foundation]
  U1[U1 Analyse product UX]
  U2[U2 First-run operability]
  U3[U3 Daily workbench]
  U4[U4 Corpus UX]
  U0 --> U1
  U0 --> U2
  U1 --> U3
  U2 --> U3
  U3 --> U4
```

U2 may start in parallel with U1 once U0 is merged (onboarding does not depend on Analyse chrome). U3 prefers U1’s status-strip patterns. U4 mechanics (acceptance gate) are done; Inbox polish may continue independently.

---

## 3. Track overview

| Track | Intent | Hardening IDs | Status |
|-------|--------|---------------|--------|
| **U0** — Trust foundation | Preset identity, plan-hash bind, content revision, shared health, export provenance | #5 #6 #11 #12 #13 | **[x] done** ([PR #5](https://github.com/glen-w/transcribe/pull/5)) |
| **U1** — Analyse product UX | Product views, shared status strip, OCR Advanced | #7 #8 #9 | **[x] done** |
| **U2** — First-run & operability | Install path, sample notebook, model guidance, doctor/diagnostics in UI | — | Planned |
| **U3** — Daily workbench | Review queues, reading mode, search/org polish (no bulk corpus activation); Archive activity bins + strip paging + page delete + model-info picker wiring | — | **[x] done** |
| **U4** — Corpus UX | Inbox / import recovery / bulk import; acceptance gate green | — | **[x] gate green** (polish open) |

---

## 4. U0 — Trust foundation

**Outcome:** Users can trust exactly what a preset will run; every analysis surface shares one health answer; exports cite a notebook revision.

**Status:** **[x] done** on `main` via [PR #5](https://github.com/glen-w/transcribe/pull/5) (`cursor/hardening-phases-3-5-4764`). Hardening checklist rows #5/#6/#11/#12/#13 are closed.

### Deliverables (landed — do not fork semantics)

| ID | Deliverable | Contract authority |
|----|-------------|-------------------|
| #5 | Freeze `AnalysisRunPlan` + `plan_hash` at launch; start refuses mismatch; no live re-snapshot | [analysis-run-storage.md](contracts/analysis-run-storage.md) |
| #6 | Named presets `content_version` + policy fingerprint; Custom = module-list fingerprint | [workspace-settings.md](contracts/workspace-settings.md) |
| #11 | Hex `content_revision` over exportable page content | [project-on-disk.md](contracts/project-on-disk.md) |
| #12 | Derived `AnalysisHealth` shared across Overview / Themes / Mood / Moments / Summaries; Ask out of batch scope | [analysis-result.md](contracts/analysis-result.md) |
| #13 | Same `content_revision` on JSON, manifest, Markdown header, plaintext header | [notebook-export.md](contracts/notebook-export.md) |

### Acceptance

- Offline tests for plan-hash bind, preset version bumps, revision stability, health aggregate priority, export stamp coherence (landed with PR #5).
- ROADMAP hardening table marks Phases 3–5 `[x]`.
- Known limitations updated for health / plan_hash / preset versions / export stamps.
- **Does not** remove module-id banners or `st.json` dumps — that is U1.

### Key files

`src/transcribe/analysis/{plan,presets,coordinator,health}.py`, `domain/content_revision.py`, `services/export.py`, `ui/{run_analysis,analysis_health_view,app,settings_analysis}.py`, phase 3–5 tests, contracts listed above.

---

## 5. U1 — Analyse product UX (hardening Phase 6)

**Status:** **[x] done** on `main` (hardening exit gate + Phase 6 notes).

**Outcome:** Analyse and Transcribe surfaces read as **user tasks**, not module/OCR consoles. Builds on U0 health/revision.

**Later deepen-in-place (shipped, not a new U1 reopen):** Analyse is the **launcher only** (This notebook | Batch). Product read-models live under **View** (Reading, Overview, Themes, Mood, Moments, People, Summaries, Ask, Detect) and consume current `published.json`. Jump-to-page / page-series clicks open **Reading**, not Review. See [public_surfaces.md](public_surfaces.md).

Parse checklist parenthetical **#7–9** as three shippable items:

### #7 — Product views

Replace module-console chrome with task-shaped read-models.

| Surface | Primary content | Demote / hide from default path |
|---------|-----------------|----------------------------------|
| Overview | Counts, diversity, entities, theme chips, charts | Raw module ids as section titles; capability/`outcome=` banners; payload `st.json` |
| Themes | Topics, wordclouds, similarity narrative | Per-module JSON expanders |
| Mood & tone | Emotion / affect / hedging strips | Enum dumps |
| Moments | Salient quotes with jump-to-page | Internal module labels |
| Summaries | Highlights → summary → insights (and LLM when healthy) | Parent-cache literacy |
| Ask | Question + answer | Stale batch payloads; treat as ad-hoc (already) |
| Last run | Short product summary (“Balanced v3 · 12 modules · healthy”) | Per-module `outcome=` lists as default |

**Rules**

- Capability honesty stays, but in **product language** (“Needs a text model”, “Optional BERTopic not installed”, “Not enough text yet”) — not `unavailable_model` as first-class chrome.
- Power users may still open an **Advanced / technical details** expander per tab or once globally.
- Existing read-model helpers and `module_ui_groups` stay the composition layer; do not invent a second analysis runner.

### #8 — Status strip

One shared health strip (consume `render_aggregate_caption` / `AnalysisHealth` from U0):

- Placement: on View consume pages (and optionally in Workflow Analyse header while a run is active). Originally above Analyse result tabs; those tabs moved to View.
- Answers: revision short prefix · aggregate state · whether a run is active/interrupted.
- Per-tab duplicate freshness banners collapse into the strip; tab bodies show content or a single empty/unavailable state.
- Ask caption continues to state it does not update batch health.

### #9 — OCR Advanced

Transcribe (Run OCR) primary chrome:

1. Vision model
2. Start transcription
3. Optional one-line cleanup toggle (or clearly secondary)

Collapse under **Advanced**: workers, force re-OCR, cleanup mode/model detail, unverified-identity tips, capability dumps, remote-host acknowledgement (keep safety-critical acknowledgement visible or confirm-gated — never bury the privacy footgun without a confirm).

### Acceptance (U1 exit)

- [x] No ordinary Analyse path requires reading module ids or `st.json` to understand results.
- [x] One status strip is the sole default freshness/health answer across batch tabs.
- [x] Transcribe primary path is model + run (+ optional cleanup); power controls under Advanced.
- [x] Acceptance / UI contract tests: `tests/unit/test_analyse_ui_contract.py` (extend) asserts product copy for common unavailable states; smoke on port 8510.
- [x] [public_surfaces.md](public_surfaces.md) + [user_guide.md](user_guide.md) describe product views, not module consoles.
- [x] Hardening Phase 6 and ROADMAP hardening **exit gate** close when U0+U1 acceptance tests pass.

### Key files

`src/transcribe/ui/notebook_views.py`, `ui/app.py`, `ui/analysis_health_view.py`, `ui/run_analysis.py`, `ui/module_ui_groups.py`, docs above, Analyse UI contract tests.

---

## 6. U2 — First-run & operability

**Outcome:** A motivated non-expert reaches a first exported notebook without digging into contracts or Docker archaeology.

### U2.1 — Home (shipped; replaces the setup-wizard sketch)

This Home **replaces** the earlier U2.1 sketch (setup checklist + Open sample on empty Home). Sample notebook stays **U2.2**. Do not ship a wizard TranscriptX already removed.

| Step | Behavior |
|------|----------|
| Empty workspace | Home empty state: **Create notebook** + **Import** (at most two CTAs). No Open sample. |
| One-line health | Ollama reachable / not reachable, plus a vision-model count when discovery works |
| Non-empty Home | Cheap archive counts (notebooks / pages), bounded recent list (8) with action strips. Does **not** scan every `published.json` on load. |

No telemetric onboarding — local session / workspace only.

### U2.2 — Sample / demo notebook

- Ship a small fixture notebook (few pages of public-domain or synthetic handwriting scans **or** text-backed pages with placeholder images) under a documented path (e.g. `samples/demo-notebook/` or generated into projects on demand).
- One-click **Open sample** copies into `TRANSCRIBE_PROJECTS_DIR` via existing `init` + import services — not a second project format.
- Sample should be analysable offline for deterministic modules (so Analyse demos without LLM).

### U2.3 — Diagnostics in UI

**Status:** **[x] shipped** (System → Diagnostics).

| Capability | Behavior |
|------------|----------|
| Workspace doctor | Always available (`corpus-doctor`, optional deep hashing) |
| Notebook doctor | When a notebook is selected in View |
| Ollama | Same one-line reachability as Home |
| Recovery / paths | Short copy; Settings still explains inbox/export mounts |

Speaker-profile repair is out of scope.

### U2.4 — Docs & install path

- Tighten [runtime/installation.md](runtime/installation.md) / [runtime/docker.md](runtime/docker.md) into a **“first notebook in 15 minutes”** path linked from README empty-state.
- Document port **8510**, absolute `HOST_PROJECTS_DIR`, Linux `extra_hosts`, UID/GID once in the first-run doc — not scattered only in deep runtime notes.
- Surface [known_limitations.md](known_limitations.md) items that bite first run (encrypted PDF, large budgets, cleanup latency).

### Acceptance (U2)

- [x] Empty Home presents Create + Import (no sample wizard).
- [ ] Sample notebook path works offline for import → (optional OCR skip if pre-seeded text) → Analyse Quick → Export.
- [x] Doctor results visible in System → Diagnostics with workspace always / notebook when selected.
- [ ] README / user guide point at the first-run install path; no contract reading required for the happy path.

### Key files

`ui/home.py`, `ui/diagnostics.py`, `ui/shell.py`, `ui/settings_hub.py`, `services/doctor.py`, `samples/` (U2.2), README, `docs/runtime/*`, `docs/user_guide.md`.

---

## 7. U3 — Daily workbench

**Status:** **[x] done** — Review queue, Reading mode, Search period parity, org tag chips, model product copy.

**Outcome:** After first success, living with one or many notebooks feels deliberate: correct faster, read comfortably, find things, organise lightly — **without** activating bulk corpus contracts.

### U3.1 — Review as a work queue

Today Review opens the shared page viewer with thin empty states ([app.py](src/transcribe/ui/app.py) Review section; [page_viewer.py](src/transcribe/ui/page_viewer.py)).

| Add | Detail |
|-----|--------|
| Needs-attention filters | Unapproved suggested dates · pages with no text · failed OCR · (optional) edited-vs-raw |
| Batch date actions | Approve/ignore visible suggestions for N pages with clear feedback |
| Faster edit loop | Keep ←/→; emphasize save affordance; reduce hover-only destructive controls where practical |
| Honesty | Time-of-day still ignored until Future metadata ships; unapproved dates still timeline-indexed — call out in Review chrome |

### U3.2 — Reading mode

Distinct from Review (edit) and Analyse:

- Chronological page image + text pairing, distraction-free chrome, jump-by-date when dates exist.
- Reuse page viewer data path; presentation mode / route under **View → Reading** — no new on-disk format.
- Optional “continue reading” remembers last page in session or lightweight UI state (not a new contract).

### U3.3 — Search & Archive deepening (FTS, not corpus index)

Stay on rebuildable archive SQLite ([known_limitations.md](known_limitations.md)):

| Improvement | Notes |
|-------------|-------|
| Date range on Search | Archive already has period/range; bring coherent filters to Search |
| Clearer empty states | Distinguish “no notebooks” vs “no hits” vs “cache rebuilding” |
| Jump richness | Preserve highlight + open-in-viewer; raise discoverability of jump-to-page |
| Activity-bin filter | **Landed** on Archive: click a timeline bar to filter to that date bin |
| Strip paging | **Landed:** `ui.archive_notebooks_initial` (Settings → Configuration → Archive); `0` = show all |
| Not yet | Entity filters, saved searches — design stubs OK; implement only if cheap on current FTS |

Do **not** treat `archive.sqlite` as backup authority (unchanged support policy).

### U3.4 — Notebook organisation polish

On existing `title` / `tags` / `cover_page_id` (no schema expansion required for MVP):

- View: cover thumbnails, tag chips, sort clarity, rename/delete discoverability (menus already exist — tighten empty/error copy).
- **Page delete** in the page viewer **landed** (refuses last page / OCR job lock).
- Optional soft fields only if contract bump is justified: short description — otherwise skip.
- Collections / archive-state / user sort order → defer to post-U4 or later candidates unless a tiny settings-only sort lands without corpus index.

### U3.5 — Model & runtime management (product abstraction)

Transcribe panel already lists/refreshes models. Deepen:

- **Model information** expander follows the **live picker selection** on This-notebook / Compare forms (**landed**).
- Show availability, approximate size when known, last-used, verified vs unverified identity.
- Short recommendations for “first OCR” vs “quality” without hard-coding a single vendor promise.
- Text-model requirements for Analyse LLM modules explained in the same vocabulary as U1 product copy.

### Acceptance (U3)

- [x] Review offers at least one needs-attention filter and batch date approve/ignore.
- [x] Reading mode ships as a distinct presentation (documented in public surfaces).
- [x] Search gains date-range (or documented parity with Archive filters) and clearer empties.
- [x] Model panel explains verified identity and text-model needs in product language.
- [x] No dependency on corpus index / ImportRun activation.

### Key files

`ui/page_viewer.py`, `ui/archive_views.py`, `ui/shell.py`, `ui/app.py`, `services/archive.py`, `docs/public_surfaces.md`, `docs/user_guide.md`.

---

## 8. U4 — Corpus UX

**Outcome:** Human continuation of bulk import: **inbox / import recovery** as the corpus home screen. The [corpus-integrity acceptance gate](contracts/corpus-integrity.md#acceptance-gate) is **green**; bulk-import UI/CLI are **supported**. Inbox polish (richer outcomes taxonomy / `TRANSCRIBE_INBOX_DIR` scan) may continue.

### Hard gate (satisfied)

Supported bulk-import UI/CLI and inbox-as-product required:

1. Corpus index writers + locks ([notebook-corpus.md](contracts/notebook-corpus.md)) — **done**
2. ImportRun / plan / resume ([import-run.md](contracts/import-run.md)) — **done**
3. Duplicate policy on commit ([source-asset.md](contracts/source-asset.md)) — **done**
4. Corpus doctor checks + synthetic multi-notebook suite ([corpus-integrity.md](contracts/corpus-integrity.md)) — **done**

### Product UX (polish continuing)

| Surface | Intent |
|---------|--------|
| **Inbox** | Path-typed folder / parent-of-folders ImportPlan (shipped); optional later: scan `TRANSCRIBE_INBOX_DIR`; richer imported / failed / duplicated / needs-review taxonomy |
| **Recovery** | Resume interrupted ImportRun; explain skip_existing vs create_duplicate |
| **Corpus home** | Natural landing after a dump of scans — not only Workflow → Import uploader |
| **Doctor** | Deep corpus doctor from U2 diagnostics when index present |

### Acceptance (U4)

- [x] Acceptance gate green before any “supported” bulk/inbox claim in public surfaces.
- [ ] Inbox workflow shows outcomes for imported / failed / duplicated / needs-review (polish).
- [x] Crash-injection and idempotency covered by corpus suite; doctor recovers index.
- [x] ROADMAP corpus section moves from planned → done for the shipped slice; remaining lifecycle items (backup/restore productization, quality thumbs) stay candidates unless explicitly pulled in.

### Key files

`src/transcribe/corpus/*`, `services` import orchestration, `ui` inbox/recovery views, `settings_hub.py`, corpus contracts + tests under the integrity suite.

---

## 9. Parallel tracks (coordination only)

| Track | Coordination rule |
|-------|-------------------|
| Detection Wave 2 ([PR #6](https://github.com/glen-w/transcribe/pull/6); [detection_wave2_plan.md](detection_wave2_plan.md)) | **Shipped**; may share page-viewer finding captions and Prompt Hub settings; must not redefine Analyse health or block U1 |
| Visual declutter expansion | Remains ROADMAP preprocessing candidate; explicit re-apply is **shipped**; further ops not required for usability-wave exit |
| OCR lifecycle (multipass / prefer / promote / composite / fine-tune) | **Shipped** (W0–W5 / [PR #15](https://github.com/glen-w/transcribe/pull/15)); Review queue only needs honesty around suggested dates / force re-OCR |
| Quality thumbs / prompt management UI | Candidates; Detection Prompt Hub may absorb prompt browse — do not duplicate |

---

## 10. Wave exit gates

### Hardening close (U0 + U1)

Matches [ROADMAP.md](ROADMAP.md) hardening exit gate:

- Crash/reopen, stale detection, offline operation, export provenance, and normal Analyse workflows covered by acceptance tests.
- No ordinary user workflow requires understanding module/cache internals.

### Usability-wave close (U0–U3; U4 polish separately)

| Gate | Evidence |
|------|----------|
| Trust | Phases 3–6 checklist `[x]`; UI contract tests green |
| First-run | Sample path + checklist + doctor UI documented and smoke-tested |
| Daily loop | Review queue + reading mode + search filter parity smoke-tested |
| Honesty | known_limitations + public_surfaces updated |
| Corpus | Acceptance gate green; bulk/inbox claimed as supported in public surfaces |

U4 Inbox polish may remain open after the usability wave is declared done for U0–U3; say so in ROADMAP status.

---

## 11. Documentation updates required as tracks land

| Doc | When |
|-----|------|
| [product_hardening_plan.md](product_hardening_plan.md) | U0/U1 status rows |
| [ROADMAP.md](ROADMAP.md) | Point **Now** at this plan; tick phases; move U2/U3 into active sequencing |
| [public_surfaces.md](public_surfaces.md) | Product views, Reading mode, Diagnostics, Inbox (only when supported) |
| [user_guide.md](user_guide.md) | First-run, Review queue, Reading |
| [known_limitations.md](known_limitations.md) | Health, presets, export revision, Review date caveats |
| [TERMS.md](TERMS.md) | `plan_hash`, `content_revision`, `AnalysisHealth` (landed with U0) |
| [USER_INDEX.md](USER_INDEX.md) / [DEV_INDEX.md](DEV_INDEX.md) / [index.md](index.md) | Link this plan |

---

## 12. Implementation checklist (track-level)

### U0
- [x] Land PR #5 (or equivalent) on `main`
- [x] Mark hardening Phases 3–5 done in ROADMAP + product_hardening_plan
- [x] Confirm offline phase 3–5 tests on `main`

### U1
- [x] #8 Status strip wired as sole default health chrome
- [x] #7 Product views for Overview / Themes / Mood / Moments / Summaries / Ask / Last run
- [x] #9 OCR Advanced grouping with privacy acknowledgement preserved
- [x] UI contract tests + docs; mark Phase 6 + hardening exit gate

### U2
- [x] Home: Create / Import + one-line Ollama health (no sample wizard)
- [ ] Sample notebook one-click path
- [x] Diagnostics / doctor UI (workspace always; notebook when selected)
- [ ] First-run docs path from README

### U3
- [x] Review needs-attention + batch dates
- [x] Reading mode
- [x] Search/Archive filter parity + empties (Archive activity-bin filter included)
- [x] Archive strip paging (`ui.archive_notebooks_initial`) + page delete
- [x] Model management product copy (picker-wired Model information)

### U4
- [x] Corpus acceptance gate green
- [x] Inbox / import recovery UI + CLI as supported surfaces
- [x] Public docs claim bulk/inbox only after gate
- [ ] Richer Inbox outcomes taxonomy / optional inbox-dir scan (polish)

---

## 13. Success metrics (qualitative)

This product does not ship analytics telemetry. Use local evidence:

1. Maintainer can complete sample → Analyse Quick → Export with LLM offline and without opening `st.json`.
2. Fresh install checklist catches missing Ollama / vision model before a mysterious OCR hang.
3. Review batch-approves a notebook of suggested dates in one pass.
4. Export artifacts share one `content_revision` a user can cite.
5. Settings inbox / Import → Batch is a real recovery home (never a dead caption).
