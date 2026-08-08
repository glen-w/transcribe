Type: GUIDE
Authority: navigation map only — each contract owns its own rules

# Contract index

Truth hierarchy: **on-disk project + page results** are authoritative. Archive SQLite is disposable derived state. Invariants live in the CONTRACT docs below — not in README, guides, or architecture.

| Concept | Authority |
|---------|-----------|
| Supported entrypoints (CLI / UI / scripts) | [public_surfaces.md](public_surfaces.md) |
| Project directory layout, `project.json`, ingest journal, locks | [contracts/project-on-disk.md](contracts/project-on-disk.md) |
| Page results, attempts, edits, fingerprints (persisted) | [contracts/page-result.md](contracts/page-result.md) |
| Portable notebook export | [contracts/notebook-export.md](contracts/notebook-export.md) |
| Future TranscriptX handoff (non-shipped) | [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md) |

Schema identity and version gates in code: `transcribe.persistence.schema.SUPPORTED` (`transcribe.project`, `transcribe.page-result`, `transcribe.notebook` — all version **1** today).
