# Review: architecture from evidence

**Date:** 2026-09-03  
**Scope:** CLI, Streamlit UI, services, persistence, tests — reconstructed from call paths, not from `ARCHITECTURE.md` as authority  
**Status:** Review landed. High-value low-risk follow-ups (CLI circuit exit, progress chrome, detection reconcile vs analysis lock) are implemented in the same change set. Remaining decoupling and P3 polish are recorded as unscheduled candidates on [ROADMAP.md — Architecture follow-ups](../ROADMAP.md#later--architecture-follow-ups-from-evidence-review--candidates).

Documentation was treated as a claim to check. This review does not redefine on-disk schemas.

## A. System model

Transcribe is a **single-user, local-first notebook workbench**. Authority is **directories of JSON and binaries**, not a database.

A notebook is a folder: `project.json` plus `results/{page_id}.json`, PNG renders, and original media. Workspace config, tag catalog, corpus index, backups, and an SQLite **search cache** sit under `TRANSCRIBE_DATA_DIR`.

CLI (`python -m transcribe`) and Streamlit (`transcribe-ui`, `127.0.0.1:8510`) share services. Live OCR and analysis jobs are in-process threads kept across reruns with `st.cache_resource`. Cross-process exclusion is flock on `.transcribe.job.lock` / `.transcribe.analysis.lock`. Mutations use a shorter mutation lock plus atomic temp-file replace.

Pipeline:

```
Import (optional visual declutter → stored PNG)
  → OCR (optional preprocess → Ollama vision → optional text-LLM cleanup)
  → PageResult.effective_text()  (edited_text else active attempt)
  → Review / dates / tags
  → Analysis modules and/or Detectors
  → Export / backup / Library search
```

Ollama is the only inference backend. There is no authentication. Remote Ollama is allowed after acknowledgement and sends page images off-box by design.

## B. FR list

Flags: **E** evidenced; **I** inferred; **A** ambiguous; **C** contradictory across surfaces.

### Core product

| ID | Outcome | Flag |
|----|---------|------|
| FR1 | Create a notebook and import JPEG/PNG/PDF into a path-contained project | E |
| FR2 | Local vision OCR with skip/resume, force, per-page isolation | E |
| FR3 | Multipass compare / prefer / composite / optional cleanup | E |
| FR4 | Review and correct text, dates, delete page, re-run OCR | E |
| FR5 | Analyse transcribed text; View read-models over published results | E |
| FR6 | Detectors (lexical, prompt, vision, names) with optional tags | E |
| FR7 | Export md/txt/html/epub/pdf/`transcribe.notebook`/fine-tune pack | E |
| FR8 | Library/search over corpus without treating SQLite as SoT | E |
| FR9 | People & Places from published NER; opt-in Nominatim | E |
| FR10 | CLI parity for init/import/run/detect/bulk/export/doctor/backup | E |

### Supporting

| ID | Outcome | Flag |
|----|---------|------|
| FR11 | Workspace settings, profiles, model discovery; notebook OCR wins listed keys | E |
| FR12 | Bulk import / OCR / analysis with durable run records and resume | E |
| FR13 | Full-workspace ZIP backup / replace-restore | E |
| FR14 | Doctor / corpus-doctor / Diagnostics | E |
| FR15 | Visual declutter, thumbnails, page ink/hue metrics from renders | E |
| FR16 | Tag catalog assign + corpus rewrite | E |
| FR17 | Builtin and custom prompts/detectors | E |

### Cross-cutting

| ID | Outcome | Flag |
|----|---------|------|
| FR18 | Crash must not silently delete authority; ingest journal; interrupted attempts when job not live | E |
| FR19 | Loopback Ollama default; remote requires acknowledgement | E |
| FR20 | At most one OCR job and one analysis job per notebook | E |
| FR21 | Unknown format/schema_version fail closed; no migrator | E / A |
| FR22 | Operator can tell whether a job ran and where it failed | E / C |
| FR23 | UI navigation preserves open notebook; no URL routing | E |

### Ambiguous / contradictory

1. **Job success after circuit skip (FR2/FR10/FR22, C).** `JobCoordinator` sets `status="completed"` when the timeout/`model_load` circuit opens. Tests pin that. UI warns via `circuit_open`. CLI `run` historically exited 0 on `completed` — automation treated a half-notebook as success. *(CLI exit fixed in this change set; on-disk `completed` + `circuit_open` unchanged.)*
2. **Cancel vs fail (FR22, C).** Coordinators use `cancelled`; UI snapshots historically mapped that to panel `failed`. *(Chrome mapping fixed in this change set.)*
3. **Detect is both a workflow and an Analyse step (FR5/FR6, A).** Different cancel, locks, and progress.
4. **Schema registry split (FR21, I).** `persistence.schema.SUPPORTED` omits settings, profiles, job-record, interface-menus.
5. **`ProjectService.load` is not a pure read (FR18, I).** Default `reconcile=True` demotes running OCR/analysis/detection attempts.
6. **Names detector depends on analysis NER (FR6, E).** `DetectionRunner._load_or_run_ner` may `run_module("ner")`.
7. **No deep links, no auth, no schema upgrade** — consistent with local v1; “durable corpus” has no `schema_version` 2 path.

## C. DP list (evidence)

| ID | Parameter | Evidence |
|----|-----------|----------|
| DP1 | Domain documents, `effective_text()`, fingerprints | `domain/models.py`, `domain/fingerprint.py`, `domain/validation.py` |
| DP2 | Path layout / containment | `paths.py:ProjectPaths`, `runtime_paths.py`, `corpus/paths.py` |
| DP3 | Atomic JSON, flock, format gate | `persistence/atomic.py`, `locks.py`, `schema.py` |
| DP4 | `ProjectService` | `services/project.py` (SoT + dates + review + declutter + reconcile) |
| DP5 | Ingest + declutter | `ingest/`, `declutter/`, `ProjectService.reapply_visual_declutter` |
| DP6 | OCR job coordinator | `services/job.py:JobCoordinator` |
| DP7 | Ollama HTTP + discovery cache | `providers/ollama.py`, `analysis/llm_runtime.py` |
| DP8 | Multipass / rank / cleanup / preference ledger | `services/multipass.py`, `ocr_compare.py`, `ocr_cleanup.py` |
| DP9 | Analysis adapter / runner / cache identity | `analysis/adapter.py`, `runner.py`, `storage.py`, `cache_identity.py` |
| DP10 | Analysis coordinator + presets | `analysis/coordinator.py`, `analysis/plan.py`, `config/models.py` |
| DP11 | Detection runner / storage / NER bridge | `detection/runner.py`, `storage.py`, `api.py`, `ner_people.py` |
| DP12 | Tags | `tagging/`, `services/tags.py` |
| DP13 | Archive SQLite cache | `services/archive.py` |
| DP14 | Corpus + batch OCR/analyse | `corpus/orchestrator.py`, `services/batch_ocr.py`, `batch_analysis.py` |
| DP15 | Export | `services/export.py` |
| DP16 | Workspace backup | `services/workspace_backup.py` |
| DP17 | Layered config | `config/resolve.py`, `facade.py`, `env_allowlist.py` |
| DP18 | Prompt hub | `prompt_engine/` |
| DP19 | Streamlit shell / session / `cache_resource` | `ui/app.py`, `shell.py`, `navigation.py` |
| DP20 | Review / page overlay | `ui/review_workbench.py`, `review_queue.py`, `page_viewer.py` |
| DP21 | Action menus | `ui/action_menus/` |
| DP22 | CLI | `__main__.py` |
| DP23 | Doctor | CLI + `ui/diagnostics.py` |
| DP24 | Places geocode | `services/places.py`, `ui/places_map.py` |
| DP25 | Page metrics / thumbs | `page_metrics/`, `services/thumbnails.py` |

## D. Current design matrix

`X` = changing that DP could reasonably affect that FR.

| FR \ DP | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 |
|---------|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FR1 Import | X | X | X | X | X | | | | | | | | X | X | | | X | | X | | X | X | | | X |
| FR2 OCR | X | X | X | X | | X | X | | | | | | X | X | | | X | X | X | | | X | | | |
| FR3 Multipass | X | X | X | X | | X | X | X | | | | | | | | | X | X | X | X | | X | | | |
| FR4 Review | X | X | X | X | X | X | | X | | | | X | X | | | | | | X | X | X | | | | X |
| FR5 Analyse | X | X | X | X | | | X | | X | X | X | | | X | | | X | X | X | | | X | | | |
| FR6 Detect | X | X | X | X | | | X | | X | X | X | X | | | | | | X | X | | | X | | | |
| FR7 Export | X | X | X | X | | | | | | | | | | | X | | X | | X | | X | X | | | |
| FR8 Library | | X | X | X | | | | | | | | | X | X | | | X | | X | | X | | | | X |
| FR9 Places | | X | | X | | | | | X | | | | | | | | | | X | | | | | X | |
| FR10 CLI | X | X | X | X | X | X | X | X | X | X | X | | | X | X | X | X | | | | | X | X | | |
| FR11 Settings | | X | X | X | | | X | | | X | | | | | | | X | | X | | X | | | | |
| FR12 Bulk | X | X | X | X | X | X | X | X | X | X | X | | | X | | | X | | X | | | X | | | |
| FR13 Backup | | X | X | X | | | | | | | | | X | X | | X | X | | X | | | X | X | | |
| FR14 Doctor | X | X | X | X | X | | | | X | | X | X | X | X | | X | | | X | | | X | X | | |
| FR15 Declutter/metrics | X | X | X | X | X | | | | | | | | | | | | X | | X | X | | | | | X |
| FR16 Tags | | X | X | X | | | | | | | X | X | | X | | | | | X | | | | | | |
| FR17 Prompts | | X | X | | | X | X | | | | X | | | | | | | X | X | | | | | | |
| FR18 Crash | X | X | X | X | X | X | | X | X | X | X | | | X | | X | | | | | | | X | | |
| FR19 Privacy | | | | | | | X | | | | | | | | | X | X | | X | | | X | | X | |
| FR20 Job isolation | | X | X | X | | X | | X | | X | X | X | | X | | X | | | X | | | X | | | |
| FR21 Schema gate | X | | X | X | | X | | | X | | X | X | | X | X | X | X | | | | X | | | | |
| FR22 Observability | | | | X | | X | X | X | X | X | X | | | X | | X | | | X | X | | X | X | | |
| FR23 Navigation | | | | X | | | | | | | | | X | | | | X | | X | X | X | | | | |

Non-obvious coupling: `effective_text()` feeds analysis/detection/export; OCR fingerprint includes prompts and cleanup plan; Analyse plans run detectors after modules; detection reconcile historically gated only on the **OCR** job lock; `load(reconcile=True)` mutates attempt files; archive freshness depends on `bump_archive_generation`.

## E. Coupling and blast radius

| DP | Class |
|----|--------|
| DP2, DP3, DP15, DP25 | Sequentially coupled, understandable |
| DP5, DP12, DP16, DP23, DP24 | Mostly independent, sequential reads of DP1/DP4 |
| DP6, DP8, DP9, DP10, DP14 | Sequential along the pipeline |
| DP1, DP4, DP7, DP17, DP19 | **Systemic** |
| DP11 detection (NER + reconcile lock + Analyse embedding) | **Cross-coupled** |
| DP13 archive, DP18 prompts, DP20 review UI | **Cross-coupled** |

Dangerous “local” edits: `effective_text` / attempt activation; `ProjectService.load`; OCR fingerprint composition; `JobProgress.status` vocabulary; forgotten archive generation bump; preset `detector_ids`; `st.cache_resource` coordinator constructors.

Pressure: `ProjectService` (~1300 lines) mixes SoT I/O, ingest recovery, OCR graph, review, dates, declutter, and analysis/detection reconcile. Review workbench and `run_transcribe.py` embed orchestration. Call cycle: `load` → analysis/detection storage; `DetectionRunner` → `ProjectService` + `AnalysisRunner`.

Do **not** replace file-shaped SoT with a database, add an event bus, or split CLI/UI service implementations because those patterns exist elsewhere.

## F. UI / state (highlights)

Routing is session-only (`ui_mode` + `root`). No `st.query_params`.

- Import partial success uses `st.success` with “(N failed)”.
- Cover Open is an opacity-0 button.
- Review dirty leave: second Prev/Next discards (`rw_force_leave`).
- Detect runs synchronously in the request; no cancel.
- Settings **Reset whole workspace settings** has no confirm (copies `settings.reset.{stamp}.json` first).
- Re-apply visual declutter has no confirm; margin loss is documented.
- Cancelled jobs historically rendered as Failed; circuit skip as Completed. *(Chrome fixed in this change set.)*

## G. Production failure (highlights)

| Failure | User / state | Retry | Notes |
|---------|--------------|-------|-------|
| Ollama timeout ×3 | UI warning; job `completed` + `circuit_open` | Yes / force | CLI `run` now exits 1 |
| `model_load` in-run | Same circuit path | Yes | Preflight path is `failed` |
| Cleanup LLM fails | Page succeeded with raw OCR | Fingerprint still includes cleanup | Skip may assume cleanup that never applied |
| Kill mid-OCR | `running` → `interrupted` if job lock free | Yes | |
| Two OCR/analysis starts | `JobConflictError` | After finish | |
| Detect during Analyse `load()` | False `interrupted` then usually overwritten | — | Analysis-lock guard added |
| Disk full mid-OCR | No ENOSPC pre-check on page writes | — | Ingest/backup do check |
| Restore mid-replace | Safety ZIP if written | Restore ZIP | Not covered by mid-crash tests |
| Unexpected schema_version | `SchemaError` | Matching build | No migrator |

## H. Data integrity / security

Authority is file-shaped JSON. Constraints are application-level. No multi-file ACID; ingest journal + locks substitute.

Trust: whoever can open port 8510 or the workspace directory is fully privileged. Compose publishes loopback by default; container process listens `0.0.0.0`. Backup ZIPs are plaintext. Remote Ollama / Nominatim are explicit exfil paths with UI/CLI gates.

No P0 remote multi-tenant issue: there is no such backend.

## I. Observability

No metrics/traces. Tools are stderr progress, UI panel, on-disk attempts, doctor, Ollama health.

Blind spots that remain: job records unvalidated / not a Diagnostics timeline; no correlation id across OCR → analysis → detect; UI coverage omitted from `.coveragerc`.

## J. Test architecture

Strong: OCR lifecycle, fingerprints, circuit, analysis cache/crash, corpus import resume, backup zip-slip, detection lexical/NER, config corrupt/concurrent save.

Weak: Streamlit behaviour (source-string contracts), encrypted PDF (implemented, untested), ENOSPC during OCR, schema migrations, multiprocess locks, restore mid-replace.

False confidence: UI tests that `assert 'progress.status == "completed"' in RUN`; circuit tests that encode skip-the-rest as `completed` (correct for coordinator status; insufficient for CLI).

## K. Prioritised findings

**P0** — none evidenced for this local single-user trust model.

**P1**

1. OCR circuit reports `completed` and CLI `run` historically exited 0. *(CLI exit addressed.)*
2. Cleanup failure still seals cleanup into the OCR fingerprint while keeping raw text.

**P2**

3. `ProjectService.load(reconcile=True)` is a write.
4. Detection ↔ analysis NER call-in.
5. `effective_text()` as implicit integration bus.
6. God `ProjectService` + large Review workbench.
7. Split schema registries.
8. Archive cache freshness depends on remembering to bump generation.
9. Detection reconcile gated only on OCR job lock. *(Analysis-lock guard addressed.)*

**P3** — Detect no cancel; settings reset / declutter weak confirm; invisible cover Open; dirty-leave second-click; session-only routing; auto-tag re-applies removed tags; cancelled chrome. *(Cancelled/circuit chrome addressed.)*

**P4** — rewrite Streamlit, introduce a DB SoT, plugin frameworks: out.

## L. Minimum viable decoupling (proposed vs done)

| ID | Change | This pass |
|----|--------|-----------|
| L1 | Circuit is not CLI success; keep on-disk `completed`; UI phase `partial` | **Done** (CLI `run` + chrome). Multipass overall-complete unchanged. |
| L2 | Split `load` from `reconcile`; detection lock | **Partial:** reconcile still default-on-load; detection now also no-ops when **analysis** lock held. Full load-default change deferred. |
| L3 | Names detector consumes published NER only | Proposed |
| L4 | One schema registry for every written `format` | Proposed |
| L5 | Pure snapshot mappers tested without Streamlit page imports | **Done:** `ui/progress_snapshots.py` |

Do not: replace JSON-on-disk, add an event bus, add v1 auth, rewrite navigation.

## M. Revised matrix (after this pass)

Remaining off-diagonals that should stay: FR2/3/4/5/6/7 × DP1 `effective_text`; FR2 × DP7 Ollama; FR5 × DP10 → DP11 optional detectors on a plan; FR8 × DP13 archive cache; FR6 × DP12 tags; FR19 × DP7; FR20 × DP6/DP10 locks; FR1 × DP5 declutter × render SHA.

Narrowed: FR10 CLI × false circuit success; FR22 × cancelled-as-failed chrome; FR6/FR18 × detection reconcile during live Analyse.

Still open: FR4 `load` × DP11/DP9 attempt mutation; FR6 × DP9 nested `run_module`; FR21 unregistered formats.

## N. Change-risk map

| Area | Looks local | What breaks | Tests after touching |
|------|-------------|-------------|----------------------|
| 1. `effective_text` / prefer | Review toggle | Analysis/detection cache, export revision, Places, FTS | OCR lifecycle, analysis identity, export, detection cache |
| 2. OCR fingerprint / `JobPlan` | Skip logic | Surprise re-OCR or stale skip | `test_resume_fingerprint`, cleanup job, preprocess |
| 3. `JobProgress.status` / `circuit_open` | Error handling | CLI exit, UI chrome, tests asserting `completed` | `test_ocr_timeout_circuit`, `cli_run_exit_code`, snapshot tests |
| 4. `ProjectService.load` / reconcile | “Just read” | Live analysis/detection attempts | Hardening, detection storage, ingest recover |
| 5. `ProjectService` mutators | One method | Job lock, archive, declutter SHA, thumbs | `test_project_*`, archive, declutter, delete-during-job |
| 6. Analysis cache identity | Module tweak | NER, names, Places, View freshness | Wave/hardening, names detector |
| 7. Preset `detector_ids` | Settings copy | Surprise vision load | `test_detect_in_analyse`, batch analysis |
| 8. Archive `ensure_index` | Search speed | Library/Search wrong | `test_archive.py` |
| 9. `cache_resource` coordinators / session `root` | UI polish | Dropped live jobs | Listing cache, batch conflict, **manual in-flight pass** |
| 10. Config resolve / `_WS_CACHE` | One knob | Wrong URL/model on next job | `test_workspace_config*`, GUI alignment |

## O. Implementation sequence

1. This review file + index (docs only historically; bundled here).
2. **L1 CLI + chrome** — `cli_run_exit_code`; cancelled/partial snapshots; `known_limitations` / `runtime/ocr.md`.
3. **Detection reconcile vs analysis lock.**
4. Later: L2 load default, L3 NER port, L4 schema registry, leftover P1 fingerprint/cleanup, and remaining P3 polish — recorded on [ROADMAP.md](../ROADMAP.md#later--architecture-follow-ups-from-evidence-review--candidates), not this pass.

## Related

- Contracts: [CONTRACT_INDEX.md](../CONTRACT_INDEX.md)
- Shape (may lag this review): [ARCHITECTURE.md](../ARCHITECTURE.md)
- Sequencing for remaining items: [ROADMAP.md — Architecture follow-ups](../ROADMAP.md#later--architecture-follow-ups-from-evidence-review--candidates)
- OCR honesty: [known_limitations.md](../known_limitations.md) · [runtime/ocr.md](../runtime/ocr.md)
- Detection storage: [detection-run-storage.md](../contracts/detection-run-storage.md)
