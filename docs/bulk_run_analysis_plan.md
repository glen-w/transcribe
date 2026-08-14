Type: PRODUCT
Authority: Delivery plan for multi-notebook Analyse batch (GUI Target parity with Transcribe Batch). Does not define runtime schemas — those land in a new CONTRACT when implementation starts. Companion to [ROADMAP.md](ROADMAP.md) and the shipped OCR batch pattern ([contracts/ocr-batch-run.md](contracts/ocr-batch-run.md)).

# Bulk run analysis plan

**Status:** [x] shipped — GUI + durable workspace run for “same Analyse plan × N notebooks”, with the **same notebook selection modes** as bulk OCR.
**Thesis:** Transcribe already has single-notebook Analyse (`AnalysisCoordinator` + frozen `AnalysisRunPlan`) and multi-notebook OCR (`OcrBatchRun` + `BatchOcrCoordinator`). Users who batch-import and batch-OCR still re-run Analyse one notebook at a time. This plan closes that gap **without** inventing corpus-level / cross-notebook analysis.

```text
Import → Batch OCR → Bulk Analyse → stay on Analyse (View consume is per-notebook)
         (same selection UX)   (same plan × N projects)
```

---

## 1. Goals and non-goals

### Goals

1. **Target parity** — Analyse gets **This notebook | Batch**, matching Import / Transcribe.
2. **Same selection modes as bulk OCR** — radio: `pending` | `import_run` | `pick` (labels adapted for Analyse; see §3).
3. **One shared Analyse plan** — preset / custom modules / optional Ask question / text-model freeze, applied sequentially to each selected notebook.
4. **Durable workspace run** — resume / status / cancel-after-current-notebook, mirroring `OcrBatchRun`.
5. **Honest live progress** — shared progress panel with dual bars (notebooks + modules), current notebook/module labels, captions, recent logs, and post-run per-item summary — parity with batch OCR (§5.1).
6. **Robust offline tests** — coordinator, selection, progress snapshot mapping, UI contract, CLI, and acceptance coverage before claiming done (§11).
7. **Docs as ship criteria** — CONTRACT + public surfaces + user guide + known limitations + indexes updated in the same delivery that enables the GUI (§12).
8. **CLI parity (same PR or immediate follow-up)** — `bulk-analyse` mirrors `bulk-run` sources.

### Non-goals (explicit)

| Out of scope | Why |
|--------------|-----|
| Cross-notebook synthesis / corpus-level Analyse | ROADMAP “Later candidates”; this is N independent project runs |
| Parallel notebooks in one process | Same Ollama bottleneck rule as OCR batch |
| Auto-start Analyse after OCR / import | Keep handoffs opt-in CTAs only (like “Transcribe imported notebooks”) |
| Changing per-module publish / cache / health semantics | Reuse `AnalysisCoordinator` / `AnalysisRunner` as-is |
| Detect bulk | Detection stays View → Detect on the open notebook |
| Ask-as-batch-health | Ask remains ad-hoc; if included in a frozen plan it runs per notebook but still does not redefine aggregate batch health |

### Naming (avoid overload)

| Say | Do not say |
|-----|------------|
| **Bulk Analyse** / **Analyse → Batch** / `AnalysisBatchRun` | “Batch analysis” alone (already means multi-module on one notebook) |
| Outer unit = **notebook**; inner unit = **module** | Confusing “batch” levels without qualifier |

Today’s in-notebook multi-module run stays “Analyse batch” / `AnalysisRunPlan`. The new workspace record is **`AnalysisBatchRun`**.

---

## 2. Product shape (GUI)

### 2.1 Shell / routing

| Today | Change |
|-------|--------|
| `is_open_notebook_workflow` treats Analyse as requiring a sidebar notebook | Exclude **Analyse** like Import/Transcribe so Batch can open without selection |
| `app.py` Analyse path always loads one project | Host Target switcher; **This notebook** is the preset launcher; **Batch** renders launch + progress only. Consume surfaces are View pages, not Analyse tabs |
| `get_analysis_coordinator(project_root)` | Keep for This notebook; add `@st.cache_resource` `get_batch_analysis_coordinator` for workspace batch |

**View consume pages and Detect** remain notebook-scoped. Batch mode is a launcher + progress surface only. After a batch finishes, **stay on Analyse**; Library opens the gallery, and per-item Open goes to Overview if published, else Reading.

### 2.2 Target switcher

Reuse `targets.py` pattern (or parallel Analyse keys):

| Key | Role |
|-----|------|
| `analyse_target` / `pending_analyse_target` | This notebook \| Batch |
| `analyse_batch_source` | `pending` \| `import_run` \| `pick` |
| `analyse_batch_import_run_id` | Seeded ImportRun |
| `analyse_batch_notebook_ids` | Seeded id list |

Cross-page CTAs (optional in same slice or follow-up):

- Post-import: **Analyse imported notebooks** (after or beside Transcribe CTA) → Analyse → Batch, source=`import_run`.
- Post–batch OCR: **Analyse transcribed notebooks** → Analyse → Batch, source=`pick` or analysis-aware `pending`, seeded with that OcrBatchRun’s notebook ids.

### 2.3 Launch chrome (Batch)

Keep the existing preset form (Quick / Balanced / Thorough / Custom, optional Ask, Review modules, text-model picker, remote-host ack). Below it:

1. Notebook source radio (**same three modes as Transcribe Batch**).
2. Caption with selection counts.
3. Recent `AnalysisBatchRun` expander + Resume.
4. Primary **Start batch analysis**.
5. Live progress / Stop / Retry failed / Change settings — **must** follow §5.1 (not a caption-only stub).

No confirmation modal beyond existing remote-host ack and validation (≥1 notebook; plan hash bind; text model when LLM modules selected).

---

## 3. Notebook selection (parity with bulk OCR)

Transcribe Batch today (`run_transcribe._render_batch_launch` + `services/batch_ocr.py`):

| Source | OCR meaning |
|--------|-------------|
| `pending` | `pages_pending > 0` (no succeeded result, including failed) |
| `import_run` | Committed notebooks from an ImportRun |
| `pick` | Manual multiselect |

**Bulk Analyse uses the same three sources.** Selection helpers should be generalized out of OCR-only code so both surfaces share discovery / import-run / pick, with **domain filters** layered on top.

### 3.1 Candidate model

Introduce a shared `NotebookCandidate` (or keep `BatchCandidate` and extend) discovered via `discover_project_roots`:

| Field | Notes |
|-------|-------|
| `notebook_id`, `title`, `root`, `managed_relpath` | Same as OCR |
| OCR counts | `pages_total`, `pages_pending`, `pages_failed` (reuse `page_counts`) |
| Analyse counts | `pages_with_text`, plus optional health snapshot for captions |

### 3.2 Source semantics for Analyse

| Source | Analyse meaning | Caption / label |
|--------|-----------------|-----------------|
| `pending` | Notebooks that **need Analyse work**: ≥1 page with effective text **and** aggregate `AnalysisHealth` in `{missing, stale, failed, interrupted, degraded}` **or** no published modules yet | **Notebooks needing analysis** (not “pending pages”) |
| `import_run` | Same ImportRun committed ids as OCR; still list notebooks with zero text (they will `skipped` at run time) | **From an import run** |
| `pick` | Manual multiselect over all discoverable notebooks | Label: `{title} ({pages_with_text} with text · {health})` |

**Hard rule:** Do not silently redefine OCR’s `pending` filter. Analyse `pending` is analysis-aware; OCR `pending` stays page-transcription-aware. Shared code = discovery + `select_by_ids` + `select_from_import_run`; filters stay domain-specific (`select_pending` vs `select_needing_analysis`).

### 3.3 Skip / fail rules at execution

| Condition | Item state |
|-----------|------------|
| Zero pages with effective text | `skipped` (insufficient_data class; do not fail the whole batch) |
| Per-notebook analysis lock conflict / unexpected error | `failed` + message; continue to next notebook |
| Cancel requested | Finish/cancel current notebook per existing coordinator rules; remaining items `cancelled` |
| Empty selection at launch | UI/CLI validation error (same as OCR) |

Fingerprint / cache skip inside a notebook remains `AnalysisRunner` behavior — bulk does not add a second skip layer beyond empty-text skip.

---

## 4. Durable contract (`AnalysisBatchRun`)

New CONTRACT: `docs/contracts/analysis-batch-run.md` (implementation PR). Pattern-match [ocr-batch-run.md](contracts/ocr-batch-run.md).

### Storage

- Directory: `{TRANSCRIBE_DATA_DIR}/corpus/analysis-runs/`
- File: `{analysis_batch_id}.json`
- Format: `transcribe.analysis-batch-run`
- `schema_version`: `1`

### Frozen outer plan (workspace)

Freeze once at `create_run` (not per notebook content):

| Field | Rule |
|-------|------|
| `analysis_batch_id` | UUID; filename stem |
| `status` | `pending` \| `running` \| `completed` \| `partial` \| `failed` \| `cancelled` |
| `preset_*` / module list / question | Same identity fields as `AnalysisRunPlan` template |
| `effective_config` + `config_fingerprint` | Snapshot at create |
| `text_model` | Frozen when any LLM module included |
| `plan_template_hash` | Hash over execution-significant template fields (**exclude** per-notebook `project_id` / `run_id`) |
| `import_run_id` | Optional seed |
| `items[]` | Ordered unique `notebook_id`s |

Per-item fields mirror OCR items (`state`, `error_message`, plus module counters: `modules_total/completed/failed/skipped`, optional `inner_run_id` pointing at that project’s `analysis/runs/<run_id>.json`).

### Execution

1. Resolve notebook root (corpus index, else project-folder scan) — reuse OCR resolvers.
2. For each item: open `ProjectService`, `build_analysis_run_plan(...)` **for that project** from the frozen template (new `run_id`, that `project_id`, same modules/config/model/preset/question), verify hash bind, `AnalysisCoordinator.run_blocking(plan)` (or equivalent).
3. One notebook at a time; per-project `.transcribe.analysis.lock` still applies.
4. Cancel: request cancel on the active inner coordinator; do not start remaining notebooks.
5. Resume: non-terminal items; reset a crash-`running` item to `pending` and re-enter (inner cache hits skip fresh modules).

**Authority split:** Workspace `AnalysisBatchRun` owns multi-notebook orchestration only. Per-module `published.json` + project `analysis/runs/` remain analysis authority (unchanged).

---

## 5. Service / UI implementation map

| Layer | Path (proposed) | Role |
|-------|-----------------|------|
| Shared candidates | `services/batch_notebooks.py` (extract from `batch_ocr.py`) | `list_candidates`, `select_by_ids`, `select_from_import_run`, resolvers |
| OCR filter | `batch_ocr.select_pending` | Thin wrapper on shared candidates |
| Analyse filter | `batch_analysis.select_needing_analysis` | Health + text gate |
| Coordinator | `services/batch_analysis.py` → `BatchAnalysisCoordinator` | `create_run` / `start` / `run_blocking` / `resume` / `request_cancel` / `get_progress` |
| Persistence | `corpus/analysis_run.py` + `CorpusPaths.analysis_runs_dir` | Store + finalize status helper |
| UI | `ui/run_analysis.py` (+ small `targets.py` keys) | Target switcher, batch launch/progress |
| App shell | `ui/app.py`, `ui/shell.py` | Analyse without forced notebook when Batch |
| Progress | `ui/components/progress_panel.py` | Reuse as-is; dual bars via snapshot detail_* fields (§5.1) |
| CLI | `__main__.py` | `bulk-analyse pending\|import-run\|notebooks\|status\|resume` |
| Factory | `build_batch_analysis_coordinator` | Streamlit `@st.cache_resource` |

### 5.1 GUI progress (hard requirement — parity with batch OCR)

Batch Analyse **must not** ship with spinner-only or caption-only feedback. Mirror Transcribe Batch (`_render_batch_progress` + `_batch_progress_to_snapshot`):

#### While running

| UI element | Behavior |
|------------|----------|
| Live fragment poll | `@st.fragment(run_every≈2s)` while status is `running` (same cadence as batch OCR) |
| Phase banner | `st.info` / success / error via `render_progress_panel` (`running_pipeline`, `completed`, `partial`, `failed`, `cancelled`) |
| Current notebook | `current_item` = title or `notebook_id` (readable, not only UUID) |
| Current module | `current_module` = inner `AnalysisProgress.current_module_id`; `current_label="Current notebook"` for outer, module shown via existing `current_module` / detail line |
| Outer progress bar | `unit_label="notebooks"` — `completed+skipped+failed / total` with skipped/failed suffixes |
| Inner progress bar | `detail_unit="modules"` — map inner completed/failed/skipped/total; `detail_current` = current module id (panel already supports nested bar; generalize “Current page” copy to honor `detail_unit` if needed) |
| Latest event caption | Forward inner `message` (e.g. “Running ner (3/12)…”) |
| Recent logs expander | Append notebook-start / module-finish / skip / fail lines (cap like OCR panel) |
| Stop control | **Stop after current notebook** → `request_cancel()`; caption explains remaining notebooks will not start |

Hide the preset/selection form while a batch is live or a post-run summary is showing (same early-return pattern as Transcribe Batch).

#### Progress snapshot contract

`BatchAnalysisProgress` → `ProgressSnapshot` mapper (pure function, unit-tested):

```text
status, phase
current_item          ← notebook title / id
completed, skipped, failed, total, pct   ← notebook counters
current_module        ← optional mirror of detail_current for panel chrome
detail_unit="modules"
detail_completed / detail_failed / detail_skipped / detail_total
detail_current        ← current_module_id
latest_event, recent_logs, error
```

Coordinator must refresh nested module counters on every inner progress tick (not only when a notebook finishes).

#### Post-run summary

When status enters `{completed, partial, failed, cancelled}`:

- Keep final dual-bar snapshot visible (not cleared on first idle poll).
- **Next** actions: View · Retry failed · Change settings (Retry rebuilds a run from failed item ids).
- Per-item list: `title · state · modules_completed/total · failed/skipped · error_message`.
- Optional: open last completed notebook in This notebook Target.

#### Non-negotiable UX gate

A2 is **not** mergeable if Batch Analyse lacks: outer notebook bar, inner module bar (when `detail_total > 0`), current notebook label, stop control, and post-run item summary. Caption-only “Running…” is a defect.

### Conflict rules

- At most one workspace `AnalysisBatchRun` thread in-process (`JobConflictError` if another bulk Analyse is live).
- Do not start bulk Analyse while a This-notebook Analyse is running on a selected notebook (or document: inner lock fails that item → `failed`, continue). Prefer **preflight skip/fail** listing locked notebooks in the launch error when easy.
- OCR job locks are independent; do not wait on OCR locks during Analyse (existing rule).

---

## 6. Delivery slices

Implement in small PRs; each must stay rebase-clean vs `main` and keep the default offline suite green. **No slice is done without its test + docs bullets.**

### A0 — Plan + pointers — [x] (this doc)

- This PRODUCT plan (including §5.1 / §11 / §12)
- ROADMAP / index pointers

### A1 — Persistence + coordinator (headless)

- `AnalysisBatchRun` contract + store + schema registration
- `BatchAnalysisCoordinator` sequential execution + nested progress ticks
- Extract shared notebook candidate helpers
- Offline tests from §11.1–§11.2 (coordinator + selection + progress mapper)
- CONTRACT linked from `CONTRACT_INDEX.md` / `TERMS.md`

### A2 — GUI Target + selection + **live progress**

- Analyse Target switcher; Batch without sidebar notebook
- Same three selection modes + seed keys
- Full §5.1 progress panel wiring (fragment poll, dual bars, stop, post-run)
- UI contract tests from §11.3
- Smoke on port 8510 when practical (not a substitute for offline contract tests)

### A3 — Handoffs + CLI + docs

- Optional post-import / post–batch-OCR CTAs
- CLI `bulk-analyse …` + §11.4 tests
- Full §12 documentation checklist
- ROADMAP A1–A3 rows marked done

**Suggested merge order:** A1 → A2 → A3. A2 must not invent a second runner. **A2 blocked on §5.1 UX gate.**

---

## 7. Acceptance criteria

### Behavior

- [ ] Analyse → Batch can run the same preset plan across ≥2 notebooks without opening each manually.
- [ ] Selection modes are the same three as Transcribe Batch (`pending` / `import_run` / `pick`); Analyse `pending` uses analysis-need semantics (§3.2).
- [ ] Empty-text notebooks are `skipped`; one notebook failure does not abort siblings.
- [ ] Cancel stops after the current notebook’s cancel semantics; remaining items `cancelled`.
- [ ] Resume continues non-terminal items; published modules survive crash/reopen (existing analysis rules).
- [ ] Per-notebook health / plan_hash semantics unchanged for each notebook.

### Progress GUI (§5.1)

- [ ] Live dual progress bars (notebooks + modules) with current notebook and current module labels.
- [ ] Phase banner + latest-event caption + recent-logs expander update while running.
- [ ] Stop control cancels remaining notebooks after the current one.
- [ ] Post-run summary lists each notebook’s outcome; Retry failed / Change settings work.

### Tests & docs

- [x] Offline suite covers §11 matrix; no live Ollama required in default CI.
- [x] §12 docs checklist complete; ROADMAP marks A1–A3 done.
---

## 8. Explicit risks / decisions

| Topic | Decision |
|-------|----------|
| Plan hash per notebook | Rebuild `AnalysisRunPlan` per project from frozen **template**; each inner plan has its own `run_id` / `project_id` / `plan_hash`. Template hash is recorded on the workspace run for audit. |
| Custom Ask question | Allowed on Batch; same question text applied to every notebook when `llm_custom_qa` is in the plan. |
| Force re-run | No OCR-style `force` flag. Users rely on stale health + cache identity; optional later “recompute even if fresh” is out of scope. |
| Multipass analogue | None — Analyse has presets, not vision multipass. |
| Relationship to ROADMAP “Corpus-level Analyse” | This feature is **not** that candidate. Corpus-level means cross-notebook products; Bulk Analyse is orchestration only. |
| Progress panel copy | Prefer generalizing `detail_current` label (“Current module” when `detail_unit=modules`) over hard-coding “Current page” for Analyse Batch. |

---

## 9. Key references

| Artifact | Role |
|----------|------|
| [contracts/ocr-batch-run.md](contracts/ocr-batch-run.md) | Pattern to clone for workspace batch runs |
| [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) | Inner plan / publish / lock authority |
| `src/transcribe/services/batch_ocr.py` | Coordinator + selection template |
| `src/transcribe/ui/run_transcribe.py` | Target + `_render_batch_progress` template |
| `src/transcribe/ui/components/progress_panel.py` | Shared dual-bar panel |
| `src/transcribe/ui/run_analysis.py` | Preset form + single-notebook launch |
| `src/transcribe/analysis/coordinator.py` | Inner engine to call per notebook |
| `tests/unit/test_batch_ocr.py` · `tests/acceptance/corpus/test_bulk_ocr.py` · `tests/unit/test_progress_reporting.py` | Test patterns to mirror |

---

## 10. Exit gate

Bulk run analysis is **done** when:

1. A1–A3 acceptance boxes (§7) are checked.
2. §5.1 progress UX gate and §11 test matrix are green offline.
3. §12 docs checklist is complete and `CONTRACT_INDEX` points at `analysis-batch-run`.
4. GUI Batch selection matches Transcribe’s three modes.
5. Ordinary users can Analyse a freshly imported/OCR’d set **while watching notebook + module progress**, without per-notebook babysitting — and without claiming cross-notebook Analyse.

---

## 11. Test matrix (offline-first)

Mirror OCR bulk coverage. Default suite stays offline (fake / no Ollama). Live probes remain optional and environmental.

### 11.1 Unit — coordinator & store (`tests/unit/test_batch_analysis.py`)

| Case | Assert |
|------|--------|
| Two notebooks complete | Both items `completed`; workspace status `completed`; each has `inner_run_id` / published modules as expected for preset |
| Empty-text skip | Item `skipped`; siblings still run; status not `failed` solely due to skips |
| One notebook fails | That item `failed` + message; next notebook still runs; finalize `partial` |
| Cancel mid-batch | Current notebook respects inner cancel; remaining items `cancelled`; no new notebooks started |
| Resume | Non-terminal items continue; completed items not re-executed from scratch (cache hits OK) |
| Job conflict | Second `start` while running raises `JobConflictError` |
| Round-trip persist | Store load/save preserves template hash, preset fields, item counters |
| `finalize_*_status` | `completed` / `partial` / `failed` / `cancelled` matrix |

### 11.2 Unit — selection & progress mapping

| Case | Assert |
|------|--------|
| `select_needing_analysis` | Includes missing/stale/failed/interrupted/degraded with text; excludes healthy-with-text and empty-text |
| `select_from_import_run` / `select_by_ids` | Same ordering/missing-id errors as OCR helpers |
| OCR `select_pending` untouched | Regression: still page-pending semantics after shared extract |
| `_batch_analysis_progress_to_snapshot` | Notebook totals → outer bar; module totals → `detail_*`; titles in `current_item`; pct sane |

Extend `tests/unit/test_progress_reporting.py` (or sibling) the way `test_batch_ocr_progress_names_notebook_and_page` covers OCR.

### 11.3 UI contract (`tests/unit/test_analyse_ui_contract.py` + import/transcribe contract style)

| Case | Assert |
|------|--------|
| Target keys / modes | Analyse exposes This notebook \| Batch; Batch does not require open notebook in shell helper |
| Selection source labels | Radio options include needing-analysis / import run / pick |
| Progress wiring present | Source references `render_progress_panel`, `unit_label="notebooks"`, detail modules, stop key |
| Schema registered | `SUPPORTED["transcribe.analysis-batch-run"] == 1` and CONTRACT file exists |
| No second runner | Batch path calls batch coordinator; does not add per-tab module runners |

### 11.4 Acceptance / CLI (`tests/acceptance/…` or corpus-adjacent)

| Case | Assert |
|------|--------|
| Three-notebook offline bulk | Preset plan across 3 projects completes/partial correctly |
| CLI `bulk-analyse pending\|notebooks\|status\|resume` | Wired in `__main__`; offline happy path like `test_bulk_ocr.py` |
| Import-run seed | Batch from ImportRun committed ids |

### 11.5 CI gate

- A1 merge: §11.1–§11.2 green.
- A2 merge: §11.3 green + §5.1 checklist manually verified in smoke when feasible.
- A3 merge: §11.4 + §12 green.
- Do not mark ROADMAP done if only happy-path coordinator tests exist.

---

## 12. Documentation checklist (ship with A1–A3)

| Doc | Update |
|-----|--------|
| `docs/contracts/analysis-batch-run.md` | New CONTRACT (A1) — lifecycle, fields, cancel/resume, non-goals |
| `docs/CONTRACT_INDEX.md` | Point at live CONTRACT (replace plan pointer) |
| `docs/TERMS.md` | `AnalysisBatchRun` → CONTRACT link |
| `docs/ARCHITECTURE.md` | Workspace bulk Analyse alongside OcrBatchRun |
| `docs/public_surfaces.md` | Analyse → Batch Target; CLI `bulk-analyse`; progress note |
| `docs/user_guide.md` | How to bulk Analyse after import/OCR; what the bars mean |
| `docs/known_limitations.md` | Sequential notebooks; empty-text skip; no force; Ask on batch; not corpus-level Analyse |
| `docs/ROADMAP.md` | Tick A1–A3 when landed |
| `README.md` (if entry surfaces listed) | One-line link if CLI/UI tables mention bulk OCR today |

**Copy rule:** Describe **notebook bar** + **module bar** in user-facing docs the same way batch OCR describes notebooks + pages. Do not document a progress-less “fire and forget” Batch.
