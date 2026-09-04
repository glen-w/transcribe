# Settings, profiles, and knobs

Where to change workspace behaviour in the UI. Schema and precedence:
[workspace-settings](../contracts/workspace-settings.md). Interface menus:
[interface-menus](../contracts/interface-menus.md).

## Where to start

**Settings** tabs: Configuration · Analysis · Detection · Tags · Prompts · Interface · Models · Profiles · Export.

| Tab | Typical use |
|-----|-------------|
| **Configuration** | Folders, **Backup**, import / visual declutter, Library cover-grid paging, Overview cards |
| **Analysis** | Preset policies (Quick / Balanced / Thorough; detectors for Thorough / Custom) |
| **Detection** | Custom detectors and detection auto-tag defaults |
| **Tags** | Workspace organisation catalogue (labels, colours, rename, merge/delete) — [tag-catalog](../contracts/tag-catalog.md) |
| **Prompts** | Prompt Hub (OCR, cleanup, detection definitions) |
| **Interface** | Action-menu prefs (which actions, icon/text appearance) |
| **Models** | Workspace Ollama URL, OCR preprocess seed, LLM budgets, Apply-OCR to open notebook |
| **Profiles** | Activate named overlays (`workflow` / `ocr` / `llm` / `export`) |
| **Export** | Read-only typography defaults; change on **Workflow → Export** or via an export profile |

## Precedence (summary)

`defaults → workspace → active profile overlay → env allowlist → project OCR allowlist`

Project OCR fields on `project.json` win over env so a notebook is not silently overridden by `TRANSCRIBE_OLLAMA_BASE_URL`. Workspace `ocr.*` seeds **new projects only** (Apply-OCR can copy allowlisted fields onto the open notebook).

Mid-job / mid-run settings changes apply to the **next** OCR or Analyse run only — active jobs use a frozen plan.

## Profile taxonomy (do not conflate)

| Kind | Meaning |
|------|---------|
| **Install extras** | `[ui]` / `[dev]` / `[export]` — packaging, not runtime presets |
| **Named profiles** | JSON under `data/config/profiles/<target>/` — activation-pointer overlays |
| **Analyse UI presets** | Quick / Balanced / Thorough / Custom — module-set (and optional detector) policies for Analyse |

Builtin export profiles: `default`, `readable`, `compact`, `large_print`. Editing a profile-supplied value detaches that target to `default` and writes workspace overrides.

## Common UI knobs

| Knob | Where | Notes |
|------|-------|-------|
| Visual declutter | Configuration → Import | Default on for imports; re-apply does not re-OCR — [source-asset](../contracts/source-asset.md) |
| Library cover-grid paging | Configuration → Library | `ui.archive_notebooks_initial` (`0` = show all) |
| Overview cards | Configuration → Overview | Visibility only; status strip always on |
| OCR preprocess seed | Models | `none` \| `gentle_contrast` for **new** notebooks |
| When setting a notebook default | Review → **OCR** · Transcribe Advanced | `prefer_is_promote` (default) \| `prefer_only` \| `prefer_promote_with_edit_gate` — [ocr.md](ocr.md#when-setting-a-notebook-default) |
| Seed transcription from merged draft after multipass | Review → **OCR** · Transcribe Advanced · Transcribe multipass row | `auto_activate_composite` (default **on**) — [ocr.md](ocr.md#seed-transcription-from-merged-draft-after-multipass) |
| Full-workspace backup | Configuration → Backup | [backup_and_restore.md](../backup_and_restore.md) |

## Env overrides

See [installation.md](installation.md). Env allowlist does not replace project OCR authority for an open notebook.

## Related

- Golden path: [../user_guide.md](../user_guide.md)
- OCR operations: [ocr.md](ocr.md)
- Analysis operations: [analysis.md](analysis.md)
- Export operations: [export.md](export.md)
- TranscriptX alignment (maintainers): [settings_tx_alignment.md](../dev/settings_tx_alignment.md)
