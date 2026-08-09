Type: CONTRACT
Authority: self — canonical analysis input schema, validation, `source_ref` form, span indexing, and content fingerprint construction

# Analysis document

Canonical input to ported analysis modules. Built by Transcribe adapters from a managed notebook project. Cores consume this document only — never `Page` objects, Streamlit state, or filesystem paths.

On-disk project layout: [project-on-disk.md](project-on-disk.md). Effective page text: [page-result.md](page-result.md). Result envelopes: [analysis-result.md](analysis-result.md). Storage: [analysis-run-storage.md](analysis-run-storage.md). Eligibility: [notebook-eligibility.md](notebook-eligibility.md).

## Identity

- `format` must be `"transcribe.analysis-document"`
- `schema_version` must be `1` for this contract
- Unsupported `schema_version` → refuse (no silent upgrade)
- This schema is **frozen for the core set**: adapters and ports must not invent alternate document shapes. Schema changes require a new `schema_version` and an explicit contract revision.

## Schema (v1)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `document_id` | string | yes | Stable id for this analysis view; **must equal** the project’s `project_id` for notebook-scoped core runs |
| `text` | string | yes | Document-level text (see concatenation rules) — **canonical** representation for document-level modules |
| `units` | array | yes | Ordered analysis units (may be empty only transiently before refusal; see validation) |
| `granularity_version` | string | yes | Version id of the unit-splitting rules used |
| `split_profile` | string | yes | Named split profile (`page` or `paragraph_v1` in the core set) |

Each unit:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `unit_id` | string | yes | Stable id (never array index alone); unique within `units` |
| `text` | string | yes | Exact effective text for this unit; must be a non-empty string (adapters omit blank pages — never emit empty units) |
| `order` | number | yes | Chronology key; finite and ≥ 0 |
| `date` | string \| null | no | When present: ISO-8601 **date only** (`YYYY-MM-DD`). When absent: JSON `null` (or omit then normalize to `null` in fingerprints). Absence **must not** invent wall-clock timestamps |
| `source_ref` | object | yes | Validated Transcribe back-pointer (below); opaque to cores |

### Uniqueness and ordering guarantees

- `document_id` is unique per managed project analysis view (core: one document id per `project_id`)
- `unit_id` values are unique within a document (`duplicate_unit_id` if not)
- `units` **must** be strictly sorted by `(order, unit_id)` ascending
- Analysis cores consume units in array order; `order` is chronology, not identity
- Same inputs + same `granularity_version` + same `split_profile` ⇒ same `unit_id` set and same offsets

### Unit id rules

- Page unit: `unit_id == page_id` (project-stable page identity)
- Derived paragraph/span unit: `"{page_id}/span:{start}-{end}"` where `start`/`end` are character offsets into that page’s effective text after the versioned splitter identified by `granularity_version` + `split_profile`
- Same page effective text + same splitter identity ⇒ same ids across reopen/rerun; edit / reorder / include-exclude changes ids or membership predictably

### Document `text` concatenation (reproducible)

For `schema_version` 1, document `text` is the **sole canonical** document-level string:

1. Sort units by `(order, unit_id)`
2. Join unit `text` values with a single newline (`\n`)
3. Do not trim unit texts; do not insert extra blank lines beyond the single separator
4. The stored `text` field must equal this concatenation exactly (adapters must not carry a divergent document string)

## Validation / refusal

Refuse with named errors (no silent repair of ids or order):

| Error | Condition |
|-------|-----------|
| `empty_document_text` | `text` is empty (includes zero-unit documents) |
| `empty_unit_text` | any unit `text` is empty |
| `missing_unit_id` | unit lacks `unit_id` |
| `duplicate_unit_id` | duplicate `unit_id` in `units` |
| `invalid_order` | `order` non-finite or negative |
| `units_not_sorted` | `units` not strictly sorted by `(order, unit_id)` |
| `text_mismatch` | `text` ≠ concatenation rule above |
| `invalid_date` | `date` present and not `YYYY-MM-DD` |
| `invalid_source_ref` | fails `source_ref` validation |
| `unsupported_schema_version` | unknown version |
| `unsupported_split_profile` | `split_profile` not in the frozen core set below |

Analysis consumes units in array order (already sorted by `(order, unit_id)`). `order` is chronology, not identity.

## Excluded pages, blank text, failed OCR

Adapters build `units` from the managed project. Normative membership:

| Page situation | Adapter behaviour |
|----------------|-------------------|
| Page marked **excluded** from analysis | Omit from `units` entirely (never emit a unit for that `page_id`) |
| Included page with **empty or whitespace-only** effective text (blank OCR, empty edit, failed attempt with no usable `raw_text` and no edit) | Omit from `units` — do **not** emit empty units |
| Included page with non-empty effective text | Emit unit(s) per `split_profile` |
| Active OCR attempt `failed` / `interrupted` / `cancelled` but a prior edit or usable active raw text exists | Use effective text per [page-result.md](page-result.md); failure status alone does not exclude the page |

If omission yields zero units → document validation fails with `empty_document_text`; callers map that to analysis-result `insufficient_data` (or `skipped_not_applicable` when an eligibility policy produced an empty eligible set — see [notebook-eligibility.md](notebook-eligibility.md)).

## Frozen core split profiles

The core set admits only these `split_profile` values. New profiles require a contract bump of `granularity_version` and explicit documentation — they are **not** free implementation choices once results and citations persist.

### `split_profile: "page"` (`granularity_version: "page_v1"`)

`page` profile canonicalisation (exact):

- Walk manifest `pages` in order; skip `analysis_excluded` pages and blank/whitespace-only / failed-empty effective text
- One unit per remaining page; `unit_id == page_id`
- `source_ref`: `{"kind":"page","page_id":...}`
- `order`: 0-based index among **emitted** units (not raw manifest index of omitted pages)
- `text`: exact effective text code points as stored — **no** NFC/NFKC rewrite
- `date`: `YYYY-MM-DD` only when the page has a day-precision user date; otherwise `null`
- Document `text` = join of unit texts with a single `\n`
- Content fingerprint includes only contract fingerprint fields — not project title/tags/cover/OCR settings
- Reject non-string texts and strings containing unpaired surrogates at validation

### `split_profile: "paragraph_v1"` (`granularity_version: "paragraph_v1"`)

Deterministic, identity-preserving paragraph derivation (required before Moments / highlights / QA evidence ports that use span units):

1. For each included page with non-empty effective text `T`, find split points at every run of **two or more** consecutive `\n` characters (blank-line separated blocks)
2. Each block is the half-open substring `T[start:end]` with leading/trailing `\n` from the separator run excluded from the block; do not otherwise trim interior whitespace
3. If no blank-line separator exists, the whole `T` is a single block `[0, len(T))`
4. Skip blocks whose text is empty or whitespace-only
5. `unit_id = "{page_id}/span:{start}-{end}"` with `start`/`end` those offsets into `T`
- `source_ref`: `{"kind":"page_span","page_id":...,"char_start":start,"char_end":end}`
- `order`: `(page_order * 1_000_000) + start` (stable, chronology-preserving across pages)
- `text`: exact substring `T[start:end]`

Derived units must remain resolvable after reopen: stable ids + `source_ref` offsets into the fingerprinted page effective text.

## `source_ref` (adapter/storage boundary; opaque to cores)

Analysis cores must treat `source_ref` as opaque and must not parse it.

Transcribe adapters **must** emit a validated durable form before persistence or UI navigation. Unconstrained strings are non-conformant.

### Allowed forms (v1)

**Page**

```json
{"kind": "page", "page_id": "<page_id>"}
```

**Span on page** (offsets into that page’s effective text)

```json
{"kind": "page_span", "page_id": "<page_id>", "char_start": 0, "char_end": 10}
```

### Validation at adapter/storage write

- `kind` ∈ `{page, page_span}`; unknown `kind` → refuse
- `page_id` must exist in the project manifest
- For `page_span`: `char_start` / `char_end` integers; `0 ≤ char_start ≤ char_end ≤ len(page_effective_text)`; half-open interval
- Required keys only; reject extra required-unknown shapes

UI navigation depends on this validated form.

## Span indexing convention

Character offsets are **zero-based, half-open** `[char_start, char_end)` indices into the exact Unicode string stored as:

- the unit’s `units[].text` when citing within a unit, or
- the page effective text when `source_ref.kind == "page_span"`

Indexing is Python `str` code-point indices (not UTF-8 byte offsets). Offsets must not be interpreted against a different normalization, a concatenated document string (unless the unit text is that string), or post-edit page text without rebuilding the `AnalysisDocument` and content fingerprint.

## Effective text source (canonical representation)

- Page units use project **effective text** per [page-result.md](page-result.md): `edited_text` if not null, else active attempt `raw_text`
- Span units use the exact substring of that page effective text selected by the versioned splitter
- Included-unit set is exactly `units` membership (excluded and blank/failed-empty pages omitted)
- **Canonical text for analysis** is always this effective text (and derived substrings / document concatenation). Adapters must not silently substitute OCR confidence strings, raw-only text when an edit exists, or display-normalized variants
- After any edit, reorder, include/exclude, or OCR change that alters effective text, adapters **must** rebuild the `AnalysisDocument` and content fingerprint before citing or caching results against it

## Canonical content fingerprint (`content_fingerprint_version: 1`)

Content fingerprints are **normative** — not implementation-defined. Analysis-run-storage composes cache identity using this value and must not invent a second content-hash meaning.

### Algorithm

1. Build a canonical object containing only fingerprint-relevant fields, with **sorted keys at every object level**:

```text
{
  "content_fingerprint_version": 1,
  "document_id": "...",
  "granularity_version": "...",
  "split_profile": "...",
  "text": "...",
  "units": [
    {
      "date": null | "YYYY-MM-DD",
      "order": <number>,
      "source_ref": { ... canonical object with sorted keys ... },
      "text": "...",
      "unit_id": "..."
    },
    ...
  ]
}
```

2. `units` must already be sorted by `(order, unit_id)` (validation ensures this).
3. `date`: JSON `null` if absent; otherwise normalized `YYYY-MM-DD`.
4. Serialize as UTF-8 JSON with sorted object keys and **no insignificant whitespace** (compact separators).
5. `content_fingerprint` = lowercase hex SHA-256 of that UTF-8 byte string.

Same logical document ⇒ same fingerprint across processes and languages that implement this serialization.
