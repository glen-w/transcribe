Type: CONTRACT
Authority: self — portable `transcribe.notebook` interchange and multi-format export bundle

# Notebook export

## Formats produced

Export builds one coherent snapshot of the project + page results, then writes:

| File | Role |
|------|------|
| `notebook.transcribe.json` | Portable structured notebook (`format: transcribe.notebook`) |
| `notebook.md` | Markdown derived from effective text |
| `notebook.txt` | Plain text derived from effective text |
| `export.manifest.json` | Checksums and file list for the bundle |

Default destination is the project `exports/` directory unless overridden (CLI dest / `TRANSCRIBE_EXPORT_DIR`).

## `content_revision`

Every export bundle **must** stamp the snapshot’s notebook `content_revision` (algorithm in [project-on-disk.md](project-on-disk.md)). The revision is computed from the **same frozen snapshot** used to build all formats — not a later reload.

| Artifact | Where |
|----------|-------|
| `notebook.transcribe.json` | top-level `content_revision` (hex) |
| `export.manifest.json` | top-level `content_revision` |
| `notebook.md` | HTML comment header `<!-- transcribe.content_revision: <hex> -->` |
| `notebook.txt` | first line `# transcribe.content_revision: <hex>` |

All four must cite the **same** hex for one export.

## `transcribe.notebook` JSON

- `format` must be `"transcribe.notebook"`
- `schema_version` must be `1`
- Includes `content_revision`, application version, project metadata, source summaries, and ordered pages
- Per page: order (`global_index`), status, effective/raw/edited text, fingerprints, provenance, tags/dates as present
- Page date fields are always emitted together: `date`, `date_approved`, `date_source` (canonical triples; undated ⇒ `date: null`, `date_approved: true`, `date_source: null`)
- **Legacy readers** may ignore unknown keys (`date_approved`, `date_source`, `content_revision`) and continue to use `date` alone
- **Must not require absolute filesystem paths** in the interchange payload

## `transcribe.export-manifest`

- `format` must be `"transcribe.export-manifest"`
- `schema_version` must be `1`
- Includes `application_version`, `project_id`, `project_updated_at`, `content_revision`, `files`, and per-file `sha256`

## Snapshot semantics

All three text formats and the structured notebook are derived from the same frozen load of `project.json` + page results. Writers stage into a temporary directory under the destination, then promote atomically so a failed export does not leave a mixed old/new set.

## Future consumers

A future TranscriptX adapter may consume `transcribe.notebook` after TranscriptX 1.0. Prefer `content_revision` when present. That seam is product/architecture guidance only today: [INTEGRATION_SEAM.md](../INTEGRATION_SEAM.md).
