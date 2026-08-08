Type: CONTRACT
Authority: self — on-disk project layout, `project.json` identity, ingest durability, and locks

# Project on-disk format

This contract owns the durable project directory. Page-result JSON details: [page-result.md](page-result.md). Export interchange: [notebook-export.md](notebook-export.md).

## Layout

A project root contains:

| Path | Role |
|------|------|
| `project.json` | Authoritative notebook manifest (`format: transcribe.project`) |
| `sources/` | Copied original JPEG/PNG/PDF bytes |
| `pages/<source_id>/<page_index>/<render_id>.png` | Versioned page renders |
| `results/<page_id>.json` | Per-page OCR attempts and edits |
| `exports/` | Default export destination inside the project |
| `prompts/` | Reserved for project prompt assets |
| `jobs/` | Ephemeral-ish OCR job run records (not page authority) |
| `.staging/` | Ingest scratch (cleared after commit / recovery) |
| `.cache/thumbs/` | Disposable thumbnails |
| `.transcribe.lock` | Short mutation lock |
| `.transcribe.job.lock` | Cross-process OCR job lock |
| `.ingest-journal.json` | Crash journal for an in-flight ingest (absent when idle) |

Relative paths stored in the manifest must resolve inside the project root (path containment).

## `project.json`

- `format` must be `"transcribe.project"`
- `schema_version` must be `1` for this build
- Owns notebook metadata (title, tags, cover page, date range), OCR settings, `sources`, ordered `pages`, and `renders`
- Source and page identity is by ID (`source_id`, `page_id`, `render_id`), not by filename alone

Writers load → modify → validate → atomically replace `project.json` under the mutation lock. Callers must not wholesale-write a stale in-memory `Project` that was loaded before an unrelated settings/metadata change.

## Ingest durability

Ingest stages bytes under `.staging/{attempt_id}/`, writes `.ingest-journal.json`, promotes files with same-filesystem replace, then commits `project.json`, then clears the journal.

- If the journal is present on open/load/cleanup, Transcribe finishes a coherent pending commit or rolls back uncommitted finals and staging
- Format identity for the journal payload: `transcribe.ingest-journal` / schema version `1`

Defensive limits (implementation-enforced): source byte cap, PDF page cap, rendered-byte budget, free-disk headroom. Exact numeric limits live in `transcribe.ingest` and may change; behaviour is “fail closed with `IngestError`”.

## Locks

| Lock | Scope |
|------|-------|
| `.transcribe.lock` | Short critical sections for manifest/result RMW |
| `.transcribe.job.lock` | At most one OCR job per project across processes |

## Non-authority

- Workspace `data/cache/archive.sqlite` is **not** part of a project and is never authoritative
- `jobs/*.json` records run-level history; resume/skip authority remains page attempts + fingerprints
