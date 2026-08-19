"""Chart colour palettes for analysis View bar charts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from transcribe.tagging.colors import parse_hex_color

DEFAULT_SENTIMENT_COLORS: dict[str, str] = {
    "negative": "#c43c3c",
    "neutral": "#e6b422",
    "positive": "#2f8f4e",
}

DEFAULT_EMOTION_COLORS: dict[str, str] = {
    "anger": "#c43c3c",
    "fear": "#e07070",
    "joy": "#2f8f4e",
    "sadness": "#888888",
    "surprise": "#e6b422",
    "trust": "#4a7ab8",
}

SENTIMENT_ORDER = ("negative", "neutral", "positive")
EMOTION_ORDER = ("anger", "fear", "joy", "sadness", "surprise", "trust")


def _sanitise_palette(
    raw: Any,
    *,
    defaults: Mapping[str, str],
) -> dict[str, str]:
    out = dict(defaults)
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        label = str(key).strip().casefold()
        if not label or label not in defaults:
            continue
        try:
            out[label] = parse_hex_color(str(value))
        except ValueError:
            continue
    return out


def sanitise_chart_colors(data: Mapping[str, Any] | None) -> dict[str, dict[str, str]]:
    data = data or {}
    return {
        "sentiment": _sanitise_palette(data.get("sentiment"), defaults=DEFAULT_SENTIMENT_COLORS),
        "emotion": _sanitise_palette(data.get("emotion"), defaults=DEFAULT_EMOTION_COLORS),
    }


def color_for_label(label: str, palette: Mapping[str, str], *, fallback: str = "#888888") -> str:
    key = str(label).casefold()
    return palette.get(key, fallback)


def render_colored_bar_pairs(
    pairs: list[tuple[str, float]],
    *,
    x_name: str,
    y_name: str,
    palette: Mapping[str, str],
    sort_order: Sequence[str] | None = None,
    fallback: str = "#888888",
) -> None:
    if not pairs:
        return
    order: list[str] = []
    if sort_order:
        order = [k for k in sort_order if any(label == k for label, _ in pairs)]
    for label, _ in pairs:
        if label not in order:
            order.append(label)
    sorted_pairs = sorted(
        pairs,
        key=lambda p: order.index(p[0]) if p[0] in order else len(order),
    )
    labels = [k for k, _ in sorted_pairs]
    values = [v for _, v in sorted_pairs]
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame({x_name: labels, y_name: values})
        color_scale = alt.Scale(
            domain=labels,
            range=[color_for_label(t, palette, fallback=fallback) for t in labels],
        )
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X(f"{x_name}:N", title=x_name, sort=order),
                y=alt.Y(f"{y_name}:Q", title=y_name),
                color=alt.Color(f"{x_name}:N", scale=color_scale, legend=None),
                tooltip=[
                    alt.Tooltip(f"{x_name}:N", title=x_name.title()),
                    alt.Tooltip(f"{y_name}:Q", title=y_name.title()),
                ],
            )
            .properties(height=220)
        )
        st.altair_chart(chart, width="stretch")
    except Exception:
        st.bar_chart({x_name: labels, y_name: values}, x=x_name, y=y_name)
