# Terms

This document is an **index of terms only**. It aggregates terminology from authoritative CONTRACT documents and points back to them.

- It **must not** introduce new semantics or rules.
- If any wording here appears to conflict with a CONTRACT document, the **CONTRACT document wins**.

## Terms and authorities

- **Project** — On-disk notebook directory with `project.json`. See [contracts/project-on-disk.md](contracts/project-on-disk.md).
- **Page result** — Per-page JSON of attempts + edits. See [contracts/page-result.md](contracts/page-result.md).
- **Effective text** — Edit if present, else active raw OCR. See [contracts/page-result.md](contracts/page-result.md).
- **Merged draft** — LLM composite of competing vision OCR attempts; a recommendation, not a vote. Internally `attempt_kind=composite`. See [contracts/ocr-multipass.md](contracts/ocr-multipass.md) · [page-result.md](contracts/page-result.md).
- **Notebook default** — `preferred_attempt_id` on a page result; which OCR attempt you Prefer for stats, export, and (depending on mode) current text. See [contracts/page-result.md](contracts/page-result.md) · [runtime/ocr.md](runtime/ocr.md#when-setting-a-notebook-default).
- **Prefer mode** — Per-notebook setting for what Prefer (and multipass auto-composite under `prefer_is_promote`) does to active vs preferred attempts. See [contracts/page-result.md](contracts/page-result.md) · [runtime/ocr.md](runtime/ocr.md#notebook-ocr-settings).
- **Review status** — Page-level `unreviewed` / `needs_attention` / `reviewed` / `skipped`; `reviewed` is valid only for the current effective text + OCR evidence fingerprints. See [contracts/page-result.md](contracts/page-result.md) · [project-on-disk.md](contracts/project-on-disk.md).
- **Fingerprint** — Canonical hash of OCR inputs for skip/resume. See [contracts/page-result.md](contracts/page-result.md).
- **JobPlan** — Frozen OCR execution inputs for one run (shape). See [ARCHITECTURE.md](ARCHITECTURE.md); persisted attempt rules in [page-result.md](contracts/page-result.md).
- **OcrBatchRun** — Durable batch OCR across notebooks. See [contracts/ocr-batch-run.md](contracts/ocr-batch-run.md).
- **AnalysisRunPlan** — Frozen Analyse batch inputs (modules, EffectiveConfig, text-model identity, plan_hash, preset identity). See [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md).
- **plan_hash** — SHA-256 bind of execution-significant AnalysisRunPlan fields. See [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md).
- **AnalysisBatchRun** — Durable bulk Analyse across notebooks (orchestration only). See [contracts/analysis-batch-run.md](contracts/analysis-batch-run.md).
- **AnalysisHealth** — Derived Analyse freshness/health shared across View consume pages. See [contracts/analysis-result.md](contracts/analysis-result.md).
- **content_revision** — SHA-256 of exportable notebook content (all pages). See [contracts/project-on-disk.md](contracts/project-on-disk.md) · [notebook-export.md](contracts/notebook-export.md).
- **`transcribe.notebook`** — Portable export JSON. See [contracts/notebook-export.md](contracts/notebook-export.md).
- **Library** — GUI notebook browser (legacy sidebar names `View` and `Archive`). Default **Covers** thumbnail overview; **Activity** is the per-notebook histogram list. Not a domain rename of the notebook corpus. See [public_surfaces.md](public_surfaces.md).
- **Ingest journal** — Crash journal for multi-file import commit. See [contracts/project-on-disk.md](contracts/project-on-disk.md).
- **Archive index** — Rebuildable SQLite FTS cache for the workspace. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Doctor** — Integrity check CLI / Diagnostics. See [public_surfaces.md](public_surfaces.md) · [corpus-integrity.md](contracts/corpus-integrity.md).
- **Prompt Hub** — Settings catalogue for OCR, cleanup, and detection prompts. See [contracts/prompt-definition.md](contracts/prompt-definition.md).
- **Detector / DetectionFinding** — Prompt-backed scan and derived span finding. See [detection-definition.md](contracts/detection-definition.md) · [detection-finding.md](contracts/detection-finding.md).
- **Visual declutter** — Import-time (and Settings re-apply) scanner-border crop; not OCR preprocess. See [contracts/source-asset.md](contracts/source-asset.md).
- **Library cover-grid paging** — `ui.archive_notebooks_initial` — cover cards before Show more (`0` = all). See [contracts/workspace-settings.md](contracts/workspace-settings.md).
- **Overview cards** — `ui.overview_cards` — which Overview cards are visible (status strip always on). See [contracts/workspace-settings.md](contracts/workspace-settings.md).
- **View Advanced expanders** — `ui.view_show_advanced` — show raw module JSON under **Advanced · …** on View pages (default off). See [contracts/workspace-settings.md](contracts/workspace-settings.md).
- **`transcribe.workspace-backup`** — Full-workspace ZIP (role roots); replace-only restore. See [workspace-backup.md](contracts/workspace-backup.md) · [backup_and_restore.md](backup_and_restore.md).
- **Role roots** — Path-agnostic ZIP prefixes remapped to current mounts on restore. See [contracts/workspace-backup.md](contracts/workspace-backup.md).
- **Install extras** (`[ui]` / `[dev]` / `[export]`) — Packaging profiles, not Analyse presets. See [runtime/installation.md](runtime/installation.md).
- **Named settings profile** — Activation-pointer overlay under `data/config/profiles/<target>/`. See [workspace-settings.md](contracts/workspace-settings.md) · [runtime/settings.md](runtime/settings.md).
- **Analyse UI preset** (Quick / Balanced / Thorough / Custom) — Module-set policies for Analyse. See [workspace-settings.md](contracts/workspace-settings.md) · [runtime/analysis.md](runtime/analysis.md).
- **Slice / ContextCollection / Person store / Reconstruction** — Planned post-1.0 autobiography concepts; **not shipped**. Sequencing only: [ROADMAP.md](ROADMAP.md) After 1.0. No contract yet. Not the Mood → Moments analysis module.
- **ClaimStatus** — Vocabulary map (Evidence / Extraction / Confirmation / Interpretation layers) onto existing `date_approved`, detection `review_status`, and `edited_text`. Documented for the 1.0 foundation checklist; runtime schema waits for After 1.0 contracts. See [ROADMAP.md](ROADMAP.md) Path to 0.9.0 Track C · After 1.0 ClaimStatus table.
- **0.9.0 / 0.9-1** — Package cut (U2 + I0–I6) then unfamiliar-user testing before **1.0**. Intermediate infra cuts: **0.7.0** (I0–I1), **0.8.0** (I2–I3). See [ROADMAP.md](ROADMAP.md) Path to 0.9.0 · [dev/user_testing_0_9.md](dev/user_testing_0_9.md).

This index may grow as new terms appear in CONTRACT docs; each term here must **delegate meaning** rather than redefine it.
