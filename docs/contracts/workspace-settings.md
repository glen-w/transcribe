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

`defaults → workspace → active profile overlay → project OCR allowlist → env allowlist`

Project may override only OCR fields owned by `project.json` → `settings`. Workspace `ocr.*` seeds **new projects only**.

## Profiles

Activation-pointer model: workspace stores `active_*_profile`; profile content overlays at resolve time (never copied into workspace). Editing a profile-supplied value detaches that target to `default` and writes workspace overrides. Builtins are immutable; Save As rejects reserved names.

Targets: `workflow`, `ocr`, `llm`.

## EffectiveConfig snapshots

Analysis batches / OCR apply operations capture one immutable `EffectiveConfig`. Modules and `config_fingerprint` consume that snapshot (bound via context), not live `get_config()` mid-run.

`ANALYSIS_CONFIG_VERSION` and `PRESET_POLICY_VERSION` are included in fingerprint-relevant config subsets.

## Recovery

Corrupt/unsupported settings: never silent overwrite. Preserve file; surface stable error codes (`settings_corrupt`, `settings_schema_unsupported`). In-memory defaults only under explicit `defaults_readonly` recovery; Saves disabled until Reset workspace (archives then writes fresh defaults).

Unsupported `schema_version` greater than this build → refuse (`settings_schema_unsupported`).
