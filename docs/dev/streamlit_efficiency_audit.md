# Streamlit efficiency / fluidity audit

**Status:** [~] active — maintainer track for every-rerun cost and interaction fluidity. Does **not** reopen usability-wave **U2** (sample notebook / first-run docs) or propose a Streamlit rewrite.

**Thesis:** The Transcribe GUI is a single Streamlit process with session-mode routing. Live OCR/Analyse jobs correctly survive reruns via `st.cache_resource`. Remaining jank comes from **paying full-shell and Review/View filesystem costs on every widget click**, not from missing product chrome.

## Non-goals

| Out of scope | Why |
|--------------|-----|
| Streamlit multipage rewrite | Host policy through 2.0; session IA is intentional |
| U2 sample notebook / first-run install docs | Owned by [usability_wave_plan.md](../usability_wave_plan.md) |
| Blanket `st.cache_resource.clear()` | Drops live job coordinators |
| Caching page-result JSON in core services | Keep caches in the UI layer (`test_core_no_streamlit`) |

## Hot-path matrix

| Surface | Cost class | Symptom | Evidence | PR1 fix |
|---------|------------|---------|----------|---------|
| Shell CSS | Every rerun | Pointless work | `shell.inject_global_styles` | Module-level `_GLOBAL_STYLES_MARKDOWN` |
| Sidebar logo | Every rerun | Disk + base64 | `shell.render_brand` | Process-local `_logo_data_uri` |
| View nav gate | Every rerun | `analysis/*/published.json` walk | `notebook_has_published_analysis` | Session cache keyed by archive generation |
| Review queue | Per Review enter / widget | N× `load_page_result` + live align + repair | `app._render_review_workbench` | Session-cache index + repair-once per token |
| Review page | Per click | Second `repair_empty_successes` | `review_workbench.render_review_page` | Skip when queue token already repaired |
| View health | Per View tab | Module health over many published.json | `notebook_views.load_view_health` | Session cache on FS token |
| Wordcloud Advanced | Per render | Re-read vendored JS | `wordcloud_render.build_wordcloud_explorer_html` | Process-local JS text |
| Analyse poll | While running | Full-app pressure at 400ms | `run_analysis` fragments | `run_every=1s` (match OCR/batch) |

## Architecture baseline

```text
app.main (every click)
  → CSS + logo + ensure_index + sidebar nav
  → global analysis chip fragment (0.5s when active)
  → mode body (Review / View / jobs / …)
```

Listing walks for Batch pickers already use [`corpus_listing_cache.py`](../../src/transcribe/ui/corpus_listing_cache.py). PR1 extends the same practice via [`rerun_cache.py`](../../src/transcribe/ui/rerun_cache.py).

## Acceptance (PR1)

1. Logo bytes are not re-read on every `main()` call after the first process load.
2. `cached_notebook_has_published_analysis` returns the filesystem answer once per `(root, archive.generation)`.
3. Review queue index rebuilds only when the Review FS token changes (result mtimes / review fields); empty-success repair runs at most once per token.
4. `load_view_health` hits session cache when switching Overview → Themes → Mood with unchanged FS token.
5. Analyse this-notebook progress fragments poll at **1s**.
6. `tests/unit/test_core_no_streamlit.py` still passes (caches stay in `transcribe.ui`).
7. Offline unit tests cover token hit/miss and invalidation helpers.

## Deferred (not PR1)

- Page-scan click lightbox (Streamlit API gap)
- Broader `@st.cache_data` over ProjectService loads
- Library cover-grid virtualization beyond existing paging
- Reducing floating-chip `run_every=0.5` further (needs cancel/UX evidence)

## Verified outcomes

- Unit: `tests/unit/test_rerun_cache.py`, `test_streamlit_efficiency_audit_docs.py`, plus shell / wordcloud / Review / GUI alignment / Analyse contract / `test_core_no_streamlit` — green.
- Chrome: module-level CSS constant + process-local logo data URI / wordcloud2.js text confirmed load-once.
- Deferred manual UI smoke (Streamlit host) for leave-page Analyse chip; coordinator `cache_resource` ownership unchanged.
