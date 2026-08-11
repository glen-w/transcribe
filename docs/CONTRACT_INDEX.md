Type: GUIDE
Authority: navigation map only — each contract owns its own rules

# Contract index

Truth hierarchy: **on-disk project + page results** are authoritative for each notebook today. Archive SQLite is disposable derived state (rebuildable search/timeline cache). Analysis outputs are authoritative only inside the managed project’s `analysis/` tree. **Bulk-import generation** adds a workspace corpus index + ImportRun authority (prospective until the activation gate). Invariants live in the CONTRACT docs below — not in README, guides, or architecture.

| Concept | Authority |
|---------|-----------|
| Supported entrypoints (CLI / UI / scripts) | [public_surfaces.md](public_surfaces.md) |
| Corpus hierarchy, `notebook_id`, ordering, corpus index, workspace locks (**prospective**) | [contracts/notebook-corpus.md](contracts/notebook-corpus.md) |
| Managed originals, fingerprints, duplicates, source/render invariants (**prospective**) | [contracts/source-asset.md](contracts/source-asset.md) |
| ImportRun / ImportPlan lifecycle, idempotency, crash/resume (**prospective**) | [contracts/import-run.md](contracts/import-run.md) |
| Corpus/notebook doctor invariants, repair boundaries, bulk-import acceptance gate (**prospective**) | [contracts/corpus-integrity.md](contracts/corpus-integrity.md) |
| Project directory layout, `project.json`, ingest journal, locks, optional `analysis/` | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Page results, attempts, edits, fingerprints (persisted) | [contracts/page-result.md](contracts/page-result.md) |
| Portable notebook export | [contracts/notebook-export.md](contracts/notebook-export.md) |
| Canonical analysis input, content fingerprint, `source_ref`, spans | [contracts/analysis-document.md](contracts/analysis-document.md) |
| Analysis result envelope, outcomes vs attempts, capability UI states, provenance, evidence | [contracts/analysis-result.md](contracts/analysis-result.md) |
| Analysis persistence, cache identity, hard/optional parents, atomic publish | [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) |
| Prompt definitions, rendering boundary, schema identity | [contracts/prompt-definition.md](contracts/prompt-definition.md) |
| Detector definitions, scope, candidate strategy | [contracts/detection-definition.md](contracts/detection-definition.md) |
| Detection findings, cross-page spans, review status | [contracts/detection-finding.md](contracts/detection-finding.md) |
| Detection result envelope, outcomes, capability | [contracts/detection-result.md](contracts/detection-result.md) |
| Detection persistence, cache identity, aggregation | [contracts/detection-run-storage.md](contracts/detection-run-storage.md) |
| Page ink / blankness / hue metrics (Pillow; active renders) | [contracts/page-metrics.md](contracts/page-metrics.md) |
| Sole notebook eligibility policy (`notebook_eligibility_v1`) | [contracts/notebook-eligibility.md](contracts/notebook-eligibility.md) |
| Durable UI action-menu prefs (`interface_menus.json` schema v1) | [contracts/interface-menus.md](contracts/interface-menus.md) |
| Workspace settings, profiles, knob precedence, analysis config versions | [contracts/workspace-settings.md](contracts/workspace-settings.md) |
| Future TranscriptX handoff (non-shipped) | [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) |

Schema identity and version gates in code: `transcribe.persistence.schema.SUPPORTED` (`transcribe.project`, `transcribe.page-result`, `transcribe.notebook`, `transcribe.analysis-document`, `transcribe.analysis-result`, `transcribe.detection-result`, `transcribe.prompt-definition`, `transcribe.page-metrics`, plus prospective `transcribe.corpus-index`, `transcribe.import-run`, `transcribe.ingest-journal` — all version **1** today). Interface menus use a separate envelope (`schema_version` 1) under `data/config/interface_menus.json` — see the interface-menus contract. Prospective corpus formats are **not** required for `transcribe.project` v1 conformance until the [activation gate](contracts/notebook-corpus.md#activation-gate).

