Type: GUIDE
Authority: navigation map only — each contract owns its own rules

# Contract index

Truth hierarchy: **on-disk project + page results** are authoritative. Archive SQLite is disposable derived state (rebuildable search/timeline cache). Analysis outputs are authoritative only inside the managed project’s `analysis/` tree. Invariants live in the CONTRACT docs below — not in README, guides, or architecture.

| Concept | Authority |
|---------|-----------|
| Supported entrypoints (CLI / UI / scripts) | [public_surfaces.md](public_surfaces.md) |
| Project directory layout, `project.json`, ingest journal, locks, optional `analysis/` | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Page results, attempts, edits, fingerprints (persisted) | [contracts/page-result.md](contracts/page-result.md) |
| Portable notebook export | [contracts/notebook-export.md](contracts/notebook-export.md) |
| Canonical analysis input, content fingerprint, `source_ref`, spans | [contracts/analysis-document.md](contracts/analysis-document.md) |
| Analysis result envelope, outcomes vs attempts, capability UI states, provenance, evidence | [contracts/analysis-result.md](contracts/analysis-result.md) |
| Analysis persistence, cache identity, hard/optional parents, atomic publish | [contracts/analysis-run-storage.md](contracts/analysis-run-storage.md) |
| Sole notebook eligibility policy (`notebook_eligibility_v1`) | [contracts/notebook-eligibility.md](contracts/notebook-eligibility.md) |
| Future TranscriptX handoff (non-shipped) | [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) |

Schema identity and version gates in code: `transcribe.persistence.schema.SUPPORTED` (`transcribe.project`, `transcribe.page-result`, `transcribe.notebook`, `transcribe.analysis-document`, `transcribe.analysis-result` — all version **1** today).
