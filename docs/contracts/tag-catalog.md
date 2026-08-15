Type: CONTRACT
Authority: self — organisation tag catalog wire format, slug/label/color identity, assignment rules, rewrite semantics, and the host-agnostic kernel copy-boundary. Assignment storage on Transcribe notebooks/pages remains `tags: string[]` in [project-on-disk.md](project-on-disk.md). Export snapshot: [notebook-export.md](notebook-export.md). Detection may *union* slugs onto pages but must not add boolean flags to `PageIndex` ([detection-definition.md](detection-definition.md)).

# Organisation tag catalog

Organisation tags are **library metadata** (notebook / page in Transcribe; transcript library items in TranscriptX). They are not analysis modules, not TX Groups, and not detection finding records.

## Copy-boundary (TranscriptX)

The kernel is host-agnostic stdlib:

- [`src/transcribe/tagging/kernel.py`](../../src/transcribe/tagging/kernel.py)
- [`src/transcribe/tagging/colors.py`](../../src/transcribe/tagging/colors.py)

Copy those two modules (keep relative imports). Do **not** copy `store.py` or `transcribe.services.tags`. Do not add a runtime dependency between Transcribe and TranscriptX. A shared PyPI package is deferred until after TranscriptX 1.0 ([INTEGRATION_SEAM.md](../INTEGRATION_SEAM.md)).

TX Theme F must **not** treat tags as Group membership. TX `tag_extraction` (analysis suggestions) is a different concept; it may *seed* slugs later but is not this catalog.

## Format

| Field | Value |
|-------|--------|
| `format` | `personal_corpus.tag-catalog` |
| `schema_version` | `1` |
| Transcribe location | `{TRANSCRIBE_DATA_DIR}/config/tag-catalog.json` |
| Writes | Atomic JSON replace under `{TRANSCRIBE_DATA_DIR}/config/.transcribe.tag-catalog.lock` |

```json
{
  "format": "personal_corpus.tag-catalog",
  "schema_version": 1,
  "updated_at": "2026-08-15T12:00:00.000Z",
  "tags": [
    {
      "tag_id": "uuid-hex",
      "slug": "poetry",
      "label": "Poetry",
      "color": "#1d76db",
      "created_at": "2026-08-15T12:00:00.000Z",
      "updated_at": "2026-08-15T12:00:00.000Z"
    }
  ]
}
```

## Identity

| Field | Role |
|-------|------|
| `tag_id` | Stable UUID hex. Rename/recolor never change it. |
| `slug` | Assignment key. Normalized: trim, lowercase, collapse whitespace, unique in the catalog. Stored on entities as `tags: string[]`. |
| `label` | Display name. **Rename edits label only** — assignments keep the slug. |
| `color` | Canonical `#rrggbb`. Uncatalogued slugs get a deterministic palette colour from the slug hash. |

Changing a slug (or merge/delete) is an explicit **rewrite plan** `{from_slug → to_slug \| null}` that hosts apply to every assignment list. `null` drops the slug.

## Assignments (hosts)

- Transcribe: `Project.tags` (notebook) and `PageIndex.tags` (page) remain `string[]` of slugs. `transcribe.project` schema_version **1** is unchanged.
- Unknown / orphan slugs on disk stay valid. Display uses the slug as label plus the hashed default colour until `ensure` creates a catalog row.
- `content_revision` hashes page tag **slugs** only. Label/colour catalog edits must not bump export identity.

## Fail-closed load (Transcribe store)

Missing file → empty in-memory catalog (normal first run); first save creates the file.

Corrupt JSON, non-object, unknown/`schema_version` ≠ 1, or `format` ≠ `personal_corpus.tag-catalog` → empty in-memory catalog, **file preserved**, bounded diagnostic. Load must not raise into Library / viewer / Archive.

## Operations

| Op | Catalog | Assignments |
|----|---------|-------------|
| ensure | create if slug missing | unchanged |
| rename label | label + `updated_at` | unchanged |
| recolor | color + `updated_at` | unchanged |
| change slug | slug unique; rewrite plan old→new | host corpus rewrite |
| merge A→B | drop A; rewrite A.slug→B.slug | host corpus rewrite |
| delete | drop row; rewrite slug→null | host corpus rewrite |

Filter: **AND** over required slugs (viewer click-to-constrain and Archive page-tag filter). Notebook tags classify the notebook; they do not constrain pages inside the viewer.

## Non-goals (v1)

- Hierarchies / nested tags
- SQLite as system of record
- Dual authority (sidecar provenance vs `tags[]`) — assignments stay `string[]`
- Detector booleans on `PageIndex` (`contains_poem`)
- Auto-removing tags when detection findings disappear (auto-tag is additive)

## Detection auto-tag (Transcribe host)

Opt-in, **not** part of detector `cache_config` / cache identity. After a successful publish (or from already-published findings), union `normalize_slug(finding_type)` onto every page in each finding span. Skip `rejected` findings. Re-running with auto-tag on re-adds a slug the user removed; turn the checkbox off to stop.

Transcribe prefs file `{TRANSCRIBE_DATA_DIR}/config/detection-auto-tag.json` (`format: transcribe.detection-auto-tag`, schema 1) stores per-detector defaults. It is not fingerprint-relevant.
