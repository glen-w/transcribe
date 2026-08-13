# Analyse visual compare (TranscriptX alignment)

Authority: developer note. Does not redefine runtime contracts.

## Problem

Published Analyse results often looked like “ready” chips or Advanced JSON
dumps. Several Overview / Summaries extractors looked for top-level keys the
modules never emit (e.g. `type_token_ratio` vs `document.ttr`).

## TranscriptX inspiration

TX `lexical_diversity` drew **bar charts by speaker** (TTR / MTLD / hapax).
Transcribe has no speakers. The spiritual analogue is:

**this notebook vs peer notebooks** — entire corpus average, or a period the
user selects (year / date range), using each notebook’s diary `date_start` /
`date_end` (same period language as Archive / Search).

## What shipped

| Layer | Role |
|-------|------|
| `services/analysis_compare.py` | Extract comparable metrics; average published payloads across projects with period filter |
| `ui/analysis_compare_view.py` | Period controls + grouped bar charts |
| `ui/analysis_product_views.py` | Correct payload read-models; page series charts; summaries field fixes; wire compare |

Comparable modules: `stats`, `lexical_diversity`, `understandability`,
`sentiment`, `emotion`, `affect_tension`, `epistemic_markers`.

Within-notebook visuals (not corpus compare): token/TTR series, sentiment /
emotion / tension lines, topic-shift similarity line, keyphrase / motif bars.

## Intentional divergences from TX

1. **Peers, not speakers** — notebook domain.
2. **Streamlit charts** — no Plotly/matplotlib chart registry or viz_id artifacts.
3. **Read-model only** — never re-runs modules; averages published envelopes.
4. **Exclude current notebook** from the average so deltas are vs peers.
5. **Undated notebooks** included for “Entire corpus”, excluded for year/range.

## Do not

- Import TranscriptX at runtime.
- Port the TX chart registry / Folium / speaker timelines.
- Treat Advanced JSON as the primary product path.
