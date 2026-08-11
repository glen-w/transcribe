# Notebook export

## Formats produced

Export builds one coherent snapshot of the project + page results (or several
snapshots for a multi-notebook anthology), then writes the selected formats:

| File | Role |
|------|------|
| `notebook.transcribe.json` | Portable structured notebook (`format: transcribe.notebook`) — single-notebook exports |
| `bundle.transcribe.json` + `notebooks/<slug>/…` | Multi-notebook JSON index + per-notebook JSON |
| `notebook.md` | Markdown derived from effective text |
| `notebook.txt` | Plain text derived from effective text |
| `notebook.html` | Styled HTML (typography from export options) |
| `notebook.epub` | EPUB ebook (requires `ebooklib` / `transcribe[export]`) |
| `notebook.pdf` | Text PDF via PyMuPDF |
| `export.manifest.json` | Checksums, options, and file list for the bundle |

Default destination is the project `exports/` directory unless overridden (CLI dest / `TRANSCRIBE_EXPORT_DIR`).

## `content_revision` and `bundle_revision`

Every export bundle **must** stamp revision identity from the same frozen
snapshot(s) used to build all formats — not a later reload.

| Artifact | Where |
|----------|-------|
| `notebook.transcribe.json` | top-level `content_revision` (hex) |
| `export.manifest.json` | `content_revision` (single) or `bundle_revision` (anthology); always includes `bundle_revision` and `notebooks[]` |
| `notebook.md` | HTML comment header `<!-- transcribe.content_revision: <hex> -->` |
| `notebook.txt` | first line `# transcribe.content_revision: <hex>` |
| `notebook.html` | visible revision meta + same hex |
| `notebook.pdf` | PDF metadata `subject` includes the revision hex |
| `notebook.epub` | DC description includes the revision hex |

For a single notebook, `bundle_revision` equals the hash of that notebook’s
`(project_id, content_revision)` pair. Typography and other presentation
options **do not** participate in `content_revision` / `bundle_revision`.

## Export options and profiles

Workspace subtree `export` (see [workspace-settings.md](workspace-settings.md))
and profile target `export` control formats, page-break mode, date/blank
inclusion, title page, and typography (body font/size, line height, paragraph
spacing, margins, heading scale).

Builtin profiles: `default`, `readable`, `compact`, `large_print`.

## Multi-notebook anthology

When multiple notebooks are selected, human-readable formats concatenate parts
in selection order (each notebook is a part; pages remain sections inside).
JSON is emitted per notebook under `notebooks/<slug>/` plus
`bundle.transcribe.json`.

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
- Includes `application_version`, `project_id`, `project_updated_at`, `content_revision`, `bundle_revision`, `notebooks`, optional `export_options`, `files`, and per-file `sha256`

## `transcribe.export-bundle`

Multi-notebook index (`bundle.transcribe.json`):

- `format` must be `"transcribe.export-bundle"`
- `schema_version` must be `1`
- Includes `title`, `bundle_revision`, and `notebooks[]` with per-part paths

## Snapshot semantics

All selected formats are derived from the same frozen load(s) of `project.json`
+ page results. Writers stage into a temporary directory under the destination,
then promote atomically so a failed export does not leave a mixed old/new set.

If EPUB is requested but `ebooklib` is not installed, and at least one other
format was requested, EPUB is **skipped** and recorded under
`skipped_formats` / `skipped_format_reasons` on the manifest. EPUB-only export
raises when the dependency is missing.

## Future consumers

A future TranscriptX adapter may consume `transcribe.notebook` after TranscriptX 1.0. Prefer `content_revision` when present. That seam is product/architecture guidance only today: [INTEGRATION_SEAM.md](../INTEGRATION_SEAM.md).
