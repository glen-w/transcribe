Type: GUIDE
Authority: non-authoritative glossary — meanings are owned by CONTRACT / PRODUCT docs

# Terms

| Term | Meaning (summary) | Authority |
|------|-------------------|-----------|
| Project | On-disk notebook directory with `project.json` | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Page result | Per-page JSON of attempts + edits | [contracts/page-result.md](contracts/page-result.md) |
| Effective text | Edit if present, else active raw OCR | [contracts/page-result.md](contracts/page-result.md) |
| JobPlan | Frozen OCR execution inputs for one run | [ARCHITECTURE.md](ARCHITECTURE.md) |
| AnalysisRunPlan | Frozen Analyse batch inputs (modules, EffectiveConfig, text-model identity, plan_hash, preset identity) | [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) |
| plan_hash | SHA-256 bind of execution-significant AnalysisRunPlan fields | [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) |
| content_revision | SHA-256 of exportable notebook content (all pages) | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| AnalysisHealth | Derived Analyse freshness/health shared across result tabs | [contracts/analysis-result.md](contracts/analysis-result.md) |
| Fingerprint | Canonical hash of OCR inputs for skip/resume | [contracts/page-result.md](contracts/page-result.md) |
| Ingest journal | Crash journal for multi-file import commit | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Archive index | Rebuildable SQLite FTS cache for the workspace | [ARCHITECTURE.md](ARCHITECTURE.md) |
| `transcribe.notebook` | Portable export JSON | [contracts/notebook-export.md](contracts/notebook-export.md) |
| Doctor | Integrity check CLI | [public_surfaces.md](public_surfaces.md) |
| Prompt Hub | Settings catalogue for OCR, cleanup, and detection prompts | [contracts/prompt-definition.md](contracts/prompt-definition.md) |
| Visual declutter | Import-time (and Settings re-apply) scanner-border crop; not OCR preprocess | [contracts/source-asset.md](contracts/source-asset.md) |
| Archive strip paging | `ui.archive_notebooks_initial` — cards before Show more (`0` = all) | [contracts/workspace-settings.md](contracts/workspace-settings.md) |
| OcrBatchRun | Durable batch OCR across notebooks | [contracts/ocr-batch-run.md](contracts/ocr-batch-run.md) |
| Detector | Prompt-backed scan for notebook phenomena (not a saved prompt alone) | [contracts/detection-definition.md](contracts/detection-definition.md) |
| DetectionFinding | Derived span finding with provenance and review status | [contracts/detection-finding.md](contracts/detection-finding.md) |
