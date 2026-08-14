Type: PRODUCT
Authority: Product hardening checklist and phase sequencing for Analyse robustness/UX. Does not redefine runtime contracts — those stay in CONTRACT docs. Companion to [ROADMAP.md](ROADMAP.md) **Now — Usability wave** and the full track plan [usability_wave_plan.md](usability_wave_plan.md) (U0 = Phases 3–5, U1 = Phase 6).

# Product hardening plan

Phased delivery after the core module set. Order: **#10 → #3/#4 → #1/#2 → #5/#6 → #11/#12 → #13 → #7–9**. Usability-wave embedding: Phases **3–5 → track U0 (done)**, Phase **6 (#7–9) → track U1 (done)**. Hardening exit gate suite: [tests/acceptance/hardening/](../tests/acceptance/hardening/).

## Checklist

| ID | Item | Phase | Status |
|----|------|-------|--------|
| #10 | Archive mutation-generation TTL + shared Ollama discovery cache | 1 | done |
| #3 | One batch Analyse launcher (preset form only) | 1 | done |
| #4 | One freshness authority (`module_freshness` / planned cache identity) | 1 | done |
| #1 | Project-scoped async AnalysisCoordinator (survive UI interruption; honest crash/reopen) | 2 | done |
| #2 | Durable AnalysisRunPlan + frozen snapshot (workers consume the plan, not live settings) | 2 | done |
| #5 | Preflight plan-hash bind | 3 | done |
| #6 | Versioned presets | 3 | done |
| #11 | `content_revision` | 4 | done |
| #12 | Derived health shared across surfaces | 4 | done |
| #13 | Provenance-aware export under stable revision | 5 | done |
| #7 | Product views (task-shaped Analyse read-models; demote module-id / JSON chrome) | 6 | done |
| #8 | Shared status strip (sole default freshness/health answer) | 6 | done |
| #9 | OCR Advanced (primary = model + run; power controls collapsed) | 6 | done |

## Phase outcomes

| Phase | IDs | Outcome |
|-------|-----|---------|
| **1** | #10, #3, #4 | Analyse has one launcher and one freshness authority |
| **2** | #1, #2 | Runs survive UI/process interruption and execute from frozen inputs |
| **3** | #5, #6 | Users can trust exactly what a preset will run |
| **4** | #11, #12 | Every analysis surface gives the same answer to “is this current and healthy?” |
| **5** | #13 | Exports identify exactly which notebook revision produced them |
| **6** | #7, #8, #9 | Analyse surfaces are simplified around user tasks rather than module mechanics |

## Phase 2 notes

- Mirror OCR `JobCoordinator` / `JobPlan`: in-process thread, project analysis lock, durable run record under `analysis/runs/`.
- Process death does **not** auto-resume; reopen marks orphaned attempts/runs `interrupted`; re-run uses published cache hits.
- Mid-run settings / text-model / module-list changes apply to the **next** run only.
- Ask notebook remains an ad-hoc action (not a durable batch run).

## Phase 6 notes

- **#8** One status strip on View consume pages answers revision · aggregate · active/interrupted. Per-tab aggregate captions and default capability banners are removed. (Originally above Analyse result tabs; product views now live under View.)
- **#7** Overview / Themes / Mood / Moments / Summaries / Ask / Last run are product read-models; module ids, capability enums, and `st.json` live under **Advanced**.
- **#9** Transcribe primary chrome is vision model + Start (+ optional cleanup toggle). Workers, force re-OCR, cleanup detail, and capability dumps sit under **Advanced**. Remote-host privacy acknowledgement stays visible/confirm-gated.

Governing contracts: [analysis-run-storage](contracts/analysis-run-storage.md) · [analysis-result](contracts/analysis-result.md) · [project-on-disk](contracts/project-on-disk.md).
