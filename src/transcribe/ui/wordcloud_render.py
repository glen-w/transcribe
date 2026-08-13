"""Render published wordcloud token frequencies as a real word-cloud image.

Aligned with TranscriptX ``core/analysis/wordclouds/plotting.py``:
``WordCloud(...).generate_from_frequencies(freq)`` then display the raster.
Transcribe keeps frequencies in the analysis payload (contract) and renders
here in the UI so the analysis core stays free of the optional ``wordcloud``
dependency. Uses ``to_image()`` (Pillow) — no matplotlib required for Streamlit.
"""

from __future__ import annotations

from typing import Any

# Soft optional — UI extras include ``wordcloud``; analysis still works without it.
_WORDCLOUD_IMPORT_ERROR: str | None = None
try:
    from wordcloud import WordCloud as _WordCloud
except Exception as exc:  # noqa: BLE001 — optional dep
    _WordCloud = None  # type: ignore[misc, assignment]
    _WORDCLOUD_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


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
