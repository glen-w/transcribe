Type: CONTRACT
Authority: self — corpus/notebook integrity invariants, doctor scopes, repair/rebuild boundaries, migration enforcement points, and the executable acceptance gate for bulk-import generation. **Runtime-normative**; activation gate in [notebook-corpus.md](notebook-corpus.md). Peers: [source-asset.md](source-asset.md), [import-run.md](import-run.md), [project-on-disk.md](project-on-disk.md).

# Corpus integrity

## Activation gate

Same gate as [notebook-corpus.md](notebook-corpus.md) — **satisfied**. Notebook-local and corpus-wide doctor checks below are required; the acceptance suite is the executable bar for supported bulk-import UI/CLI.

## Doctor scopes

| Scope | Responsibility |
|-------|----------------|
| Notebook doctor | Extend today’s per-project `DoctorService`: structural + deep hash + source/render invariants in this contract |
| Corpus doctor | Workspace-wide: corpus index, ImportRuns, cross-notebook ID uniqueness, locator containment |

Both may run offline. Deep mode rehashes managed source and render bytes.

## Notebook invariants

In addition to existing `validate_project` / page-result checks, enforce:

1. Unique `page_id`, `source_id`, `render_id` within the notebook
2. Unique `(source_id, page_index)` among pages
3. For each source: pages’ `page_index` set equals `{0..page_count-1}` and `|pages| == page_count`
4. Every `page.active_render_id` resolves; active render belongs to the page’s source; `render.source_sha256 == SourceAsset.sha256`
5. PDF coherence: when `media_type` is PDF, render `pdf_page_index` (when present) equals `page.page_index`
6. `page.width`/`height` equal active render dimensions
7. Managed source/render files exist (and match hashes in deep mode)
8. No orphan page-result files without a page (warning or error per existing practice); no unreferenced authoritative source/render records ([source-asset.md](source-asset.md))
9. Approved date metadata satisfies existing date invariants
10. Well-formed ingest journal or quarantined corrupt journal — never silent delete ([import-run.md](import-run.md))

## Corpus invariants

1. Every corpus index `notebook_id` loads a `project.json` whose `id == notebook_id`
2. Every index `managed_relpath` is unique, contained under `TRANSCRIBE_PROJECTS_DIR`, and resolves
3. **`notebook_id` uniqueness** across the corpus index
4. **Global uniqueness** of `page_id`, `source_id`, and `render_id` across all registered notebooks (IDs are corpus-wide capable; collisions are errors even if folders differ)
5. Index entry order is well-formed (list); no duplicate entries
6. ImportRun files that claim committed IDs: those IDs resolve in the cited notebook, or the item is explicitly `skipped`/`failed` with recorded reason
7. At most one live `.ingest-journal.json` interpretation per notebook; corrupt journals quarantined and reported
8. Corpus lock / notebook lock order is an implementation duty; doctor does not prove lock order but may flag concurrent-journal anomalies

## Repair and rebuild boundaries

| May rebuild / delete-and-recreate | Must never guess-rebuild |
|----------------------------------|---------------------------|
| Archive SQLite / FTS | `notebook_id`, `page_id`, `source_id`, `render_id` |
| Thumbnails / `.cache/**` | Human-approved metadata |
| Disposable Library summary projections | Provenance, OCR attempt history, edits |
| Optional ImportRun registry index file (from run files) | Managed source bytes |
| | ImportRun immutable plan bodies and committed item outcomes |
| | Corpus index entries (may **re-register** a known `project.json` only via explicit recovery that reads `project.id`, never invents IDs) |

Supported recovery paths must leave **doctor green** (or only documented warnings) when completed successfully.

## Migration enforcement

Before writers emit optional SourceAsset linkage fields or ImportRun IDs into `transcribe.project`:

- Follow additive optional v1 rules in [source-asset.md](source-asset.md#migration-rules-before-writing-new-linkage-fields)
- Doctors must accept legacy sources without `import_run_id` / `original_path` / `source_size_bytes`
- After writers ship, doctors may warn on committed ImportRun items whose sources lack `import_run_id` only when policy requires linkage for that generation—default: warn, do not invalidate legacy notebooks

## Acceptance gate (executable)

**Bulk-import implementation is supported** (UI and CLI bulk paths) when the synthetic multi-notebook corpus suite passes all of the following — and that suite is green:

1. **Deterministic crash-injection** at each boundary in [import-run.md](import-run.md#crash--recovery-boundaries) (corpus registration, notebook creation, source promotion, render promotion, `project.json` commit, ImportRun item commit, final run-state commit), with resume producing the authoritative winner and no duplicate committed IDs
2. **Retry / idempotency** under exact `plan_id` + `plan_fingerprint` + `import_policy_id` equality: second commit is a no-op for committed items; failed items may progress without regenerating IDs
3. **Duplicate policy**: `skip_existing` skips only same SHA in the **target** notebook; same bytes in another notebook are not silently skipped without explicit corpus-wide dedupe in the plan; `create_duplicate` always allocates the preallocated distinct IDs
4. **Corpus-index corruption / rebuild**: corrupt index quarantined/reported; recovery re-registers from authoritative `project.json` IDs without inventing new `notebook_id`s; locator uniqueness restored
5. **Deep doctor** green (or documented warnings only) after every supported recovery path on the synthetic corpus. Retained quarantine artifacts after a successful index rebuild are **warnings** (`corpus_quarantine_present`), not errors — operators may delete them after review.
6. Fixture coverage includes: many notebooks × many pages, duplicate bytes, renamed external files, interrupted imports, missing managed sources, reordered pages, failed OCR, re-import, legacy schema v1 notebooks, Unicode/weird filenames, PDF split provenance, ordering ambiguity refused at validate, malformed journal quarantine. Cancel paths must distinguish `cancelled` vs `cancelled_with_commits` without rolling back committed items.

**Acceptance bar:** no page identity loss; no silent overwrite of approved human metadata; deterministic resume; doctor green (warnings-only allowed for documented quarantine retention) after every supported recovery path.

## Non-goals

- Automatic healing that invents missing IDs or approved metadata
- Treating archive SQLite as an authority to repair notebooks from
- Shipping bulk import behind a feature flag without this suite green (gate is closed; suite must remain green)
