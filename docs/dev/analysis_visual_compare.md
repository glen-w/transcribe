Type: GUIDE
Authority: developer note — View chart compare behaviour; does not redefine analysis contracts

# Analyse visual compare (TranscriptX alignment)

## Problem

Published Analyse results often looked like “ready” chips or Advanced JSON
dumps. Several Overview / Summaries extractors looked for top-level keys the
modules never emit (e.g. `type_token_ratio` vs `document.ttr`).

## TranscriptX inspiration

TX `lexical_diversity` drew **bar charts by speaker** (TTR / MTLD / hapax).
Transcribe has no speakers. The spiritual analogue is:

**this notebook vs peer notebooks** — entire corpus average, or a period the
user selects (year / date range), using each notebook’s diary `date_start` /
`date_end` (same period language as Library / Search).

## What shipped

| Layer | Role |
|-------|------|
| `services/analysis_compare.py` | Extract comparable metrics; average published payloads across projects with period filter |
| `ui/analysis_compare_view.py` | Period controls + grouped bar charts |
| `ui/analysis_display_helpers.py` | Pure payload → chart/table rows (all modules) |
| `ui/analysis_product_views.py` | Per-module product visuals + summaries field fixes + compare wiring |
| `ui/places_map.py` | Entity tone (entity_sentiment) on People & places |

### Visual intent by module

| Module | User visual | Corpus/period compare? |
|--------|-------------|------------------------|
| `stats` | chips + tokens/page bars; compare chart scales tokens÷1k / chars÷10k so pages stay visible | yes |
| `lexical_diversity` | chips + TTR line | yes |
| `understandability` | chips + Flesch line | yes |
| `wordclouds` | **Basic** static cloud or **Advanced** interactive explorer (TX controls) | no |
| `ner` | type mix + top surfaces; Places map | no |
| `entity_sentiment` | entity mean-sentiment bars + table | no |
| `sentiment` | compound line + tone mix | yes |
| `epistemic_markers` | category bars + hedge/booster by page | yes |
| `keyphrases` | phrase list + score bars | no |
| `topic_modeling` / `bertopic` | topic weight bars + terms | no |
| `semantic_similarity` | motif similarity bars + pairs | no |
| `topic_shift` | adjacent-similarity line + boundaries | no |
| `emotion` | label totals + intensity line | yes |
| `contextual_emotion` | dominant-label counts + intensity | no |
| `fine_grained_emotion` | same when payload exists | no |
| `affect_tension` | tension line | yes |
| `moments` / `highlights` | score bars + quote list; Moments **Jump to page** → Reading | no |
| `summary` / `insights` / LLM text | prose / grouped lists | no |
| `llm_action_items` | grouped action / decision / question | no |
| `llm_custom_qa` | Ask answer + evidence | no |

**Click-to-page:** within-notebook page-order series (tokens, TTR, Flesch, sentiment,
emotion / tension / intensity, hedges vs boosters, topic-shift similarity, ink
coverage) use Altair + Streamlit `on_select` and jump to Reading via the same
`open_page_context` path as Moments (shared `jump_to_reading`; Back returns to
the source View page). Categorical charts stay non-clickable.

Comparable modules: `stats`, `lexical_diversity`, `understandability`,
`sentiment`, `emotion`, `affect_tension`, `epistemic_markers`.

Within-notebook visuals (not corpus compare): token/TTR/Flesch series, sentiment /
emotion / tension lines, topic-shift similarity line, keyphrase / motif / topic bars,
entity tone, action-item groups.

## Intentional divergences from TX

1. **Peers, not speakers** — notebook domain.
2. **Streamlit charts** — no Plotly/matplotlib chart registry or viz_id artifacts.
3. **Read-model only** — never re-runs modules; averages published envelopes.
4. **Exclude current notebook** from the average so deltas are vs peers.
5. **Undated notebooks** included for “Entire corpus”, excluded for year/range.
6. **Word clouds in the UI** — TX renders a static PNG via `wordcloud` and an interactive explorer HTML (`wordcloud2.js` + search / top N / min value / sort / CSV). Transcribe Overview offers the same **Basic / Advanced** choice: Basic uses `WordCloud.to_image()` (Pillow); Advanced embeds a TX-shaped explorer with **vendored** `wordcloud2.js` (offline; TX uses a CDN). Analysis module still emits only `tokens[]`. `wordcloud` is a default package dependency so Basic clouds work on a plain `pip install -e .`; Analyse still falls back to token-weight bars if import fails.

## Do not

- Import TranscriptX at runtime.
- Port the TX chart registry / Folium / speaker timelines.
- Treat Advanced JSON as the primary product path.
