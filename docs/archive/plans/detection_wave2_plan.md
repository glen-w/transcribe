> **Archived / superseded.** Detection Prompt Hub / Detect delivery history (shipped parallel track). Current authority: [docs/ROADMAP.md](../../ROADMAP.md). Do not treat as live roadmap or support policy.

# Detection / Prompt Hub wave 2

Wave 1 shipped `prompt_engine` + `detection` + built-in `poetry` (CLI + caption badges). Wave 2 adds Unified Prompt Hub, Detect product UI, and built-ins `todo_lists` / `lists` / `quotations`, plus durability/honesty hardening.

## Checklist

| ID | Item | Status |
|----|------|--------|
| D1 | Integrate onto main without regressing Analyse Phase 2 / shell / page-viewer | done |
| D2 | Single prompt authority: OCR, cleanup, detection resolve through Hub | done |
| D3 | Detection cache identity uses hub-resolved `(prompt_id, version)`; overrides always win and bump freshness | done |
| D4 | Interrupted attempts reconciled on project open; active runs use `load(reconcile=False)` | done |
| D5 | Prompt definition frozen into planned identity / attempt at run start; mid-run Hub edits apply next run only | done |
| D6 | Hub safety: validate on save; restore builtin; dry-run non-mutating; custom vs override isolation | done |
| D7 | Validators: evidence/item caps; malformed JSON → abstention warnings | done |
| D8 | Snapshot custom detector defs under project `detection/custom/` | done |
| D9 | Review carry-forward on republish by span identity | done |
| D10 | Docs + offline tests; ROADMAP marks Prompt Hub + Detection shipped | done |

## Explicit non-goals

- Async `DetectionCoordinator` / durable multi-detector run plans (Analysis Phase 2 parity)
- Heuristic `candidate_strategy` beyond `all_pages`
- Additional built-in detectors beyond poetry + todo/lists/quotations
- Moving analysis module inline prompts into the Hub
- Archive SQLite indexing of findings

## Follow-on (not Wave 2)

Analyse suite orchestration can freeze `detector_ids` into `AnalysisRunPlan` / Batch and invoke `DetectionService` after modules (This notebook + Batch). That keeps detection storage/contracts intact and does not reopen Wave 2.

## Exit gate

Wave 2 is done when D1–D9 have code + offline tests, D10 docs linked, Detect/Prompt Hub usable on Analyse/Settings, and the branch is rebase-clean vs `main`.

Governing contracts: [prompt-definition](../../contracts/prompt-definition.md) · [detection-definition](../../contracts/detection-definition.md) · [detection-finding](../../contracts/detection-finding.md) · [detection-result](../../contracts/detection-result.md) · [detection-run-storage](../../contracts/detection-run-storage.md).
