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

## OCR lifecycle knobs (`ocr.*`)

Workspace OCR seeds **new notebooks** and Apply-to-project (allowlisted). Live
job authority remains `project.json` → `settings`.

| Key | Default | Role |
|-----|---------|------|
| `prefer_mode` | `prefer_is_promote` | Prefer semantics: `prefer_is_promote` \| `prefer_only` \| `prefer_promote_with_edit_gate` (see [page-result.md](page-result.md)) |
| `auto_activate_composite` | `true` | After multipass, auto-activate composite candidates |
| `multipass_default_models` | `[]` | Optional UI default multi-select list |
| `finetune_*` | see [finetune-export.md](finetune-export.md) | Fine-tune export defaults |

Project OCR may override `prefer_mode` and `auto_activate_composite` (and other
allowlisted OCR fields). Review → Compare settings writes the project override.

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
| policy knobs | `allow_llm`, allowlists, `include_excluded_from_default`, optional `module_ids` override |
| `content_version` | integer content generation; builtins default to `1`; missing on load → `1` |

`PRESET_POLICY_VERSION` is schema/shape only. **Content identity** is `content_version` plus the policy body fingerprint (SHA-256 of knobs **excluding** `content_version`).

Settings writes that change a named preset’s policy body **must** bump that preset’s `content_version`. Unchanged saves must not bump. Custom selections on Run Analysis are not workspace presets: they use `preset_key=custom`, `content_version=0`, and a fingerprint of the selected module list.

Frozen `AnalysisRunPlan` records `preset_key`, `preset_content_version`, and `preset_policy_fingerprint` so a run identifies exactly which preset generation produced it (see [analysis-run-storage.md](analysis-run-storage.md)).

## Recovery

Corrupt/unsupported settings: never silent overwrite. Preserve file; surface stable error codes (`settings_corrupt`, `settings_schema_unsupported`). In-memory defaults only under explicit `defaults_readonly` recovery; Saves disabled until Reset workspace (archives then writes fresh defaults).

Unsupported `schema_version` greater than this build → refuse (`settings_schema_unsupported`).
