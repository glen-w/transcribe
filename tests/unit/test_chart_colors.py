"""Chart colour palettes for analysis View bar charts."""

from __future__ import annotations

from transcribe.ui.chart_colors import (
    DEFAULT_EMOTION_COLORS,
    DEFAULT_SENTIMENT_COLORS,
    color_for_label,
    sanitise_chart_colors,
)


def test_sanitise_chart_colors_defaults_when_empty() -> None:
    out = sanitise_chart_colors(None)
    assert out["sentiment"] == DEFAULT_SENTIMENT_COLORS
    assert out["emotion"] == DEFAULT_EMOTION_COLORS


def test_sanitise_chart_colors_merges_valid_overrides() -> None:
    out = sanitise_chart_colors(
        {
            "sentiment": {"negative": "#ff0000", "bogus": "#123456"},
            "emotion": {"joy": "2f8f4e", "anger": "not-a-color"},
        }
    )
    assert out["sentiment"]["negative"] == "#ff0000"
    assert out["sentiment"]["neutral"] == DEFAULT_SENTIMENT_COLORS["neutral"]
    assert out["emotion"]["joy"] == "#2f8f4e"
    assert out["emotion"]["anger"] == DEFAULT_EMOTION_COLORS["anger"]


def test_color_for_label_casefold() -> None:
    palette = {"joy": "#2f8f4e"}
    assert color_for_label("Joy", palette) == "#2f8f4e"
    assert color_for_label("sadness", palette) == "#888888"
