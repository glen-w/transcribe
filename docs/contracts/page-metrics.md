Type: CONTRACT
Authority: self — page ink/blankness/hue metrics schema, cache identity, and publish rules. Top-level project paths: [project-on-disk.md](project-on-disk.md). Does not redefine analysis or detection envelopes.

# Page metrics (ink / blankness / hue)

Deterministic **Pillow-only** visual metrics over each page’s **active render** PNG. Separate from text Analyse modules ([analysis-document.md](analysis-document.md)) and from visual declutter ([source-asset.md](source-asset.md) declutter provenance).

## Identity

- `format` must be `"transcribe.page-metrics"`
- `schema_version` must be `1` for this contract
- Unsupported `schema_version` → refuse (no silent upgrade)

## Ownership and layout

| Path | Role |
|------|------|
| `page_metrics/published.json` | Current published notebook metrics (optional until first write) |

- Creating `page_metrics/` on first write is **not** a project-layout migration; absence remains conformant.
- Authoritative outputs are **project-local** under `page_metrics/` — never workspace archive SQLite.
- Cores/algorithm functions are pure over image bytes; the service owns filesystem I/O and publish.

## Published document schema (v1)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `format` | string | yes | `"transcribe.page-metrics"` |
| `schema_version` | number | yes | `1` |
| `project_id` | string | yes | Must equal `project.json` id |
| `algorithm_version` | string | yes | Frozen algorithm id (e.g. `"1"`) |
| `cache_identity` | string | yes | Hex SHA-256 of identity payload (below) |
| `outcome` | string | yes | `success` \| `insufficient_data` |
| `computed_at` | string | yes | ISO-8601 UTC timestamp |
| `rollup` | object | yes | Notebook aggregates (may be empty when insufficient) |
| `pages` | array | yes | Ordered per-page rows (project page order) |

### Per-page row

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `page_id` | string | yes | Project-stable page id |
| `render_id` | string | yes | Active render id used |
| `render_sha256` | string | yes | `rendered_image_sha256` from render provenance |
| `ink_coverage_pct` | number | yes | 0–100; fraction of pixels classified as ink |
| `blankness_pct` | number | yes | `100 - ink_coverage_pct` (rounded consistently) |
| `ink_hue` | string | yes | Dominant label: `black` \| `blue` \| `red` \| `brown` \| `green` \| `other` \| `mixed` \| `none` |
| `ink_hue_degrees` | number \| null | no | Peak hue in degrees when chromatic; else `null` |
| `paper_tone` | string | yes | Coarse paper hint: `white` \| `cream` \| `grey` \| `warm` \| `cool` \| `unknown` |
| `width` | number | yes | Analysed pixel width (after optional downsample) |
| `height` | number | yes | Analysed pixel height |
| `pixel_count` | number | yes | Pixels considered |
| `ink_pixel_count` | number | yes | Ink-classified pixels |

### Rollup object

| Field | Type | Notes |
|-------|------|-------|
| `page_count` | number | Rows in `pages` |
| `mean_ink_coverage_pct` | number \| null | Arithmetic mean; `null` if no pages |
| `median_ink_coverage_pct` | number \| null | Median; `null` if no pages |
| `mean_blankness_pct` | number \| null | |
| `hue_counts` | object | Map label → count of pages with that dominant `ink_hue` |

## Cache identity

Hex SHA-256 of canonical JSON:

```
{
  "algorithm_version": "<string>",
  "project_id": "<id>",
  "pages": [
    { "page_id": "<id>", "render_sha256": "<hex>" },
    ...
  ]
}
```

- `pages` follows **project page order** among measurable pages (resolvable active render).
- The notebook’s explicit `cover_page_id` (when set) is **omitted** from identity, `pages`, and rollups — covers are not treated as ink/paper content. Unset `cover_page_id` does **not** imply first-page exclusion (display/Open may still fall back to the first page).
- Pages whose active render file is missing are omitted from identity and from `pages` (service may warn); identity still reflects only successfully measured pages.
- Changing algorithm version, page set (including cover designation), order, or any active render SHA invalidates the published artifact.

## Outcomes

| Situation | `outcome` |
|-----------|-----------|
| At least one non-cover page measured | `success` |
| Project has no pages / no measurable renders / only the explicit cover is measurable | `insufficient_data` (`pages` empty, rollup zeros/nulls) |

## Atomicity

- Publish via `write_json_atomic` to `page_metrics/published.json`.
- Do not hold long compute under `mutation_lock`; short lock only if coordinating with other RMW writers (optional for this lane).
- Stale published file (identity mismatch) must not be treated as fresh — recompute and replace.

## Non-goals

- Not an Analyse text module; not part of presets or `AnalysisDocument`.
- Not OCR preprocess or declutter; does not rewrite page pixels.
- No OpenCV / ML segmentation in v1.
