"""Clickable Altair charts for per-page Analyse series (order on x-axis)."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from transcribe.ui.page_series_selection import PAGE_SELECT, selected_page_id

_DEFAULT_HEIGHT = 220


def render_clickable_page_series(
    rows: Sequence[dict[str, Any]],
    *,
    y: str | Sequence[str],
    key: str,
    chart_type: str = "line",
    x_title: str = "Page order",
    height: int = _DEFAULT_HEIGHT,
) -> str | None:
    """Render a page-order series; return a newly clicked ``page_id`` once.

    Each row must include ``order``, ``page_id``, and the y field(s). Empty /
    missing ``page_id`` rows are skipped for selection. Falls back to a
    non-clickable Streamlit chart when Altair/pandas is unavailable.
    """
    y_fields = [y] if isinstance(y, str) else list(y)
    if not y_fields:
        return None
    usable = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("page_id")
        and r.get("order") is not None
        and all(r.get(f) is not None for f in y_fields)
    ]
    if not usable:
        return None

    selected: str | None = None
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame(usable)
        point = alt.selection_point(
            name=PAGE_SELECT,
            fields=["page_id"],
            toggle=False,
        )
        x_enc = alt.X(
            "order:Q",
            title=x_title,
            axis=alt.Axis(tickMinStep=1, grid=False),
        )
        if chart_type == "bar" and len(y_fields) == 1:
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=x_enc,
                    y=alt.Y(f"{y_fields[0]}:Q", title=y_fields[0]),
                    opacity=alt.condition(point, alt.value(1.0), alt.value(0.55)),
                    tooltip=[
                        alt.Tooltip("order:Q", title="Order"),
                        alt.Tooltip(f"{y_fields[0]}:Q", title=y_fields[0]),
                        alt.Tooltip("page_id:N", title="Page"),
                    ],
                )
                .add_params(point)
                .properties(height=height)
            )
        elif chart_type == "bar" and len(y_fields) > 1:
            long = df.melt(
                id_vars=["order", "page_id"],
                value_vars=y_fields,
                var_name="series",
                value_name="value",
            )
            chart = (
                alt.Chart(long)
                .mark_bar()
                .encode(
                    x=x_enc,
                    y=alt.Y("value:Q", title=None),
                    color=alt.Color("series:N", title=None),
                    xOffset="series:N",
                    opacity=alt.condition(point, alt.value(1.0), alt.value(0.55)),
                    tooltip=[
                        alt.Tooltip("order:Q", title="Order"),
                        alt.Tooltip("series:N", title="Series"),
                        alt.Tooltip("value:Q", title="Value"),
                        alt.Tooltip("page_id:N", title="Page"),
                    ],
                )
                .add_params(point)
                .properties(height=height)
            )
        else:
            # Line + clickable points (multi-series melts to long form).
            if len(y_fields) == 1:
                base = alt.Chart(df)
                line = base.mark_line(point=False).encode(
                    x=x_enc,
                    y=alt.Y(f"{y_fields[0]}:Q", title=y_fields[0]),
                )
                pts = (
                    base.mark_circle(size=64)
                    .encode(
                        x=x_enc,
                        y=alt.Y(f"{y_fields[0]}:Q", title=y_fields[0]),
                        opacity=alt.condition(point, alt.value(1.0), alt.value(0.65)),
                        tooltip=[
                            alt.Tooltip("order:Q", title="Order"),
                            alt.Tooltip(f"{y_fields[0]}:Q", title=y_fields[0]),
                            alt.Tooltip("page_id:N", title="Page"),
                        ],
                    )
                    .add_params(point)
                )
                chart = (line + pts).properties(height=height)
            else:
                long = df.melt(
                    id_vars=["order", "page_id"],
                    value_vars=y_fields,
                    var_name="series",
                    value_name="value",
                )
                base = alt.Chart(long)
                line = base.mark_line(point=False).encode(
                    x=x_enc,
                    y=alt.Y("value:Q", title=None),
                    color=alt.Color("series:N", title=None),
                )
                pts = (
                    base.mark_circle(size=64)
                    .encode(
                        x=x_enc,
                        y=alt.Y("value:Q", title=None),
                        color=alt.Color("series:N", title=None),
                        opacity=alt.condition(point, alt.value(1.0), alt.value(0.65)),
                        tooltip=[
                            alt.Tooltip("order:Q", title="Order"),
                            alt.Tooltip("series:N", title="Series"),
                            alt.Tooltip("value:Q", title="Value"),
                            alt.Tooltip("page_id:N", title="Page"),
                        ],
                    )
                    .add_params(point)
                )
                chart = (line + pts).properties(height=height)

        spec = chart.to_dict()
        view_cfg = spec.setdefault("config", {}).setdefault("view", {})
        view_cfg.pop("continuousWidth", None)
        view_cfg.pop("continuousHeight", None)
        spec["width"] = "container"
        spec["autosize"] = {"type": "fit-x", "contains": "padding"}

        gen = int(st.session_state.get(f"{key}_gen", 0))
        event = st.vega_lite_chart(
            spec,
            width="stretch",
            key=f"{key}__{gen}",
            on_select="rerun",
            selection_mode=PAGE_SELECT,
        )
        page_id = selected_page_id(event)
        if page_id:
            st.session_state[f"{key}_gen"] = gen + 1
            selected = page_id
    except Exception:
        _fallback_native(usable, y_fields, chart_type=chart_type, height=height)
    return selected


def _fallback_native(
    rows: Sequence[dict[str, Any]],
    y_fields: list[str],
    *,
    chart_type: str,
    height: int,
) -> None:
    data: dict[str, list[Any]] = {"order": [r["order"] for r in rows]}
    for f in y_fields:
        data[f] = [r[f] for r in rows]
    if chart_type == "bar":
        st.bar_chart(data, x="order", y=y_fields if len(y_fields) > 1 else y_fields[0], height=height)
    else:
        st.line_chart(data, x="order", y=y_fields if len(y_fields) > 1 else y_fields[0], height=height)


def maybe_jump(page_id: str | None, on_jump: Any) -> None:
    """Invoke ``on_jump(page_id)`` when both are present."""
    if page_id and callable(on_jump):
        on_jump(str(page_id))
