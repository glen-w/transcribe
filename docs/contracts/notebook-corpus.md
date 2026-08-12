Type: CONTRACT
Authority: self — corpus hierarchy, notebook identity, ownership, ordering, corpus index wire format, and workspace locking. **Runtime-normative** for bulk-import generation (activation gate satisfied). Layout paths subordinate to this contract are described in [project-on-disk.md](project-on-disk.md). Source bytes/provenance: [source-asset.md](source-asset.md). Import lifecycle: [import-run.md](import-run.md). Integrity/doctor: [corpus-integrity.md](corpus-integrity.md).

# Notebook corpus

## Activation gate

This contract is **runtime-normative** for the bulk-import generation. The gate below is **satisfied** (corpus index, ImportRun/plan orchestration, lock order, corpus doctor checks, and [acceptance suite](corpus-integrity.md#acceptance-gate) green).

Shipped together:

1. Durable corpus index (`transcribe.corpus-index`) with atomic writers
2. `ImportRun` / `ImportPlan` persistence and commit orchestration
3. Corpus lock + lock-order enforcement
4. Corpus doctor checks listed in [corpus-integrity.md](corpus-integrity.md)
5. Acceptance suite green per [corpus-integrity.md](corpus-integrity.md#acceptance-gate)

**`transcribe.project` schema_version `1` remains fully conformant** without a corpus index: implementations must not require a corpus index to load, OCR, analyse, or export existing notebooks. New writers must not break v1 projects that lack corpus registration. Absence of `corpus-index.json` in a workspace means bulk-import is not yet used there; legacy discovery of `project.json` children continues.

This document (with [source-asset.md](source-asset.md), [import-run.md](import-run.md), [corpus-integrity.md](corpus-integrity.md)) owns identity, ownership, ordering, and workspace corpus authority. [project-on-disk.md](project-on-disk.md) remains sole authority for **per-notebook directory layout** and per-notebook ingest journal/locks.

## Purpose

Transcribe is a durable **notebook corpus**. OCR, analysis, thumbs, and archive search are derived processes. An imported page is an archival object: once committed, its identity, managed original, human edits, OCR history, and notebook membership survive renames, folder moves, OCR model changes, analysis modules, and UI changes.

## Hierarchy

```text
Corpus (workspace)
  └── Notebook (notebook_id ≡ project.id)
        └── Page (page_id)
              ├── SourceAsset (source_id)     # primary imported bytes; PDF may back N pages
              ├── Render(s) (render_id)      # derived display pixels
              └── OCR attempts / edits       # page-result
        └── Analysis artifacts               # derived under analysis/
```

Product language “Project → Notebook” maps to **Corpus → Notebook** here so it does not collide with wire format `transcribe.project`.

## Identity

| ID | Rules |
|----|--------|
| `notebook_id` | Generated UUID hex; immutable; never reconstructed from folder name, filename, title, or path |
| `page_id` | Generated UUID hex; immutable; never reconstructed from paths |
| `source_id` / `render_id` | Generated UUID hex; immutable |

**Wire alias:** In `transcribe.project` v1, the field is `id`. Domain name is `notebook_id`. Invariant wherever both appear: `notebook_id == project.id`. Renaming “Notebook 17” → “Paris 2019” changes metadata only.

**Filesystem layout is non-contractual for identity.** Directory names under the projects root are implementation locators only. Domain IDs and the corpus index are authoritative for “which notebook exists” and “where it is managed.”

## Ownership

- A page belongs to **exactly one** notebook.
- A `SourceAsset` belongs to exactly one notebook and backs one or more pages of that notebook.
- A single-image import creates one source and one page. A PDF import creates **one** source and **N** pages (N = represented within-source page set).
- OCR attempts and analysis artifacts are owned by the notebook (via `page_id` / project-local `analysis/`).
- Loose arrays of unrelated page records outside a notebook entity are non-conformant.

## Ordering (chosen representation)

| Scope | Authoritative representation |
|-------|------------------------------|
| Pages within a notebook | **`project.pages` list order** in `project.json`. Position = list index. Reorder permutes the list only; never changes `page_id`. |
| Notebooks within the corpus | **`entries` list order** in the corpus index. Position = list index. Reorder permutes the list only; never changes `notebook_id`. |

Do **not** use parallel explicit ordinal integers as a second authority. Derived displays may show 1-based positions; they must recompute from list order.

`page_index` on a page is **within-source** identity/order (image → `0`; PDF → PDF page index), **not** the notebook’s global page order. Global notebook order is solely `project.pages` list order.

## Corpus index wire contract

Durable workspace document that locates managed notebooks without treating folder names as identity.

| Field | Value |
|-------|--------|
| `format` | `transcribe.corpus-index` |
| `schema_version` | `1` |
| Location | `{TRANSCRIBE_DATA_DIR}/corpus/corpus-index.json` (create parent dirs on first write) |
| Writes | Atomic replace only (temp → fsync → `os.replace` → directory fsync), under the corpus lock |

### Document shape

```text
{
  "format": "transcribe.corpus-index",
  "schema_version": 1,
  "updated_at": "<ISO-8601>",
  "entries": [
    {
      "notebook_id": "<uuid-hex>",
      "managed_relpath": "<path relative to TRANSCRIBE_PROJECTS_DIR>",
      "registered_at": "<ISO-8601>",
      "updated_at": "<ISO-8601>"
    }
  ]
}
```

### Entry rules

- `entries` list order is the authoritative notebook order.
- `notebook_id` must equal `project.id` inside the managed notebook’s `project.json`.
- `managed_relpath` is a **mutable locator** (may change if the directory is moved within the projects root). It must stay path-contained under `TRANSCRIBE_PROJECTS_DIR` and must resolve to a directory containing a valid `project.json`.
- Duplicate `notebook_id` values are invalid.
- Duplicate `managed_relpath` values are invalid.
- Absence of the corpus index file means bulk import has not been used in that workspace yet; legacy discovery of `project.json` children continues. When the index is present, it is the durable locator set.

### What the index is not

- Not a search/timeline cache (that remains disposable archive SQLite).
- Not a substitute for notebook entity records.
- Not authoritative for page order, OCR, or analysis.

## Workspace locking and lock order

| Lock | Path / scope |
|------|----------------|
| Corpus lock | `{TRANSCRIBE_DATA_DIR}/corpus/.corpus.lock` — corpus index, ImportRun registry mutations, notebook registration |
| Notebook mutation lock | `<notebook>/.transcribe.lock` — `project.json`, sources/renders promote, page results, analysis RMW (existing) |

**Lock order (mandatory):** always acquire **corpus lock → notebook mutation lock**. Never acquire in reverse. Never hold two notebook mutation locks while taking the corpus lock in between in a way that inverts order.

**Serialization:** commits that target the same `notebook_id` must be serialized (one active ingest transaction per notebook; see [import-run.md](import-run.md) and the single `.ingest-journal.json` rule in [project-on-disk.md](project-on-disk.md)). Distinct notebooks may commit concurrently only if each holds its own mutation lock and the corpus lock is not held across long per-notebook work—corpus lock critical sections must stay short (index/run-registry RMW only).

## Human metadata protection

Generalize the `date_approved` pattern:

- Machine processes (import, OCR, re-analysis) may populate **unapproved** suggestions.
- Approved human corrections must not be silently overwritten.
- v1 normative field set: page diary `date` / `date_approved` / `date_source` (existing). Title/tags/future fields should reuse the same approved-vs-machine shape when added; do not invent one-off silent overwrite rules.

## Authoritative vs derived

| Authoritative | Derived / disposable |
|---------------|----------------------|
| `project.json` entity + ordered pages | Archive SQLite / FTS |
| Managed source bytes + fingerprints | Thumbnails, `.cache/**` |
| Page results (OCR history, edits) | Library summary projections |
| Corpus index entries + order | Directory names as UX labels |
| ImportRun / ImportPlan records | |
| Human-approved metadata | |

Indexes and caches may be rebuilt; IDs, provenance, approved metadata, OCR history, and ImportRun history must never be reconstructed by guessing.

## Non-goals

- Nested multi-notebook containers inside one `project.json`
- Treating external scan folders as the durable unit
- Reconstructing `notebook_id` / `page_id` from paths
- Deserializing full OCR/analysis payloads merely to show the Library
