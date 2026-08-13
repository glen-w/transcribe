Type: PRODUCT
Authority: Delivery plan for multi-notebook Analyse batch (GUI Target parity with Transcribe Batch). Does not define runtime schemas — those land in a new CONTRACT when implementation starts. Companion to [ROADMAP.md](ROADMAP.md) and the shipped OCR batch pattern ([contracts/ocr-batch-run.md](contracts/ocr-batch-run.md)).

# Bulk run analysis plan

**Status:** [ ] planned — GUI + durable workspace run for “same Analyse plan × N notebooks”, with the **same notebook selection modes** as bulk OCR.

**Thesis:** Transcribe already has single-notebook Analyse (`AnalysisCoordinator` + frozen `AnalysisRunPlan`) and multi-notebook OCR (`OcrBatchRun` + `BatchOcrCoordinator`). Users who batch-import and batch-OCR still re-run Analyse one notebook at a time. This plan closes that gap **without** inventing corpus-level / cross-notebook analysis.

```text
Import → Batch OCR → Bulk Analyse → per-notebook Published results
         (same selection UX)   (same plan × N projects)
```

---

## 1. Goals and non-goals

### Goals

1. **Target parity** — Analyse → Run Analysis gets **This notebook | Batch**, matching Import / Transcribe.
2. **Same selection modes as bulk OCR** — radio: `pending` | `import_run` | `pick` (labels adapted for Analyse; see §3).
3. **One shared Analyse plan** — preset / custom modules / optional Ask question / text-model freeze, applied sequentially to each selected notebook.
4. **Durable workspace run** — resume / status / cancel-after-current-notebook, mirroring `OcrBatchRun`.
5. **Honest progress** — shared progress panel with notebook as outer unit and module as nested detail.
6. **CLI parity (same PR or immediate follow-up)** — `bulk-analyse` mirrors `bulk-run` sources.

### Non-goals (explicit)

| Out of scope | Why |
|--------------|-----|
| Cross-notebook synthesis / corpus-level Analyse | ROADMAP “Later candidates”; this is N independent project runs |
| Parallel notebooks in one process | Same Ollama bottleneck rule as OCR batch |
| Auto-start Analyse after OCR / import | Keep handoffs opt-in CTAs only (like “Transcribe imported notebooks”) |
| Changing per-module publish / cache / health semantics | Reuse `AnalysisCoordinator` / `AnalysisRunner` as-is |
| Detect bulk | Detection stays Analyse → Detect on the open notebook |
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
| `app.py` Analyse path always loads one project | Host Target switcher; **This notebook** keeps today’s tabs; **Batch** renders launch + progress only (no Published / Detect tabs) |
| `get_analysis_coordinator(project_root)` | Keep for This notebook; add `@st.cache_resource` `get_batch_analysis_coordinator` for workspace batch |

**Published results / Detect** remain notebook-scoped. Batch mode is a launcher + progress surface only. After a batch finishes, offer “Open notebook” / jump to This notebook for the last completed item (same spirit as Transcribe post-run links).

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
5. Progress / Stop / Retry failed / Change settings — mirror batch OCR.

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
| Progress | `ui/components/progress_panel.py` | `unit_label="notebooks"`; nest current module |
| CLI | `__main__.py` | `bulk-analyse pending\|import-run\|notebooks\|status\|resume` |
| Factory | `build_batch_analysis_coordinator` | Streamlit `@st.cache_resource` |

### Progress mapping

Outer `BatchAnalysisProgress`: notebook totals + `current_item` + nested module fields from inner `AnalysisProgress` (analogous to OCR’s nested page fields).

### Conflict rules

- At most one workspace `AnalysisBatchRun` thread in-process (`JobConflictError` if another bulk Analyse is live).
- Do not start bulk Analyse while a This-notebook Analyse is running on a selected notebook (or document: inner lock fails that item → `failed`, continue). Prefer **preflight skip/fail** listing locked notebooks in the launch error when easy.
- OCR job locks are independent; do not wait on OCR locks during Analyse (existing rule).

---

## 6. Delivery slices

Implement in small PRs; each must stay rebase-clean vs `main` and keep the default offline suite green.

### A0 — Plan + contract skeleton — [ ] (this doc)

- This PRODUCT plan
- ROADMAP / index pointers
- CONTRACT draft may land with A1 if preferred

### A1 — Persistence + coordinator (headless)

- `AnalysisBatchRun` contract + store
- `BatchAnalysisCoordinator` sequential execution
- Extract shared notebook candidate helpers
- Offline unit tests: create / skip empty / fail one continue / cancel remaining / resume / status finalize (`completed` vs `partial`)

### A2 — GUI Target + selection parity

- Analyse Target switcher
- Same three selection modes + seed keys
- Shared progress panel wiring
- Shell: Batch without sidebar notebook
- UI contract / smoke extensions as needed

### A3 — Handoffs + CLI + docs

- Optional post-import / post–batch-OCR CTAs
- CLI `bulk-analyse …`
- `public_surfaces.md`, `user_guide.md`, `known_limitations.md`, `TERMS.md`, `ARCHITECTURE.md`, `CONTRACT_INDEX.md`

**Suggested merge order:** A1 → A2 → A3. A2 must not invent a second runner.

---

## 7. Acceptance criteria

- [ ] Analyse → Batch can run the same preset plan across ≥2 notebooks without opening each manually.
- [ ] Selection modes are the same three as Transcribe Batch (`pending` / `import_run` / `pick`); Analyse `pending` uses analysis-need semantics (§3.2).
- [ ] Empty-text notebooks are `skipped`; one notebook failure does not abort siblings.
- [ ] Cancel stops after the current notebook’s cancel semantics; remaining items `cancelled`.
- [ ] Resume continues non-terminal items; published modules survive crash/reopen (existing analysis rules).
- [ ] Published results / health / plan_hash semantics unchanged for each notebook.
- [ ] Offline tests cover coordinator + selection filters; no live Ollama required in default suite.
- [ ] Docs list the surface; ROADMAP marks the slice done when A1–A3 land.

---

## 8. Explicit risks / decisions

| Topic | Decision |
|-------|----------|
| Plan hash per notebook | Rebuild `AnalysisRunPlan` per project from frozen **template**; each inner plan has its own `run_id` / `project_id` / `plan_hash`. Template hash is recorded on the workspace run for audit. |
| Custom Ask question | Allowed on Batch; same question text applied to every notebook when `llm_custom_qa` is in the plan. |
| Force re-run | No OCR-style `force` flag. Users rely on stale health + cache identity; optional later “recompute even if fresh” is out of scope. |
| Multipass analogue | None — Analyse has presets, not vision multipass. |
| Relationship to ROADMAP “Corpus-level Analyse” | This feature is **not** that candidate. Corpus-level means cross-notebook products; Bulk Analyse is orchestration only. |

---

## 9. Key references

| Artifact | Role |
|----------|------|
| [contracts/ocr-batch-run.md](contracts/ocr-batch-run.md) | Pattern to clone for workspace batch runs |
| [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) | Inner plan / publish / lock authority |
| `src/transcribe/services/batch_ocr.py` | Coordinator + selection template |
| `src/transcribe/ui/run_transcribe.py` | Target + batch launch UI template |
| `src/transcribe/ui/run_analysis.py` | Preset form + single-notebook launch |
| `src/transcribe/analysis/coordinator.py` | Inner engine to call per notebook |

---

## 10. Exit gate

Bulk run analysis is **done** when A1–A3 acceptance boxes are checked, the CONTRACT is linked from `CONTRACT_INDEX.md`, GUI Batch selection matches Transcribe’s three modes, and ordinary users can Analyse a freshly imported/OCR’d set without per-notebook babysitting — without claiming cross-notebook Analyse.
