Type: GUIDE
Authority: settings / profiles / UI knobs operations — summarizes [workspace-settings](../contracts/workspace-settings.md); does not redefine schema

# Settings, profiles, and knobs

Where to change workspace behaviour in the UI and how overlays resolve. Authoritative schema and precedence: [contracts/workspace-settings.md](../contracts/workspace-settings.md). Interface menus: [contracts/interface-menus.md](../contracts/interface-menus.md). Alignment notes vs TranscriptX: [dev/settings_tx_alignment.md](../dev/settings_tx_alignment.md).

## Where to start

**Settings** tabs: Configuration · Analysis · Detection · Prompts · Interface · Models · Profiles · Export.

| Tab | Typical use |
|-----|-------------|
| **Configuration** | Folders, **Backup**, import / visual declutter, Archive paging, Overview cards |
| **Analysis** | Preset policies (Quick / Balanced / Thorough) |
| **Detection** | Custom detectors |
| **Prompts** | Prompt Hub (OCR, cleanup, detection definitions) |
| **Interface** | Action-menu prefs |
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
| **Analyse UI presets** | Quick / Balanced / Thorough / Custom — module-set policies for Analyse |

Builtin export profiles: `default`, `readable`, `compact`, `large_print`. Editing a profile-supplied value detaches that target to `default` and writes workspace overrides.

## Common UI knobs

| Knob | Where | Notes |
|------|-------|-------|
| Visual declutter | Configuration → Import | Default on for imports; re-apply does not re-OCR — [source-asset](../contracts/source-asset.md) |
| Archive strip paging | Configuration → Archive | `ui.archive_notebooks_initial` (`0` = show all) |
| Overview cards | Configuration → Overview | Visibility only; status strip always on |
| OCR preprocess seed | Models | `none` \| `gentle_contrast` for **new** notebooks |
| Prefer mode | Models / Review Compare | Prefer / promote semantics — [page-result](../contracts/page-result.md) |
| Full-workspace backup | Configuration → Backup | [backup_and_restore.md](../backup_and_restore.md) |

## Env overrides

See [installation.md](installation.md). Env allowlist does not replace project OCR authority for an open notebook.

## Related

- Golden path: [../user_guide.md](../user_guide.md)
- OCR operations: [ocr.md](ocr.md)
- Analysis operations: [analysis.md](analysis.md)
- Export operations: [export.md](export.md)
