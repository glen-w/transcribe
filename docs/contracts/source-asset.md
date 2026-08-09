Type: CONTRACT
Authority: self — managed originals, fingerprints, provenance, duplicate taxonomy/policy, and source/page/render linkage invariants. Prospective **bulk-import generation** authority; activation gate in [notebook-corpus.md](notebook-corpus.md). Layout: [project-on-disk.md](project-on-disk.md). Import policies/runs: [import-run.md](import-run.md). Doctor checks: [corpus-integrity.md](corpus-integrity.md).

# Source assets

## Activation gate

Same gate as [notebook-corpus.md](notebook-corpus.md). Until activation, existing `SourceDocument` fields in `transcribe.project` v1 remain the shipped source model. This contract defines the durable semantics bulk import must obey and the integrity invariants notebook validation must grow to enforce (see Migration).

## Purpose

Every imported image/PDF is a **managed immutable original** plus provenance. Runtime authority after commit is the managed copy and its content hash—not the external path that happened to be scanned.

## Managed originals

- Import **copies** source bytes into the notebook’s managed `sources/` tree.
- External path/filename are **non-authoritative provenance only**. They may move or disappear between scan and resume; idempotency must not key off them.
- After commit, missing managed bytes (or fingerprint mismatch) is an integrity **error**, not a soft warning to re-read `/Volumes/...`.

## Identity vs fingerprint

| Concept | Role |
|---------|------|
| `source_id` | Immutable identity of the SourceAsset record |
| `sha256` | SHA-256 of the **imported source bytes** (JPEG/PNG/PDF as stored). Integrity + duplicate classification |
| External path/filename | Provenance display / audit only |

## Field semantics (aligned to current `SourceDocument`)

| Field | Status | Semantics |
|-------|--------|-----------|
| `source_id` | Required | UUID hex |
| `sha256` | Required | Content hash of managed source bytes |
| `media_type` | Required | e.g. `image/jpeg`, `image/png`, `application/pdf` |
| `original_filename` | Required today | Basename/provenance label from import |
| `stored_relpath` | Required | Managed path relative to notebook root |
| `page_count` | Required | Exact size of the represented within-source page set (see below) |
| `imported_at` | Required | Import timestamp |
| `render_dpi` | Required | DPI used when renders were produced for this source |
| `original_path` | **Optional / future** | Full external path provenance; absence is valid |
| `source_size_bytes` | **Optional / future** | Byte length at import; absence is valid |
| `import_run_id` | **Optional / nullable** | Set when created by an ImportRun; **must be null/absent for legacy sources** predating bulk-import generation |

### `bytes_present`

**Computed integrity state**, not persisted authoritative metadata. Doctor/deep validation reports whether the managed file exists and matches `sha256`. Do not store a stale `bytes_present: true` flag on the entity.

## PDF and page linkage

- **Do not** put `pdf_page_index` on the SourceAsset. One PDF SourceAsset owns **N** pages.
- Each page carries `source_id` + within-source `page_index`.
- `pdf_page_index` lives on **render provenance** (and may be mirrored in staging journals). Where a render was produced from a PDF page, invariant: `render.pdf_page_index == page.page_index` for that page’s active render lineage when the source `media_type` is `application/pdf`.
- For single-image sources, `page_index` is `0` and `pdf_page_index` is null/absent on renders.

## `page_count` and within-source indices

For each `source_id`:

1. Let `P` be the set of pages with that `source_id`.
2. `page_count` **must equal** `|P|`.
3. The set of `page_index` values in `P` **must be exactly** `{0, 1, …, page_count - 1}` (contiguous, starting at 0, no duplicates, no gaps).
4. `(source_id, page_index)` is unique across the notebook.

Current shipped validation that only compares counts is **insufficient**; contiguous unique indices are required by this contract (enforced when integrity updates land; see [corpus-integrity.md](corpus-integrity.md)).

## Page ↔ render integrity invariants

Within a notebook (normative; doctor/`validate_project` must enforce):

1. **Unique `(source_id, page_index)`** among pages.
2. **Active render belongs to the page’s source:** the active render’s provenance must reference the same `source_id` as the page (via render bookkeeping already stored: source hash linkage and path layout `pages/<source_id>/<page_index>/…`). Explicitly: `page.active_render_id` resolves; that render’s `source_sha256` equals the page’s SourceAsset `sha256`; render path containment uses the page’s `source_id` and `page_index`.
3. **`render.source_sha256 == SourceAsset.sha256`** for every render retained for pages of that source.
4. **PDF index coherence:** for PDF sources, every page’s `page_index` equals the corresponding render’s `pdf_page_index` when present; `page_count` matches PDF page set represented.
5. **Dimension coherence:** `page.width`/`page.height` equal the active render’s `width`/`height`.
6. **No unreferenced authoritative renders/sources** unless explicitly permitted as a documented soft state. Default: every `sources[]` entry is referenced by ≥1 page; every `renders` map entry is the active render of exactly one page **or** is retained under an explicit future multi-render policy. Until multi-render history is a product feature, unreferenced renders are doctor **errors** (or warnings only if a migration note marks them transitional—default error for bulk-import generation).

## Duplicate taxonomy

Classify before applying policy—never silently merge:

| Class | Meaning |
|-------|---------|
| `same_bytes_same_notebook` | SHA-256 already present as a SourceAsset in the **target** notebook |
| `same_bytes_other_notebook` | SHA-256 present in a **different** notebook’s sources |
| `same_filename_different_bytes` | Provenance name collides; hashes differ |
| `modified_replacement` | Prior path/fingerprint pair no longer matches bytes (detected; not auto-applied) |
| `pdf_page_duplicate_extract` | Plan would create a second page for an already-represented `(source, page_index)` |

## Duplicate policies (first bulk-import release)

Allowed policies (named on the ImportPlan / `import_policy_id`):

| Policy | Behaviour |
|--------|-----------|
| `skip_existing` | See precise definition below |
| `create_duplicate` | Always create new `source_id` / `page_id` / `render_id` even when hashes match |

**`replace_source` is out of policy** for the first bulk-import release. It must not be selectable; implementations must not offer silent replace.

### `skip_existing` (precise)

- **May skip** only when the candidate source SHA-256 already exists **in the target notebook** specified by the plan item (`same_bytes_same_notebook`).
- **Must not** silently skip because the same bytes exist in **another** notebook.
- Corpus-wide deduplication is allowed **only** when the plan explicitly sets a policy/flag requesting it (separate from default `skip_existing`). Default plans without that flag treat `same_bytes_other_notebook` as a distinct classification: either `create_duplicate` per policy or a validation finding—never an implicit skip.
- Skips are recorded on the ImportRun item outcome with the existing `source_id` / page IDs that caused the skip.

## Idempotency drivers

Idempotency keys for commit/resume are:

1. Immutable planned IDs (`plan_id`, `item_id`, preallocated `notebook_id` / `source_id` / `page_id` / `render_id`)
2. Source content `sha256`
3. `import_policy_id` + plan fingerprint equality ([import-run.md](import-run.md))

External paths and filenames **must not** drive idempotency.

## Migration rules (before writing new linkage fields)

Before any writer persists `import_run_id`, `original_path`, or `source_size_bytes` into `transcribe.project`:

| Decision (locked) | Rule |
|-------------------|------|
| Additive optional fields on schema_version **1** | `import_run_id`, `original_path`, `source_size_bytes` may be added as **optional** keys. Readers must treat absence/`null` as legacy-conformant. |
| No silent requiredness | Bulk-import writers may set them; OCR/review paths must not require them. |
| Schema bump reserved | Making any of these required, renaming `id`→`notebook_id` on the wire, or changing `page_count` semantics incompatibly requires `schema_version` bump and an explicit migration note—not drive-by implementation. |

Until migration writers ship, doctors must accept legacy sources with only today’s required fields.

## Non-goals

- Content-defined merging of near-duplicate images
- Deduplicating bytes into a global content-addressed blob store in v1 (notebook-local managed copies remain the unit)
- Using filename lexicography as identity
