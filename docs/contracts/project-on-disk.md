Type: CONTRACT
Authority: self — on-disk project layout, `project.json` identity, ingest durability, and locks. Sole authority for top-level managed-project paths.

# Project on-disk format

This contract owns the durable project directory layout. Page-result JSON details: [page-result.md](page-result.md). Export interchange: [notebook-export.md](notebook-export.md). Analysis artifact rules under `analysis/`: [analysis-run-storage.md](analysis-run-storage.md).

Transcribe is a **managed-library** application: importing a notebook copies source bytes into a canonical project directory. External originals remain untouched and outside Transcribe ownership. After ingest, runtime authority is stable `project_id` / `source_id` / `page_id` (+ renders) and canonical metadata — not original external paths or filenames.

## Layout

A project root contains:

| Path | Role |
|------|------|
| `project.json` | Authoritative notebook manifest (`format: transcribe.project`); owns canonical `project_id` |
| `sources/` | Copied original JPEG/PNG/PDF bytes |
| `pages/<source_id>/<page_index>/<render_id>.png` | Versioned page renders |
| `results/<page_id>.json` | Per-page OCR attempts and edits |
| `analysis/` | Durable per-notebook analysis artifacts (optional until first write; see [analysis-run-storage.md](analysis-run-storage.md)) |
| `exports/` | Default export destination inside the project |
| `prompts/` | Reserved for project prompt assets |
| `jobs/` | Ephemeral-ish OCR job run records (not page authority) |
| `.staging/` | Ingest scratch (cleared after commit / recovery) |
| `.cache/thumbs/` | Disposable thumbnails |
| `.cache/analysis/` | Optional disposable analysis acceleration (never authoritative) |
| `.transcribe.lock` | Short mutation lock |
| `.transcribe.job.lock` | Cross-process OCR job lock |
| `.ingest-journal.json` | Crash journal for an in-flight ingest (absent when idle) |

Relative paths stored in the manifest must resolve inside the project root (path containment).

### `analysis/` optionality

- The `analysis/` directory is **optional until the first analysis artifact is written**.
- Existing managed projects without `analysis/` remain valid.
- Introducing analysis under `analysis/` **is not** a project-layout migration: absence of `analysis/` is conformant; writers create it on demand.

Other contracts (including analysis-run-storage) **reference** these paths and must not independently redefine the top-level project tree.

## `project.json`

- `format` must be `"transcribe.project"`
- `schema_version` must be `1` for this build
- Owns notebook metadata (title, tags, cover page, date range), OCR settings, `sources`, ordered `pages`, and `renders`
- Canonical notebook identity is `project_id` (stable across moves of the project directory)
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
| `.transcribe.lock` | Short critical sections for manifest/result/analysis RMW |
| `.transcribe.job.lock` | At most one OCR job per project across processes |

## Non-authority

- Workspace `data/cache/archive.sqlite` is **not** part of a project and is never authoritative (rebuildable search/timeline cache; on-disk project + page results remain truth)
- Any future analysis discovery/index rows in archive (or elsewhere) are disposable pointers at project-local artifacts under `analysis/` and must never become analysis authority
- `jobs/*.json` records run-level history; resume/skip authority remains page attempts + fingerprints
- `.cache/**` is disposable acceleration only

## Explicit non-goals (layout)

- Do **not** operate in-place on external notebook folders as the durable unit
- Do **not** require user JPEGs at project root with an application-owned `.transcribe/` subtree for derived state
- Do **not** introduce a global authoritative analysis store outside the managed project
