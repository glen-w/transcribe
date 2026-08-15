Type: GUIDE
Authority: developer note — does not redefine runtime contracts; settings owned by workspace-settings.md

# Settings / profiles / models alignment (TranscriptX ↔ Transcribe)

TX source pin (read, not imported): `glen-w/TranscriptX` `main` at
[`da742f937996d8fd2d4d40ecd9135af5126e4404`](https://github.com/glen-w/TranscriptX/commit/da742f937996d8fd2d4d40ecd9135af5126e4404)
(2026-08-13). Transcribe UI stays on port **8510**; TX binds **8501**.

**Theme** in this note means Streamlit/CSS chrome, OCR `preprocess_profile`,
and export typography profiles. It does **not** mean View → Themes (topics)
or Overview wordcloud cards except existing `ui.overview_cards` copy.

## What TranscriptX does

| Concern | TX behaviour |
|---------|----------------|
| Settings tabs | Configuration · Analysis · Storage · Watcher · Speakers · Interface · Models · Questions · Corrections (`src/transcriptx/web/page_modules/settings.py`) |
| System siblings | Settings, Tools, **Profiles**, **Dashboard Builder**, Diagnostics (`navigation.py` `PAGE_SPECS`, section `settings`) |
| Gating | Settings `required_context` is `"none"`; context bar hidden for the settings section |
| Configuration scopes | Default (read-only) / Project (`config.json`) / Draft override / Run override. Env `TRANSCRIPTX_*` **wins** |
| Profiles | Separate System page. `ProfileManager` targets: `workflow`, `topic_modeling`, `semantic_similarity`, `acts`, `tag_extraction`, `qa_analysis`, `temporal_dynamics`, `vectorization`, `llm_models`. Copy-into facade, then env |
| Models tab | Ollama **text** tags; live `/api/tags`; `llm_models` preset CRUD; “Set as project active”; Run Analysis “Custom (this run)” |
| Prompts | No hub. Templates in Python modules. Settings → Questions is a `llm_custom_qa` **question library** |
| Interface | Action menus + info tooltips; recovery preserves file; Replace writes `.bak.` |
| Theme | No `.streamlit/config.toml`; CSS in `web/shell.py` (`#1f77b4`, dark-theme nav). No Settings theme picker |
| Reset | Unsaved **Reset** (reload scope baseline) / **Revert to defaults**. `test_config_reset.py` is process-global test isolation |
| Language | Subject is **transcript**; “Project” is a config layer |

## What Transcribe does (aligned)

| Concern | Transcribe behaviour |
|---------|----------------------|
| Settings tabs | Configuration · Analysis · Detection · Tags · Prompts · Interface · Models · Profiles · Export (`settings_interface.py` `SETTINGS_TABS`) |
| System | Settings · Diagnostics only. Profiles stays a **tab**, not a System page |
| Gating | Settings `required_context` is `"none"` (stay-don’t-bounce). Apply-OCR gated on a selected notebook; Re-apply declutter has its own notebook picker |
| Configuration | Workspace-only guided sections (folders, import, archive, Overview cards). No Default/Project/Run radio |
| Profiles | Activation-pointer + four targets (`workflow`, `ocr`, `llm`, `export`). Overlay at resolve; detach-on-edit; builtins virtual |
| Precedence | `defaults → workspace → active profile overlay → env allowlist → project OCR allowlist`. Project OCR **wins** env |
| Models tab | Workspace Ollama URL, text-model hint, token budgets, `preprocess_profile` seed, Apply-OCR. Live discovery stays on Transcribe / Analyse launchers |
| Prompts | Prompt Hub for `ocr` / `cleanup` / `detection` / `custom`; override version bump; dry-run. Analyse module prompts stay module-local |
| Export tab | Read-only effective `export.*` + active profile. Live editors on **Workflow → Export**. Typography: `readable` / `compact` / `large_print` |
| Theme | `.streamlit/config.toml` is port **8510** only (no `[theme]`). CSS in `ui/shell.py` already TX-shaped. No Settings theme picker |
| Reset | Archive `settings.reset.{stamp}.json` then factory defaults. Never silent overwrite (`settings_corrupt`, `settings_schema_unsupported`) |
| Language | **notebook**, British **Analyse**. GUI must not say **project** |

## Intentional divergences (keep)

1. **No speaker/session-scoped settings** — TX Speakers tab / `speaker_profiles/`. Transcribe has notebooks.
2. **No TX run-override stack** — no Draft/Run `run_config_override.json`. Jobs freeze `EffectiveConfig`; live OCR authority is `project.json`.
3. **No copy-into-workspace profiles** — overlay + detach-on-edit (contracted).
4. **No TX module profile targets** (`topic_modeling`, `acts`, …) — analysis depth is UI presets.
5. **No Dashboard Builder / YAML layout clone** — Overview cards checklist (`ui.overview_cards`) already shipped.
6. **No TX Storage/Watcher/Questions/Corrections tabs** — paths are env/Docker; Prompt Hub ≠ question library.
7. **Profiles stay a Settings tab** — System IA is Settings · Diagnostics.
8. **Prompt Hub is Transcribe-native** — TX has none. Do not CDN-host prompts. Do not move Analyse inline prompts into the Hub here.
9. **Launcher vs Settings model split** — live Ollama discovery stays on Transcribe/Analyse (`model_info.py`).
10. **Visual theme control** — ignore TX (already copied in `shell.py`). No light/dark picker.
11. **Reset is archive-then-defaults** — not TX unsaved editor Reset/Revert.
12. **Env vs project OCR** — TX env wins; Transcribe project OCR wins so a workspace/env URL cannot silently override an open notebook.
13. **Port 8510 / no TX process coupling.**
14. **CDN-hosted prompt/theme assets** — keep offline. TX’s optional Ollama-library scrape is not copied.

## Do not

- Import TranscriptX at runtime or share a settings schema (`docs/INTEGRATION_SEAM.md` untouched).
- Reopen Analyse/View IA, Library, Open→Reading, Overview card ids, or frozen interface-menus action IDs.
- Bounce Settings → Home when no notebook is selected.
- Silently rewrite corrupt settings.
- Change `ANALYSIS_CONFIG_VERSION` / `PRESET_POLICY_VERSION` without a contract bump plan.
