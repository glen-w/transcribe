# OCR model recipes

Workspace overlay for per-tag OCR prompt freeze and generation-option patches.
Not part of `settings.json`. Live at job start (next job only; the frozen
`JobPlan` already holds prompt text and options).

## On-disk location

`{TRANSCRIBE_DATA_DIR}/config/ocr-model-recipes.json`

```json
{
  "format": "transcribe.ocr-model-recipes",
  "schema_version": 1,
  "recipes": []
}
```

Missing file → code builtins only. Corrupt JSON / unexpected `format` /
`schema_version` ≠ 1 → **do not overwrite**; jobs use builtins; Settings shows
`ocr_recipes_corrupt` or `ocr_recipes_schema_unsupported`. An explicit Reset
or Save from Settings may replace the file.

Workspace backup packs `config/`, so overlays travel with the workspace.

## Overlay row

| Field | Required on custom | Notes |
|-------|--------------------|--------|
| `recipe_id` | yes | Lowercase slug `^[a-z][a-z0-9_]{1,63}$` |
| `title` | yes (custom) | Display name |
| `match_tokens` | yes (custom) | Substrings of the lowercased Ollama tag |
| `match_mode` | no | `any` (default) or `all` |
| `exclude_tokens` | no | If any substring hits, the recipe does not match |
| `prompt_id` | when `freeze_prompt` | Must exist in the OCR Prompt Hub / builtin OCR registry |
| `freeze_prompt` | no | Default `true`. `false` = options-only (notebook `prompt_id` stays) |
| `generation_options` | no | Keys: `repeat_penalty`, `stop` (string list), `temperature` (0–2), `num_predict` (64–8192). Overlay keys merge onto the builtin; JSON `null` drops a key |
| `warnings` | no | Picker copy |
| `advice_kind` | no | `ocr_oriented` \| `recommended_vlm` \| `general_vlm` |
| `enabled` | no | Default `true`. `false` disables the lane |

Partial rows with a builtin `recipe_id` overlay only the listed fields.

## Merge

1. User overlay rows **prepend** (file order; higher priority).
2. Same `recipe_id` as a builtin → `source=override` (merged).
3. Unknown `recipe_id` → `source=custom`.
4. Builtins not named in the overlay append after user rows.
5. Lookup: first **enabled** recipe whose tokens match.

## Job plan

Prompt text:

1. Non-empty notebook custom prompt always wins.
2. Else if a matching recipe has `freeze_prompt` → recipe `prompt_id` (Hub override of that id still applies).
3. Else notebook `prompt_id`.

Recipe `generation_options` overlay the notebook options whenever a recipe
matches, including when a custom prompt won the text.

`JobPlan.recipe_id` and `AttemptProvenance.recipe_id` record the matched id
(empty when none). They are **not** in the skip fingerprint. Fingerprint uses
prompt SHA and generation options (including extra keys such as
`repeat_penalty`). Changing overlay options therefore re-runs succeeded pages
once.

## Matching

Lowercased tag. `match_mode=any`: any token is a substring. `match_mode=all`:
every token is a substring. `exclude_tokens` veto. First enabled hit wins.

## UI

**Settings → Models → OCR model recipes.** Enable/disable writes the overlay.
Add/edit upserts a row. Revert drops an override (builtin restored). Remove
drops a custom row.

## Related

- Runtime guide: [runtime/ocr_model_recipes.md](../runtime/ocr_model_recipes.md)
- Code: `src/transcribe/services/ocr_model_recipes.py`,
  `src/transcribe/services/ocr_model_recipe_store.py`
- Page results / fingerprints: [page-result.md](page-result.md)
