# Import runs

## Activation gate

Same gate as [notebook-corpus.md](notebook-corpus.md) — **satisfied**; this contract is runtime-normative. Single-file ingest via `IngestService` + `.ingest-journal.json` remains a supported import path. This contract defines the bulk orchestration layer used by bulk-import UI/CLI.

## Lifecycle

```text
scan → plan → validate → commit
```

Only **commit** mutates the corpus (notebook entities, managed bytes, corpus index, ImportRun outcomes). Scan/plan/validate are read-only w.r.t. corpus authority (they may write disposable plan drafts under the ImportRun store).

### Adapters

Folder-per-notebook, naming conventions, scanner batches, PDF trees, etc. are **import adapters**. They emit one canonical `ImportPlan`. Adapter heuristics must not leak into notebook identity (`notebook_id` is always preallocated/generated—never “folder name”).

### Notebook cover (folder-per-notebook / file-name heuristic)

When creating or filling a notebook from imported image sources:

1. If a source basename is `cover.jpg`, `cover.jpeg`, or `cover.png` (case-insensitive), and the notebook has no `cover_page_id` yet, set `cover_page_id` to that source’s page (within-source `page_index` 0).
2. Otherwise leave `cover_page_id` unset; display/Open fall back to the **first page in notebook order** (`project.pages[0]`), not earliest dated page.
3. Do not overwrite an existing user-set `cover_page_id`. Cover PDFs are out of scope for this heuristic.

### Ordering ambiguity

Natural sort may be the **proposed** order in a plan. Ambiguous ordering (duplicate numbers, mixed PDF/image without an explicit rule, missing indices, conflicting cues) is a **validate error**. Commit is refused until the plan is resolved. Silent guessing is non-conformant.

## Plan operations

An `ImportPlan` is a list of items. Each item is exactly one of:

| `op` | Meaning |
|------|---------|
| `create_notebook` | Create a new managed notebook directory + `project.json`, then register it in the corpus index, optionally with initial pages/sources |
| `import_into_notebook` | Append sources/pages into an **existing** `notebook_id` already present in the corpus index / on disk |

These must not be collapsed into one ambiguous “import” op. Recovery paths differ (see Crash boundaries).

## Stable IDs and preallocation

Before commit begins, the validated plan must contain:

| ID | Rule |
|----|------|
| `plan_id` | Stable UUID for this plan document; immutable for the plan’s life |
| `item_id` | Stable UUID per plan item; immutable |
| Resulting `notebook_id` | Preallocated for `create_notebook`; fixed target for `import_into_notebook` |
| Resulting `source_id` / `page_id` / `render_id` | Preallocated for every page/source the item would create |

**Retry/idempotency must not regenerate these IDs.** A resumed commit uses the same plan bytes / same IDs. If an item already committed those IDs, recommit is a no-op for that item.

## Plan fingerprint and policy

| Field | Rule |
|-------|------|
| `import_manifest.schema_version` | Integer; `1` for this contract generation |
| `import_policy_id` | Stable string naming duplicate/ordering policy package (e.g. policies that include `skip_existing` or `create_duplicate`) |
| `plan_fingerprint` | Lowercase hex SHA-256 of the **canonical plan body** defined below |

### Canonical plan body (fingerprint input)

Compact UTF-8 JSON with sorted keys containing exactly:

- `schema_version`
- `plan_id`
- `import_policy_id`
- `items` — array in plan order; each item includes `item_id`, `op`, target/`notebook_id`, ordered intended page specs with preallocated IDs, source fingerprints (`sha256`), media type, within-source `page_index` list, and policy-relevant flags (e.g. explicit corpus-wide dedupe request). **Exclude** mutable external paths from the fingerprint, or include them only inside a nested `provenance` object that is **omitted** from the fingerprint input.

### Idempotent equality (replaces vague “same plan + policy”)

A commit attempt is an idempotent retry of a prior attempt iff **all** hold:

1. `plan_id` equal
2. `plan_fingerprint` equal
3. `import_policy_id` equal
4. Item `item_id` set equal (same multiset of items)

Otherwise it is a **different** plan and must not reuse another run’s committed item outcomes as no-ops unless an explicit “continue with new plan” product flow creates a new `ImportRun`.

## ImportRun storage

| Field | Value |
|-------|--------|
| Format | `transcribe.import-run` |
| `schema_version` | `1` |
| Location | `{TRANSCRIBE_DATA_DIR}/corpus/import-runs/<import_run_id>.json` |
| Registry / index (optional companion) | `{TRANSCRIBE_DATA_DIR}/corpus/import-runs/index.json` listing run IDs + terminal status (derived convenience; each run file is authoritative for that run) |
| Writes | Atomic replace under corpus lock (short critical section) |

### Run document shape (normative fields)

- `import_run_id`, `format`, `schema_version`
- `plan_id`, `plan_fingerprint`, `import_policy_id`, `import_manifest.schema_version`
- Immutable history: frozen plan snapshot reference or inlined canonical plan body used for fingerprint; discovery inputs summary; timestamps `created_at`
- Mutable execution state: `status`, per-item outcomes, `updated_at`, error summaries
- Per-item outcome: `item_id`, `state` (`pending` \| `committed` \| `skipped` \| `failed` \| `cancelled_pending`), resulting IDs, skip classification, failure code/message

### Immutable history vs mutable execution

- Plan identity fields and canonical plan body are **immutable** after run creation.
- Item outcome records append/advance forward only (pending → committed/skipped/failed/cancelled_pending). Committed outcomes must not be rewritten to a different ID set.
- Final `status` is written once to a terminal value (see Cancellation).

### Retention

- ImportRun files are **retained by default** (audit/resume). Deletion is an explicit operator action, not automatic GC on success.
- Optional future compaction may archive terminal runs older than a configured age; compaction must not delete the only record of committed page provenance linkage (`import_run_id` on sources) without a documented export.

## Intra-notebook ingest constraint

Existing `.ingest-journal.json` permits **at most one active ingest transaction per notebook**. Bulk orchestration **must enforce** this: never start a second source commit against a notebook that has a live journal; never assume intra-notebook parallelism. Parallelism across notebooks is allowed only under [notebook-corpus.md](notebook-corpus.md) lock rules.

## Cancellation

- Cancellation stops **pending** items; it **never rolls back** already committed pages/sources/notebooks.
- Terminal statuses:

| Status | Meaning |
|--------|---------|
| `complete` | All items committed or intentionally skipped per policy; none failed |
| `partial` | At least one committed and at least one failed (and/or cancelled pending), not a clean full success |
| `failed` | No items committed; one or more failed (or planning/commit aborted before any commit) |
| `cancelled` | Operator cancel with **no** items committed (clean no-op cancellation) |
| `cancelled_with_commits` | Operator cancel after one or more items already committed |

UI/CLI must not collapse `cancelled` and `cancelled_with_commits`.

## Crash / recovery boundaries

At each boundary, recovery picks an **authoritative winner** and is resume-safe.

| Boundary | After success looks like | Authoritative winner on restart |
|----------|--------------------------|--------------------------------|
| 1. Corpus registration (create) | Corpus index entry present for `notebook_id` | If `project.json` exists with that `id` but index lacks entry → **register** (complete registration). If index entry exists but `project.json` missing → **error/quarantine** (do not invent notebook). |
| 2. Notebook creation | `project.json` exists with preallocated `notebook_id` | Winner is on-disk `project.json`. Incomplete create without valid manifest → roll back directory only if never registered; if registered, doctor error. |
| 3. Source promotion | Managed source file present + matches planned `sha256` | File + hash win; journal continues toward manifest commit. |
| 4. Render promotion | Render PNG present + matches planned render hash | File + hash win. |
| 5. `project.json` commit | Pages/sources/renders include preallocated IDs | Manifest wins; clear per-notebook ingest journal only after manifest matches journal intent. |
| 6. ImportRun item commit | Item outcome `committed`/`skipped` with IDs | ImportRun item record wins for idempotency; do not recreate. |
| 7. Final run-state commit | Terminal `status` set | Terminal status wins; do not reopen terminal runs except via explicit new plan. |

**Create vs register race:** If `project.json` was created with the preallocated `notebook_id` but corpus registration did not commit, recovery **must** complete registration (append index entry) rather than creating a second notebook or deleting the valid project. If registration exists without a loadable project, report integrity error—do not delete the index entry silently.

## Journals: corrupt / malformed

- Per-notebook `.ingest-journal.json` and ImportRun execution journals/scratch must not be **silently discarded** when unreadable or schema-invalid.
- Required behaviour: **report** (doctor/CLI error) and **quarantine** (e.g. rename to `.ingest-journal.corrupt.<timestamp>` / move under `corpus/quarantine/`) leaving an audit trail.
- Automatic delete of unreadable journals is **non-conformant** for bulk-import generation safety. Recovery may roll back only when the journal is well-formed and indicates a non-`manifest_pending` incomplete state per [project-on-disk.md](project-on-disk.md).

## Relation to per-notebook ingest

ImportRun orchestrates many notebook-local commits. Each page/source commit still uses the existing stage → journal → promote → atomic `project.json` replace mechanism. ImportRun does not replace that journal; it records outcomes around it.

## Non-goals

- One filesystem transaction for an entire multi-thousand-page run
- Silent path-based resume when planned IDs are absent
- Offering `replace_source` in v1 policy IDs
