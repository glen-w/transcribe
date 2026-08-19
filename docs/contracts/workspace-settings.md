Type: CONTRACT
Authority: self — workspace `settings.json`, profiles, precedence, recovery, and analysis config fingerprinting. Project OCR authority remains [project-on-disk.md](project-on-disk.md).

# Workspace settings

## Layout

Under `TRANSCRIBE_DATA_DIR` (default `./data`):

| Path | Role |
|------|------|
| `config/settings.json` | Workspace settings (`format: transcribe.settings`) |
| `config/profiles/{target}/{name}.json` | User profiles (`format: transcribe.profile`) |
| `config/.transcribe.settings.lock` | Cross-process settings/profile mutation lock |

Virtual builtin profiles are **not** on disk.

## Precedence (per key)

`defaults → workspace → active profile overlay → env allowlist → project OCR allowlist`

Project OCR fields win over env so notebook `project.json` settings are not
silently overridden by `TRANSCRIBE_OLLAMA_BASE_URL`. Project may override only
OCR fields owned by `project.json` → `settings`. Workspace `ocr.*` seeds
**new projects only**. Workspace `ingest.render_dpi` (default **200**, range
72–600) is the PDF rasterisation DPI for Workflow → Import.

Workspace `export.*` controls default export formats, structure, and typography
(see [notebook-export.md](notebook-export.md)).

Workspace `ingest.*` seeds PDF rasterisation and visual declutter defaults for
**Workflow → Import** (and Settings → Configuration → Import). Declutter may
also be **re-applied** to an existing notebook from that panel (creates a new
`render_id` when pixels change; does not re-run OCR) — see
[source-asset.md](source-asset.md).

Workspace `ui.*` holds UI presentation defaults that do not affect OCR or
analysis fingerprints.

Detection auto-tag defaults live in `data/config/detection-auto-tag.json`
(`transcribe.detection-auto-tag` v1), **not** in fingerprint-relevant settings.
See [tag-catalog.md](tag-catalog.md).

## UI knobs (`ui.*`)

| Key | Default | Role |
|-----|---------|------|
| `archive_notebooks_initial` | `0` | Archive strip: how many notebook cards load before **Show more**. `0` shows all. Session “Show more / Show fewer” advances by this page size (or by total when `0`). |
| `overview_cards` | all frozen ids | Ordered visible Overview cards (`page_metrics`, `stats`, `lexical_diversity`, `understandability`, `wordclouds`, `ner`, `sentiment`, `epistemic_markers`). Unknown/duplicate ids dropped; catalogue order; empty after sanitise restores the default all-ids list. Status strip is always shown. |
| `view_show_advanced` | `false` | When `true`, View pages show per-module **Advanced · …** expanders with raw published JSON. Default off — ordinary use does not need module/cache literacy. Applies to Overview, Themes, Mood, Moments, Summaries, Ask, and Themes → People (entity tone). Analyse launcher Advanced sections are unchanged. Legacy key `overview_show_advanced` is still read on load. |

Edited under **Settings → Configuration → Archive** and **Settings → Configuration → Overview**. `ui.*` does not fingerprint.

## OCR lifecycle knobs (`ocr.*`)

Workspace OCR seeds **new notebooks** and Apply-to-project (allowlisted). Live
job authority remains `project.json` → `settings`.

| Key | Default | Role |
|-----|---------|------|
| `preprocess_profile` | `none` | Image preprocess named profile (`none` \| `gentle_contrast`). Edited under **Settings → Models**; seeds new notebooks; Apply-OCR can copy. |
| `prefer_mode` | `prefer_is_promote` | **When setting a notebook default** — `prefer_is_promote` \| `prefer_only` \| `prefer_promote_with_edit_gate` (Review UI labels in [page-result.md](page-result.md); guide: [runtime/ocr.md](../runtime/ocr.md#when-setting-a-notebook-default)) |
| `auto_activate_composite` | `true` | **Seed transcription from merged draft after multipass** — auto-activate succeeded composite after multipass ([runtime/ocr.md](../runtime/ocr.md#seed-transcription-from-merged-draft-after-multipass)) |
| `multipass_default_models` | `[]` | Optional UI default multi-select list |
| `finetune_*` | see [finetune-export.md](finetune-export.md) | Fine-tune export defaults |

Project OCR may override `prefer_mode` and `auto_activate_composite` (and other
allowlisted OCR fields). **Workflow → Review → Other → OCR settings**, Compare OCR attempts, and Transcribe Advanced write the project override.

## Profiles

Activation-pointer model: workspace stores `active_*_profile`; profile content overlays at resolve time (never copied into workspace). Editing a profile-supplied value detaches that target to `default` and writes workspace overrides. Builtins are immutable; Save As rejects reserved names.

Targets: `workflow`, `ocr`, `llm`, `export`.

Builtin export profiles: `default`, `readable`, `compact`, `large_print`
(typography / structure overlays under the `export` config subtree).

## EffectiveConfig snapshots

Analysis batches / OCR apply operations capture one immutable `EffectiveConfig`. Modules and `config_fingerprint` consume that snapshot (bound via context), not live `get_config()` mid-run.

`ANALYSIS_CONFIG_VERSION` and `PRESET_POLICY_VERSION` are included in fingerprint-relevant config subsets.

### Analysis UI presets (`analysis.ui_presets`)

Each named preset policy (`quick` / `balanced` / `thorough`) carries:

| Field | Role |
|-------|------|
| policy knobs | `allow_llm`, allowlists, `include_excluded_from_default`, optional `module_ids` override, `allow_detection`, `detector_ids` (empty allowlist = all detectors) |
| `content_version` | integer content generation; builtins default to `1`; missing on load → `1` |

Builtin defaults: Quick and Balanced have `allow_detection=false`; Thorough has `allow_detection=true` and an empty detector allowlist. Missing detection keys on load default to off / empty (legacy bodies still parse).

`PRESET_POLICY_VERSION` is schema/shape only. **Content identity** is `content_version` plus the policy body fingerprint (SHA-256 of knobs **excluding** `content_version`).

Settings writes that change a named preset’s policy body **must** bump that preset’s `content_version`. Unchanged saves must not bump. Custom selections on Analyse are not workspace presets: they use `preset_key=custom`, `content_version=0`, and a fingerprint of the selected module list.

Frozen `AnalysisRunPlan` records `preset_key`, `preset_content_version`, and `preset_policy_fingerprint` so a run identifies exactly which preset generation produced it (see [analysis-run-storage.md](analysis-run-storage.md)).

## Recovery

Corrupt/unsupported settings: never silent overwrite. Preserve file; surface stable error codes (`settings_corrupt`, `settings_schema_unsupported`). In-memory defaults only under explicit `defaults_readonly` recovery; Saves disabled until Reset workspace (archives then writes fresh defaults).

Unsupported `schema_version` greater than this build → refuse (`settings_schema_unsupported`).
