Type: CONTRACT
Authority: self — detector definitions, scope, candidate strategy, and orchestration metadata

# Detection definition

A **DetectorDefinition** orchestrates scanning notebook content for phenomena. It references one or more **PromptDefinition** identities but is not equivalent to a saved prompt.

## Identity

| Field | Required | Notes |
|-------|----------|-------|
| `detector_id` | yes | Built-in (`poetry`) or `custom/<slug>` |
| `version` | yes | Bump on logic/schema/threshold changes |
| `title` | yes | Catalogue label |
| `description` | no | Human-readable summary |
| `prompt_ref` | when `engine=prompt` | `{prompt_id, version}` (v1: single ref); omitted for lexical counters |
| `engine` | no | `prompt` (default) \| `lexical_count` |
| `scope` | yes | `page` \| `page_window` \| `notebook` |
| `input_mode` | yes | `auto` \| `text` \| `vision` |
| `candidate_strategy` | yes | v1: `all_pages`; future heuristics |
| `window_size` | when window scope | Default 3 for adjacent-page detection |
| `window_overlap` | when window scope | Default 1 |
| `confidence_threshold` | yes | Post-validation filter (0–1) |
| `finding_type` | yes | Stable label namespace (`poetry`, `custom:<id>`) |
| `aggregation_strategy` | yes | `merge_adjacent_spans` \| `none` (per-page lexical counters) |
| `model_requirements` | no | May override prompt defaults |
| `extra_config` | no | Engine-specific (e.g. `lexical_matcher`, lexicon digest) |

## Built-in vs custom

- **Built-in detectors** ship in code registry (`transcribe.detection.registry`): `poetry`, `todo_lists`, `lists`, `quotations`, `beer_labels`, plus lexical counters `first_person` and `swear_words`.
- **Custom detectors** are declarative user definitions compiled to DetectorDefinition + constrained prompt. No arbitrary Python plugins in v1.
- **Lexical count detectors** (`engine=lexical_count`) match OCR text deterministically (no LLM). They emit one finding per page when the count is above `min_count`, with `detector_data.count` / `samples`.

## CustomDetectorDefinition (user-facing, declarative)

Approximate fields:

| Field | Notes |
|-------|-------|
| `name` | Display name |
| `instruction` | Phenomenon description (compiled into prompt data slot wrapper) |
| `scope` | `page` \| `notebook` (notebook enables adjacent-page windows) |
| `adjacent_page_detection` | bool |
| `model_mode` | `auto` \| `text` \| `vision` |
| `confidence_threshold` | float |

Compiled to `detector_id = custom/<slug>` with fixed response schema `custom_finding_v1`.

## Non-goals

- Detectors must not add boolean flags to `PageIndex` (e.g. `contains_poem`).
- Detectors must not be implemented solely as analysis modules when page/window scanning and cross-page spans are required.
- Auto-tag (opt-in) may **union** `normalize_slug(finding_type)` onto `PageIndex.tags` for pages in a finding span. That uses the existing tags list — it is not a boolean flag. Auto-tag is **not** part of `cache_config` / cache identity. See [tag-catalog.md](tag-catalog.md).
