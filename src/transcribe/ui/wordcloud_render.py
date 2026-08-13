"""Render published wordcloud token frequencies as basic or advanced clouds.

Aligned with TranscriptX:
- **Basic** — ``WordCloud.generate_from_frequencies`` → Pillow image
  (``plotting.py``), shown with ``st.image``.
- **Advanced** — interactive explorer HTML (``terms_io._build_wordcloud_explorer_html``)
  with search / top-N / min-value / sort / CSV, using vendored ``wordcloud2.js``
  (offline; TX loads the same library from a CDN).

Analysis still emits only ``tokens[]``; all rendering is UI-side.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Literal

# Soft optional — UI extras include ``wordcloud``; analysis still works without it.
_WORDCLOUD_IMPORT_ERROR: str | None = None
try:
    from wordcloud import WordCloud as _WordCloud
except Exception as exc:  # noqa: BLE001 — optional dep
    _WordCloud = None  # type: ignore[misc, assignment]
    _WORDCLOUD_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_WORDCLOUD2_JS = _ASSETS_DIR / "wordcloud2.js"

SortMode = Literal["value", "term", "rank"]


def wordcloud_available() -> bool:
    return _WordCloud is not None


def wordcloud_unavailable_reason() -> str | None:
    if _WordCloud is not None:
        return None
    return (
        "Optional package `wordcloud` is not installed. "
        "Install UI extras (``pip install -e '.[ui]'``) for real word clouds; "
        "token bars still work without it."
        + (f" ({_WORDCLOUD_IMPORT_ERROR})" if _WORDCLOUD_IMPORT_ERROR else "")
    )


def wordcloud2_js_available() -> bool:
    return _WORDCLOUD2_JS.is_file()


def frequencies_from_tokens(tokens: list[dict[str, Any]] | None) -> dict[str, float]:
    """Build WordCloud frequencies from ``wordclouds_payload_v1`` token rows."""
    freq: dict[str, float] = {}
    if not isinstance(tokens, list):
        return freq
    for row in tokens:
        if not isinstance(row, dict):
            continue
        token = row.get("token")
        if not token:
            continue
        # Prefer raw count (TX generate_from_frequencies); fall back to weight.
        raw = row.get("count")
        if raw is None:
            raw = row.get("weight")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        freq[str(token)] = value
    return freq


def terms_from_tokens(tokens: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """TX ``WordcloudTerms.terms`` shape: ``{term, value, rank}`` sorted by value."""
    freq = frequencies_from_tokens(tokens)
    ranked = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"term": term, "value": float(value), "rank": idx + 1}
        for idx, (term, value) in enumerate(ranked)
    ]


def terms_payload_from_analysis(
    payload: dict[str, Any],
    *,
    title: str = "Word themes",
) -> dict[str, Any]:
    """Explorer JSON payload mirrored from TX ``_build_terms_payload``."""
    tokens = payload.get("tokens") if isinstance(payload, dict) else None
    terms = terms_from_tokens(tokens if isinstance(tokens, list) else None)
    return {
        "source": "wordclouds",
        "variant": "basic",
        "variant_key": "basic_unigram",
        "speaker": None,
        "ngram": 1,
        "metric": "count",
        "terms": terms,
        "title": title,
    }


def filter_terms(
    terms: list[dict[str, Any]],
    *,
    search: str = "",
    top_n: int = 50,
    min_value: float = 0.0,
    sort_mode: SortMode = "value",
) -> list[dict[str, Any]]:
    """Apply TX explorer filters (search / min value / sort / top N)."""
    needle = (search or "").casefold().strip()
    items = [
        t
        for t in terms
        if isinstance(t, dict)
        and float(t.get("value") or 0) >= float(min_value)
        and (not needle or needle in str(t.get("term") or "").casefold())
    ]
    if sort_mode == "term":
        items.sort(key=lambda t: str(t.get("term") or "").casefold())
    elif sort_mode == "rank":
        items.sort(key=lambda t: int(t.get("rank") or 10**9))
    else:
        items.sort(key=lambda t: (-float(t.get("value") or 0), str(t.get("term") or "")))
    n = max(1, int(top_n))
    return items[:n]


def render_wordcloud_image(
    frequencies: dict[str, float],
    *,
    width: int = 900,
    height: int = 420,
    background_color: str = "white",
    max_words: int = 100,
    prefer_horizontal: float = 0.85,
) -> Any | None:
    """Return a Pillow Image, or None when the optional dep / freqs are missing.

    TX uses white background and ``generate_from_frequencies``; we mirror that
    and return ``wc.to_image()`` for ``st.image`` (no matplotlib figure).
    """
    if _WordCloud is None or not frequencies:
        return None
    # Deterministic layout seed so reopening Overview does not reshuffle glyphs.
    wc = _WordCloud(
        width=max(200, int(width)),
        height=max(120, int(height)),
        background_color=background_color,
        max_words=max(1, int(max_words)),
        prefer_horizontal=prefer_horizontal,
        collocations=False,
        random_state=42,
    )
    wc.generate_from_frequencies(frequencies)
    return wc.to_image()


def render_wordcloud_from_payload(
    payload: dict[str, Any],
    *,
    width: int = 900,
    height: int = 420,
) -> Any | None:
    tokens = payload.get("tokens") if isinstance(payload, dict) else None
    freq = frequencies_from_tokens(tokens if isinstance(tokens, list) else None)
    max_words = len(freq) if freq else 100
    return render_wordcloud_image(
        freq, width=width, height=height, max_words=max_words
    )


def build_wordcloud_explorer_html(
    title: str,
    terms_payload: dict[str, Any],
    *,
    wordcloud2_js: str | None = None,
) -> str:
    """TX-style interactive explorer HTML (search, top N, min value, sort, CSV).

    ``wordcloud2.js`` is inlined from vendored assets so Advanced mode works
    offline (TX loads the same library from jsDelivr).
    """
    js_src = wordcloud2_js
    if js_src is None:
        if not _WORDCLOUD2_JS.is_file():
            raise FileNotFoundError(
                f"vendored wordcloud2.js missing at {_WORDCLOUD2_JS}"
            )
        js_src = _WORDCLOUD2_JS.read_text(encoding="utf-8")
    safe_title = html.escape(title or "Word themes")
    # Payload is JSON-embedded; json.dumps handles escaping for </script>.
    terms_json = json.dumps(terms_payload, ensure_ascii=False).replace(
        "</", "<\\/"
    )
    # Script body must not close early; wordcloud2.js is trusted vendored source.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <script>{js_src}</script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 12px; background: #fff; color: #222; }}
    .controls {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; align-items: flex-end; }}
    .controls label {{ font-size: 12px; color: #333; }}
    .controls input, .controls select, .controls button {{
      font-size: 13px; padding: 4px 8px;
    }}
    #cloudWrap {{ width: 100%; height: 420px; position: relative; }}
    #wordcloudCanvas {{ display: block; width: 100%; height: 100%; border: 1px solid #e6e6e6; }}
    #wordcloudEmptyState {{
      position: absolute; inset: 0; display: flex; align-items: center;
      justify-content: center; text-align: center; padding: 16px;
      color: #555; font-size: 14px; background: #fafafa; border: 1px solid #e0e0e0;
      box-sizing: border-box;
    }}
    #wordcloudEmptyState[hidden] {{ display: none !important; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; font-size: 12px; }}
    th {{ background: #f5f5f5; text-align: left; }}
    .actions {{ display: flex; gap: 8px; }}
  </style>
</head>
<body>
  <div class="controls">
    <label>Search<br><input id="search" type="text" placeholder="filter terms"></label>
    <label>Top N<br><input id="topN" type="number" value="50" min="1" max="500"></label>
    <label>Min Value<br><input id="minValue" type="number" value="0" step="0.01"></label>
    <label>Sort<br>
      <select id="sortMode">
        <option value="value">Value</option>
        <option value="term">Term</option>
        <option value="rank">Rank</option>
      </select>
    </label>
    <div class="actions">
      <button id="copyTerms" type="button">Copy filtered terms</button>
      <button id="downloadCsv" type="button">Download CSV</button>
    </div>
  </div>
  <div id="cloudWrap">
    <canvas id="wordcloudCanvas" width="800" height="420" aria-label="Word cloud"></canvas>
    <div id="wordcloudEmptyState" data-wordcloud-empty="1" hidden>No terms match the current filters.</div>
  </div>
  <div id="table"></div>
  <script>
    window.WORDCLOUD_TERMS = {terms_json};
  </script>
  <script>
    const MAX_CLOUD_WORDS = 120;
    const MIN_FONT_CSS = 14;
    const MAX_FONT_CSS = 72;
    const GRID_SIZE = 14;

    const terms = window.WORDCLOUD_TERMS.terms || [];
    const searchInput = document.getElementById('search');
    const topNInput = document.getElementById('topN');
    const minValueInput = document.getElementById('minValue');
    const sortModeInput = document.getElementById('sortMode');
    const tableContainer = document.getElementById('table');
    const cloudWrap = document.getElementById('cloudWrap');
    const canvas = document.getElementById('wordcloudCanvas');
    const emptyState = document.getElementById('wordcloudEmptyState');

    let resizeTimer = null;

    function filteredTerms() {{
      const search = searchInput.value.toLowerCase();
      const minValue = parseFloat(minValueInput.value || '0');
      const topN = parseInt(topNInput.value || '50', 10);
      let items = terms.filter(t => String(t.term || '').toLowerCase().includes(search) && Number(t.value) >= minValue);
      const sortMode = sortModeInput.value;
      if (sortMode === 'term') {{
        items = items.sort((a, b) => String(a.term).localeCompare(String(b.term)));
      }} else if (sortMode === 'rank') {{
        items = items.sort((a, b) => a.rank - b.rank);
      }} else {{
        items = items.sort((a, b) => b.value - a.value);
      }}
      return items.slice(0, topN);
    }}

    function renderTable(items) {{
      const rows = items.map(t => `<tr><td>${{t.rank}}</td><td>${{t.term}}</td><td>${{t.value}}</td></tr>`).join('');
      tableContainer.innerHTML = `
        <table>
          <thead><tr><th>Rank</th><th>Term</th><th>Value</th></tr></thead>
          <tbody>${{rows}}</tbody>
        </table>`;
    }}

    function syncCanvasToLayout() {{
      const dpr = window.devicePixelRatio || 1;
      const rect = cloudWrap.getBoundingClientRect();
      const cssW = Math.max(1, Math.floor(rect.width));
      const cssH = Math.max(1, Math.floor(rect.height));
      canvas.style.width = cssW + 'px';
      canvas.style.height = cssH + 'px';
      canvas.width = Math.max(1, Math.round(cssW * dpr));
      canvas.height = Math.max(1, Math.round(cssH * dpr));
      return dpr;
    }}

    function clearCloudCanvas() {{
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }}

    function buildCloudList(items) {{
      const cap = Math.min(items.length, MAX_CLOUD_WORDS);
      const slice = items.slice(0, cap);
      const scaled = slice.map(t => Math.sqrt(Math.max(Number(t.value), 0)));
      if (scaled.length === 0) return [];
      const minS = Math.min.apply(null, scaled);
      const maxS = Math.max.apply(null, scaled);
      let norm;
      if (minS === maxS) {{
        norm = scaled.map(() => 0.5);
      }} else {{
        norm = scaled.map(s => (s - minS) / (maxS - minS));
      }}
      return slice.map((t, i) => [t.term, norm[i]]);
    }}

    function renderCloud(items) {{
      const dpr = syncCanvasToLayout();
      if (items.length === 0) {{
        return;
      }}
      const list = buildCloudList(items);
      if (list.length === 0) {{
        clearCloudCanvas();
        return;
      }}
      try {{
        WordCloud.stop();
      }} catch (e) {{}}

      const weightToPx = function (w) {{
        return (MIN_FONT_CSS + w * (MAX_FONT_CSS - MIN_FONT_CSS)) * dpr;
      }};

      WordCloud(canvas, {{
        list: list,
        gridSize: GRID_SIZE,
        weightFactor: weightToPx,
        minRotation: 0,
        maxRotation: 0,
        rotateRatio: 0,
        shuffle: false,
        backgroundColor: '#fff',
        color: 'random-dark',
        clearCanvas: true,
        drawOutOfBound: false
      }});
    }}

    function render() {{
      const items = filteredTerms();
      renderTable(items);
      if (items.length === 0) {{
        emptyState.removeAttribute('hidden');
        emptyState.textContent = 'No terms match the current filters.';
        syncCanvasToLayout();
        clearCloudCanvas();
        return;
      }}
      if (typeof WordCloud === 'undefined') {{
        emptyState.removeAttribute('hidden');
        emptyState.textContent = 'Word cloud library failed to load.';
        syncCanvasToLayout();
        clearCloudCanvas();
        return;
      }}
      emptyState.setAttribute('hidden', '');
      renderCloud(items);
    }}

    function scheduleRender() {{
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(function () {{
        resizeTimer = null;
        render();
      }}, 150);
    }}

    function toCsv(items) {{
      const rows = ['term,value'].concat(items.map(t => `${{t.term}},${{t.value}}`));
      return rows.join('\\n');
    }}

    document.getElementById('copyTerms').addEventListener('click', () => {{
      const items = filteredTerms();
      const csv = toCsv(items);
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(csv);
      }}
    }});

    document.getElementById('downloadCsv').addEventListener('click', () => {{
      const items = filteredTerms();
      const csv = toCsv(items);
      const blob = new Blob([csv], {{ type: 'text/csv' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'wordcloud_terms.csv';
      a.click();
      URL.revokeObjectURL(url);
    }});

    searchInput.addEventListener('input', render);
    topNInput.addEventListener('input', render);
    minValueInput.addEventListener('input', render);
    sortModeInput.addEventListener('change', render);
    window.addEventListener('resize', scheduleRender);
    if (typeof ResizeObserver !== 'undefined') {{
      const ro = new ResizeObserver(scheduleRender);
      ro.observe(cloudWrap);
    }}
    render();
  </script>
</body>
</html>"""


def render_wordcloud_section(
    payload: dict[str, Any],
    *,
    key_prefix: str = "overview_wc",
) -> None:
    """Streamlit product control: Basic static cloud vs Advanced TX explorer."""
    import streamlit as st
    import streamlit.components.v1 as components

    from transcribe.ui.analysis_display_helpers import wordcloud_rows

    rows = wordcloud_rows(payload, limit=100)
    if not rows:
        st.info("Word themes: no tokens yet.")
        return

    mode = st.radio(
        "Word cloud mode",
        ("Basic", "Advanced"),
        horizontal=True,
        key=f"{key_prefix}_mode",
        help=(
            "Basic: static frequency cloud (TranscriptX PNG path). "
            "Advanced: interactive explorer with search, top N, min value, "
            "sort, and CSV export (TranscriptX wordcloud explorer)."
        ),
    )

    if mode == "Advanced":
        if not wordcloud2_js_available():
            st.warning(
                "Advanced explorer assets are missing (`wordcloud2.js`). "
                "Showing Basic mode instead."
            )
            mode = "Basic"
        else:
            terms_payload = terms_payload_from_analysis(payload, title="Word themes")
            explorer = build_wordcloud_explorer_html("Word themes", terms_payload)
            components.html(explorer, height=720, scrolling=True)
            st.caption(
                "Advanced explorer runs locally (vendored wordcloud2.js) — "
                "adjust filters above the cloud; copy or download CSV of the filtered terms."
            )
            return

    # Basic (default)
    image = render_wordcloud_from_payload(payload)
    if image is not None:
        st.image(image, width="stretch")
    elif not wordcloud_available():
        st.caption(wordcloud_unavailable_reason() or "")
    with st.expander("Token weights", expanded=image is None):
        st.bar_chart(
            {
                "token": [r["token"] for r in rows[:40]],
                "weight": [r["weight"] for r in rows[:40]],
            },
            x="token",
            y="weight",
        )
        top = rows[:12]
        st.caption(
            "Top · "
            + " · ".join(
                f"{r['token']}×{r['count']}" if r["count"] else r["token"] for r in top
            )
        )
