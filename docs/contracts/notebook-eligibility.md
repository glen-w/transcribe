Type: CONTRACT
Authority: self — normative `notebook_eligibility_v1` policy inputs, outputs, versioning, and cache-identity contribution. Sole Wave 1 compatibility policy replacing TranscriptX `insight_eligibility`.

# Notebook eligibility

**Wave 1 compatibility policy name:** `notebook_eligibility_v1`

This is the **only** permitted stand-in for TranscriptX `insight_eligibility` in Wave 1. Ports must not invent per-module eligibility stubs, softeners, or silent bypasses. Modules that TX gated with `insight_eligibility` either:

1. **Invoke this policy** (required list below), or
2. Are **explicitly ungated** in this contract (documented deliberate choice), or
3. Use a **named notebook-native substitute** recorded here or in the pin row’s `semantic_delta` (e.g. `moments` salience fork — not an eligibility stub)

Used with [analysis-document.md](analysis-document.md). Contributes to cache identity via [analysis-run-storage.md](analysis-run-storage.md). Outcomes: [analysis-result.md](analysis-result.md).

## Identity

| Field | Value |
|-------|-------|
| `policy_id` | `notebook_eligibility_v1` |
| `policy_version` | `1` |

## Purpose

Decide which analysis units are eligible for modules that must not run on empty, excluded, or trivially non-content units.

## Deterministic inputs

| Input | Notes |
|-------|-------|
| Candidate `units[]` | From the adapter’s pre-eligibility unit list (same id/text/order/date/source_ref rules as analysis-document) |
| Per-page include flag | Page excluded from analysis ⇒ units for that `page_id` are ineligible (`reason: excluded`) |
| Effective texts | Already reflected in unit `text` (edited vs raw per page-result) |

No randomness. No I/O. No Speakers. No wall-clock.

## Deterministic outputs

```text
{
  "policy_id": "notebook_eligibility_v1",
  "policy_version": "1",
  "eligible_unit_ids": ["...", "..."],  // sorted ascending
  "decisions": [
    {
      "unit_id": "...",
      "eligible": true | false,
      "reason": "ok" | "excluded" | "empty_or_whitespace" | "too_short"
    },
    ...
  ]
}
```

`decisions` sorted by `unit_id` ascending. `eligible_unit_ids` is exactly the set of decisions with `eligible: true`, sorted.

### Rules (`policy_version` 1)

Evaluate each unit in isolation:

| Reason | Condition | Eligible |
|--------|-----------|----------|
| `excluded` | Backing page marked excluded from analysis | no |
| `empty_or_whitespace` | `unit.text` empty or only Unicode whitespace | no |
| `too_short` | After whitespace-trim, character length < 3 | no |
| `ok` | otherwise | yes |

If **no** units are eligible → modules that require this policy conclude `outcome: skipped_not_applicable` (see analysis-result edge-case table).

## Modules that must invoke this policy

These modules must call `notebook_eligibility_v1` and build their `AnalysisDocument.units` from the eligible set only (or equivalently filter before fingerprinting the document they persist):

- `keyphrases`
- `topic_modeling`
- `bertopic`
- `highlights`
- `insights`

## Explicit Wave 1 resolutions (no ad-hoc stubs)

| Module / path | Policy |
|---------------|--------|
| `keyphrases`, `topic_modeling`, `bertopic`, `highlights`, `insights` | **Required:** `notebook_eligibility_v1` |
| `wordclouds` (base) | **Ungated** relative to TX insight eligibility — runs on document text / units after blank+excluded omission |
| `wordclouds` + keyphrase enrichment | Optional parent `keyphrases` only when that parent is a compatible published `success`; otherwise baseline token cloud ([analysis-run-storage.md](analysis-run-storage.md)) |
| `moments` | **Not** an eligibility bypass — notebook-native salience **fork** (no TX `momentum`); does not call `notebook_eligibility_v1` unless a future contract version adds it |
| `stats`, `lexical_diversity`, `understandability`, `ner`, `sentiment`, `entity_sentiment`, `epistemic_markers`, `semantic_similarity`, `topic_shift`, emotion family, `affect_tension`, LLM suite | **Ungated** by this policy in Wave 1 (blank/excluded pages still omitted by the adapter per analysis-document) |

## Compatibility tests (required)

Implementation must include tests that:

1. Each required module invokes `notebook_eligibility_v1` (not a private filter)
2. Empty / whitespace / too-short / excluded units are dropped with the named reasons
3. Zero eligible units → `skipped_not_applicable`, not empty `success`
4. `wordclouds` without `keyphrases` still succeeds on baseline path
5. No module ships an inline “softened insight_eligibility” stub

## Cache identity contribution

When a module uses this policy, analysis-run-storage cache identity must include:

- `eligibility_policy_id` = `notebook_eligibility_v1`
- `eligibility_policy_version` = `1`
- `eligibility_fingerprint` = lowercase hex SHA-256 of compact UTF-8 JSON with sorted keys of the **outputs** object above (`policy_id`, `policy_version`, `eligible_unit_ids`, `decisions`)

## Non-goals

- Full TranscriptX `insight_eligibility` / genre gating (Wave 3+)
- Per-module private eligibility heuristics for the modules listed as required above
- Treating “bypass” as an implementation free-for-all
