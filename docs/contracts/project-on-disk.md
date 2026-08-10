Type: CONTRACT
Authority: self — on-disk project layout, `project.json` wire fields, per-notebook ingest durability, and per-notebook locks. Sole authority for top-level managed-notebook directory paths. Corpus identity, workspace ordering, ImportRun orchestration, and cross-notebook integrity are owned by the prospective bulk-import contracts: [notebook-corpus.md](notebook-corpus.md), [source-asset.md](source-asset.md), [import-run.md](import-run.md), [corpus-integrity.md](corpus-integrity.md).

# Project on-disk format

This contract owns the durable **per-notebook** directory layout. Page-result JSON details: [page-result.md](page-result.md). Export interchange: [notebook-export.md](notebook-export.md). Analysis artifact rules under `analysis/`: [analysis-run-storage.md](analysis-run-storage.md).

**Conformance:** `transcribe.project` schema_version `1` remains fully conformant without a corpus index or ImportRun support. Bulk-import generation must not invalidate existing notebooks; see the [activation gate](notebook-corpus.md#activation-gate).

**Filesystem layout is non-contractual for identity.** Directory names are implementation locators. Durable notebook identity is `project.id` (`notebook_id` in corpus domain language). After bulk-import activation, the corpus index supplies the mutable `managed_relpath` locator ([notebook-corpus.md](notebook-corpus.md)).

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
| `detection/` | Durable per-notebook detection findings (optional until first write; see [detection-run-storage.md](detection-run-storage.md)) |
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

### `detection/` optionality

- The `detection/` directory is **optional until the first detection artifact is written**.
- Existing managed projects without `detection/` remain valid.
- Introducing detection under `detection/` **is not** a project-layout migration: writers create it on demand.

Other contracts (including analysis-run-storage and detection-run-storage) **reference** these paths and must not independently redefine the top-level project tree.

## `project.json`

- `format` must be `"transcribe.project"`
- `schema_version` must be `1` for this build
- Owns notebook metadata (title, tags, cover page, date range), OCR settings, `sources`, ordered `pages`, and `renders`
- Canonical notebook identity is `project_id` / `id` (stable across moves of the project directory); domain alias `notebook_id ≡ project.id`
- **Page order** within the notebook is the `pages` array order (authoritative; not filename lexicography)
- Source and page identity is by ID (`source_id`, `page_id`, `render_id`), not by filename alone
- `page_index` is within-source only; it is not the notebook global order
- Page diary dates may be auto-suggested (`date_source: extracted|inherited`) or human-approved. Invariants: `date=null` ⇒ `date_approved=true` and `date_source=null`; approved dates have `date_source=null`; unapproved dates require a source. Legacy manifests without these keys load as approved.

Writers load → modify → validate → atomically replace `project.json` under the mutation lock. Callers must not wholesale-write a stale in-memory `Project` that was loaded before an unrelated settings/metadata change.

## Ingest durability

Ingest stages bytes under `.staging/{attempt_id}/`, writes `.ingest-journal.json`, promotes files with same-filesystem replace, then commits `project.json`, then clears the journal.

- If the journal is present on open/load/cleanup, Transcribe finishes a coherent pending commit or rolls back uncommitted finals and staging **when the journal is well-formed**
- Format identity for the journal payload: `transcribe.ingest-journal` / schema version `1`
- **At most one active ingest transaction per notebook** (single `.ingest-journal.json`). Bulk orchestration must enforce this — no intra-notebook parallel commits ([import-run.md](import-run.md))
- Malformed/corrupt journals must be **reported and quarantined**, not silently discarded (bulk-import generation requirement; see [import-run.md](import-run.md) and [corpus-integrity.md](corpus-integrity.md))

Defensive limits (implementation-enforced): source byte cap, PDF page cap, rendered-byte budget, free-disk headroom. Exact numeric limits live in `transcribe.ingest` and may change; behaviour is “fail closed with `IngestError`”.

## Locks

| Lock | Scope |
|------|-------|
| `.transcribe.lock` | Short critical sections for manifest/result/analysis RMW |
| `.transcribe.job.lock` | At most one OCR job per project across processes |

Workspace corpus lock and **corpus → notebook** lock order are defined in [notebook-corpus.md](notebook-corpus.md) (prospective until activation).

## Non-authority

- Workspace `data/cache/archive.sqlite` is **not** part of a project and is never authoritative (rebuildable search/timeline cache; on-disk project + page results remain truth)
- Any future analysis discovery/index rows in archive (or elsewhere) are disposable pointers at project-local artifacts under `analysis/` and must never become analysis authority
- `jobs/*.json` records run-level history; resume/skip authority remains page attempts + fingerprints
- `.cache/**` is disposable acceleration only

## Explicit non-goals (layout)

- Do **not** operate in-place on external notebook folders as the durable unit
- Do **not** require user JPEGs at project root with an application-owned `.transcribe/` subtree for derived state
- Do **not** introduce a global authoritative analysis store outside the managed project
