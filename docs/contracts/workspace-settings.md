# Workspace settings

## Layout

Under `TRANSCRIBE_DATA_DIR` (default `./data`):

| Path | Role |
|------|------|
| `config/settings.json` | Workspace settings (`format: transcribe.settings`) |
| `config/profiles/{target}/{name}.json` | User profiles (`format: transcribe.profile`) |
| `config/ocr-model-recipes.json` | OCR model recipe overlay (`format: transcribe.ocr-model-recipes`) — live at job start, not an `ocr.*` new-notebook seed. See [ocr-model-recipes.md](ocr-model-recipes.md) |
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
(see [notebook-export.md](notebook-export.md)). `export.exclude_ignored_pages`
(default **true**) is also the Reading hide-ignored default; the Reader
**Show ignored pages** checkbox is a session override and does not write
settings.

Workspace `ingest.*` seeds PDF rasterisation and visual declutter defaults for
**Workflow → Import** (and Settings → Configuration → Import). Declutter may
also be **re-applied** to an existing notebook from that panel (creates a new
`render_id` when pixels change; does not re-run OCR) — see
[source-asset.md](source-asset.md). The same Configuration panel can
**Regenerate thumbnails** (force-rewrite disposable cover + grid JPEGs under
`.cache/thumbs/`); single-notebook and bulk import warm thumbs on commit.

Workspace `ui.*` holds UI presentation defaults that do not affect OCR or
analysis fingerprints.

Detection auto-tag defaults live in `data/config/detection-auto-tag.json`
(`transcribe.detection-auto-tag` v1), **not** in fingerprint-relevant settings.
See [tag-catalog.md](tag-catalog.md).

OCR model recipes live in `data/config/ocr-model-recipes.json`
(`transcribe.ocr-model-recipes` v1). They apply to **every** OCR job at plan
freeze (not new-notebook seeds). Resulting prompt SHA and generation options
are fingerprint-relevant; `recipe_id` itself is not. See
[ocr-model-recipes.md](ocr-model-recipes.md).

## UI knobs (`ui.*`)

| Key | Default | Role |
|-----|---------|------|
| `archive_notebooks_initial` | `0` | Library **Covers** grid: how many notebook cards load before **Show more**. `0` shows all. Session “Show more / Show fewer” advances by this page size (or by total when `0`). |
| `hide_ignored_pages` | `true` | When `true`, Reading omits pages with `Page.ignored` unless the Reader **Show ignored pages** override is on. Edited under **Settings → Configuration → Reading**. Does not fingerprint. |
| `overview_cards` | all frozen ids | Ordered visible Overview cards (`page_metrics`, `stats`, `lexical_diversity`, `understandability`, `wordclouds`, `ner`, `sentiment`, `epistemic_markers`). Unknown/duplicate ids dropped; catalogue order; empty after sanitise restores the default all-ids list. Status strip is always shown. |
| `view_show_advanced` | `false` | When `true`, View pages show per-module **Advanced · …** expanders with raw published JSON. Default off — ordinary use does not need module/cache literacy. Applies to Overview, Themes, Mood, Moments, Summaries, Ask, and People & Places (entity tone). Analyse launcher Advanced sections are unchanged. Legacy key `overview_show_advanced` is still read on load. |
| `model_preference_hints` | `all_choices` | History beside vision model pickers on Transcribe / Review and in **Settings → Models** installed-models table. `off` hides hints; `prefer_only` counts explicit notebook-default ledger events; `all_choices` (default) also includes **Use as current text** / promote events in the share percentage. Edited under **Settings → Models**. Does not fingerprint. |

Edited under **Settings → Configuration → Library** and **Settings → Configuration → Overview**. `ui.*` does not fingerprint.

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
allowlisted OCR fields). **Workflow → Review → OCR → OCR settings** and Transcribe Advanced write the project override.

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

### Ask RAG (`analysis.rag`)

Paperful-shaped knobs. Default **off**. Fingerprinted for `llm_rag_qa` only (`ANALYSIS_CONFIG_VERSION` 2).

| Key | Default | Role |
|-----|---------|------|
| `enabled` | `false` | Master switch for RAG Ask |
| `auto_ingest` | `false` | Reserved for post-OCR index refresh (not wired). Use `transcribe rag ingest` to warm indexes; Ask still rebuilds a stale index when RAG runs |
| `embed_provider` | `ollama` | Only `ollama` in this slice |
| `embed_model` | `nomic-embed-text` | Ollama embedding tag |
| `embed_base_url` | `""` | Empty → notebook/Ollama base URL |
| `embed_batch_size` | `32` | Min 1 |
| `chunk_chars` / `chunk_overlap` | `2048` / `256` | Min chunk 200; overlap capped at half |
| `top_k` | `10` | Passages packed into the prompt |
| `max_context_chars` | `24000` | Min 1000 |
| `hybrid` | `true` | Vector + FTS; falls back to vector-only |
| `model` | `""` | Chat override; empty → Ask text model |
| `ask_mode` | `grounded` | `grounded` \| `rag` \| `both` — View → Ask default |

Index lives under `{project}/.cache/rag/{provider}__{model}/` (disposable). Edited under **Settings → Analysis**.

## Recovery

Corrupt/unsupported settings: never silent overwrite. Preserve file; surface stable error codes (`settings_corrupt`, `settings_schema_unsupported`). In-memory defaults only under explicit `defaults_readonly` recovery; Saves disabled until Reset workspace (archives then writes fresh defaults).

Unsupported `schema_version` greater than this build → refuse (`settings_schema_unsupported`).
