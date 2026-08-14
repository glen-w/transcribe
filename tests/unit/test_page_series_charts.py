"""Deep tests for clickable page-series chart rendering and jump wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from transcribe.analysis.health import AnalysisHealth, ModuleHealth
from transcribe.ui.page_series_selection import PAGE_SELECT, selected_page_id


def _rows_sentiment() -> list[dict[str, Any]]:
    return [
        {"order": 1, "page_id": "page-a", "compound": -0.2},
        {"order": 2, "page_id": "page-b", "compound": 0.5},
        {"order": 3, "page_id": "page-c", "compound": 0.1},
    ]


def _rows_epistemic() -> list[dict[str, Any]]:
    return [
        {"order": 1, "page_id": "page-a", "hedges": 2, "boosters": 1},
        {"order": 2, "page_id": "page-b", "hedges": 0, "boosters": 4},
    ]


def _click_event(page_id: str) -> SimpleNamespace:
    return SimpleNamespace(selection={PAGE_SELECT: [{"page_id": page_id}]})


def _param_names(spec: dict[str, Any]) -> list[str]:
    params = spec.get("params") or []
    # Layered charts nest params on layer entries.
    names = [p.get("name") for p in params if isinstance(p, dict)]
    for layer in spec.get("layer") or []:
        if isinstance(layer, dict):
            for p in layer.get("params") or []:
                if isinstance(p, dict):
                    names.append(p.get("name"))
    return [n for n in names if n]


def _mark_types(spec: dict[str, Any]) -> set[str]:
    marks: set[str] = set()
    top = spec.get("mark")
    if isinstance(top, str):
        marks.add(top)
    elif isinstance(top, dict) and top.get("type"):
        marks.add(str(top["type"]))
    for layer in spec.get("layer") or []:
        if not isinstance(layer, dict):
            continue
        m = layer.get("mark")
        if isinstance(m, str):
            marks.add(m)
        elif isinstance(m, dict) and m.get("type"):
            marks.add(str(m["type"]))
    return marks


def test_line_chart_click_returns_page_id_and_remounts() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.return_value = _click_event("page-b")
        clicked = render_clickable_page_series(
            _rows_sentiment(),
            y="compound",
            key="sentiment_line",
            chart_type="line",
        )
    assert clicked == "page-b"
    assert st.session_state["sentiment_line_gen"] == 1
    kwargs = st.vega_lite_chart.call_args.kwargs
    assert kwargs["on_select"] == "rerun"
    assert kwargs["selection_mode"] == PAGE_SELECT
    assert kwargs["key"] == "sentiment_line__0"
    spec = st.vega_lite_chart.call_args.args[0]
    assert PAGE_SELECT in _param_names(spec)
    assert "line" in _mark_types(spec)
    assert "circle" in _mark_types(spec)
    assert spec.get("width") == "container"
    assert spec.get("autosize", {}).get("type") == "fit-x"


def test_second_click_same_page_uses_bumped_widget_key() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {"sentiment_line_gen": 1}
        st.vega_lite_chart.return_value = _click_event("page-b")
        clicked = render_clickable_page_series(
            _rows_sentiment(),
            y="compound",
            key="sentiment_line",
        )
    assert clicked == "page-b"
    assert st.vega_lite_chart.call_args.kwargs["key"] == "sentiment_line__1"
    assert st.session_state["sentiment_line_gen"] == 2


def test_no_selection_does_not_bump_gen() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.return_value = SimpleNamespace(selection={})
        clicked = render_clickable_page_series(
            _rows_sentiment(),
            y="compound",
            key="quiet",
        )
    assert clicked is None
    assert "quiet_gen" not in st.session_state


def test_bar_chart_single_series_mark_and_click() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    rows = [
        {"order": 1, "page_id": "p1", "token_count": 40.0},
        {"order": 2, "page_id": "p2", "token_count": 55.0},
    ]
    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.return_value = _click_event("p2")
        clicked = render_clickable_page_series(
            rows,
            y="token_count",
            key="tokens",
            chart_type="bar",
        )
    assert clicked == "p2"
    spec = st.vega_lite_chart.call_args.args[0]
    assert "bar" in _mark_types(spec)
    assert PAGE_SELECT in _param_names(spec)


def test_bar_chart_multi_series_melt_preserves_page_id() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.return_value = _click_event("page-a")
        clicked = render_clickable_page_series(
            _rows_epistemic(),
            y=["hedges", "boosters"],
            key="epistemic",
            chart_type="bar",
        )
    assert clicked == "page-a"
    spec = st.vega_lite_chart.call_args.args[0]
    assert "bar" in _mark_types(spec)
    # Melted dataset still carries page_id for selection.
    datasets = spec.get("datasets") or {}
    data_name = (spec.get("data") or {}).get("name")
    rows = datasets.get(data_name) if data_name else None
    if rows is None and isinstance(spec.get("data"), dict):
        rows = spec["data"].get("values")
    assert rows is not None
    assert any(r.get("page_id") == "page-a" for r in rows)
    assert any(r.get("series") in {"hedges", "boosters"} for r in rows)


def test_skips_incomplete_rows_and_empty_input() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        assert (
            render_clickable_page_series(
                [{"order": 1, "compound": 0.1}],  # missing page_id
                y="compound",
                key="bad",
            )
            is None
        )
        assert render_clickable_page_series([], y="compound", key="empty") is None
        assert render_clickable_page_series(_rows_sentiment(), y=[], key="noy") is None
        st.vega_lite_chart.assert_not_called()


def test_fallback_line_when_vega_raises() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.side_effect = RuntimeError("vega broken")
        clicked = render_clickable_page_series(
            _rows_sentiment(),
            y="compound",
            key="fallback",
            chart_type="line",
        )
    assert clicked is None
    st.line_chart.assert_called_once()
    call = st.line_chart.call_args
    assert call.args[0]["order"] == [1, 2, 3]
    assert call.kwargs["x"] == "order"
    assert call.kwargs["y"] == "compound"


def test_fallback_bar_when_vega_raises() -> None:
    from transcribe.ui.page_series_charts import render_clickable_page_series

    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.side_effect = RuntimeError("vega broken")
        clicked = render_clickable_page_series(
            [{"order": 1, "page_id": "p1", "token_count": 3}],
            y="token_count",
            key="fb_bar",
            chart_type="bar",
        )
    assert clicked is None
    st.bar_chart.assert_called_once()
    assert st.bar_chart.call_args.kwargs["y"] == "token_count"


def test_maybe_jump_invokes_only_when_ready() -> None:
    from transcribe.ui.page_series_charts import maybe_jump

    jumps: list[str] = []
    maybe_jump("p1", jumps.append)
    maybe_jump(None, jumps.append)
    maybe_jump("p2", None)
    maybe_jump("p3", "not-callable")  # type: ignore[arg-type]
    assert jumps == ["p1"]


def test_selected_page_id_dict_event_shape() -> None:
    assert (
        selected_page_id({"selection": {PAGE_SELECT: [{"page_id": "dict-page"}]}})
        == "dict-page"
    )


def _ok_module(module_id: str, payload: dict[str, Any]) -> ModuleHealth:
    return ModuleHealth(
        module_id=module_id,
        freshness="ok",
        capability="ready",
        outcome="success",
        envelope={"outcome": "success", "payload": payload, "warnings": [], "evidence": []},
        live_evidence=[],
    )


def _health(modules: dict[str, ModuleHealth]) -> AnalysisHealth:
    return AnalysisHealth(
        content_revision="rev",
        modules=modules,
        aggregate="healthy",
        active_run_status=None,
        scoped_module_ids=tuple(modules.keys()),
    )


def test_mood_sentiment_chart_click_calls_on_jump() -> None:
    from transcribe.ui.analysis_product_views import render_mood_product

    payload = {
        "units": [
            {"order": 1, "unit_id": "page-a", "compound": -0.1},
            {"order": 2, "unit_id": "page-b", "compound": 0.4},
        ],
        "global_stats": {"compound_mean": 0.15},
    }
    health = _health({"sentiment": _ok_module("sentiment", payload)})
    jumps: list[str] = []

    with (
        patch("transcribe.ui.analysis_product_views.st") as st,
        patch(
            "transcribe.ui.analysis_product_views.render_clickable_page_series",
            return_value="page-b",
        ) as chart,
        patch("transcribe.ui.analysis_product_views.render_advanced_payload"),
        patch("transcribe.ui.analysis_product_views._maybe_compare"),
    ):
        st.session_state = {}
        render_mood_product(
            health,
            ["sentiment"],
            project_id="nb1",
            on_jump=jumps.append,
        )

    assert jumps == ["page-b"]
    assert chart.call_args.kwargs["y"] == "compound"
    assert "mood_sentiment_nb1" in chart.call_args.kwargs["key"]


def test_overview_tokens_chart_click_calls_on_jump() -> None:
    from transcribe.ui.analysis_product_views import render_overview_product

    payload = {
        "units": [
            {"order": 1, "unit_id": "tok-1", "token_count": 12},
            {"order": 2, "unit_id": "tok-2", "token_count": 20},
        ],
        "document": {},
    }
    health = _health({"stats": _ok_module("stats", payload)})
    jumps: list[str] = []

    with (
        patch("transcribe.ui.analysis_product_views.st") as st,
        patch(
            "transcribe.ui.analysis_product_views.render_clickable_page_series",
            return_value="tok-2",
        ) as chart,
        patch("transcribe.ui.analysis_product_views.render_advanced_payload"),
        patch("transcribe.ui.analysis_product_views._maybe_compare"),
        patch(
            "transcribe.ui.analysis_product_views.extract_foundations_display",
            return_value=[],
        ),
    ):
        st.session_state = {}
        render_overview_product(
            health,
            ["stats"],
            project_id="nb1",
            on_jump=jumps.append,
        )

    assert jumps == ["tok-2"]
    assert chart.call_args.kwargs["chart_type"] == "bar"
    assert chart.call_args.kwargs["y"] == "token_count"


def test_themes_topic_shift_click_calls_on_jump() -> None:
    from transcribe.ui.analysis_product_views import render_themes_product

    payload = {
        "n_units": 2,
        "consecutive": [
            {
                "from_unit_id": "a/span:0-5",
                "from_order": 1,
                "similarity": 0.8,
            }
        ],
        "shifts": [],
    }
    health = _health({"topic_shift": _ok_module("topic_shift", payload)})
    jumps: list[str] = []

    with (
        patch("transcribe.ui.analysis_product_views.st") as st,
        patch(
            "transcribe.ui.analysis_product_views.render_clickable_page_series",
            return_value="a",
        ) as chart,
        patch("transcribe.ui.analysis_product_views.render_advanced_payload"),
    ):
        st.session_state = {}
        render_themes_product(
            health,
            ["topic_shift"],
            project_id="nb1",
            on_jump=jumps.append,
        )

    assert jumps == ["a"]
    assert chart.call_args.kwargs["y"] == "similarity"


def test_end_to_end_click_to_jump_without_mocking_chart() -> None:
    """Real Altair path: selection event → page_id → maybe_jump callback."""
    from transcribe.ui.page_series_charts import maybe_jump, render_clickable_page_series

    jumps: list[str] = []
    with patch("transcribe.ui.page_series_charts.st") as st:
        st.session_state = {}
        st.vega_lite_chart.return_value = _click_event("page-c")
        clicked = render_clickable_page_series(
            _rows_sentiment(),
            y="compound",
            key="e2e",
        )
        maybe_jump(clicked, jumps.append)
    assert jumps == ["page-c"]
    spec = st.vega_lite_chart.call_args.args[0]
    # Values embed page_ids used by selection_mode.
    datasets = spec.get("datasets") or {}
    values = None
    for layer in spec.get("layer") or [spec]:
        data = layer.get("data") if isinstance(layer, dict) else None
        if isinstance(data, dict) and data.get("values"):
            values = data["values"]
            break
        if isinstance(data, dict) and data.get("name") and data["name"] in datasets:
            values = datasets[data["name"]]
            break
    if values is None and datasets:
        values = next(iter(datasets.values()))
    assert values is not None
    assert {r["page_id"] for r in values} == {"page-a", "page-b", "page-c"}


def test_mood_emotion_and_epistemic_clicks_call_on_jump() -> None:
    from transcribe.ui.analysis_product_views import render_mood_product

    emotion = {
        "units": [{"order": 1, "unit_id": "e1", "intensity": 0.7}],
        "global_stats": {"intensity_mean": 0.7},
    }
    epistemic = {
        "units": [
            {
                "order": 1,
                "unit_id": "ep1",
                "category_counts": {"epistemic_hedge": 1, "certainty_booster": 2},
            }
        ],
        "global_stats": {},
    }
    health = _health(
        {
            "emotion": _ok_module("emotion", emotion),
            "epistemic_markers": _ok_module("epistemic_markers", epistemic),
        }
    )
    jumps: list[str] = []
    chart_returns = iter(["e1", "ep1"])

    with (
        patch("transcribe.ui.analysis_product_views.st") as st,
        patch(
            "transcribe.ui.analysis_product_views.render_clickable_page_series",
            side_effect=lambda *a, **k: next(chart_returns),
        ) as chart,
        patch("transcribe.ui.analysis_product_views.render_advanced_payload"),
        patch("transcribe.ui.analysis_product_views._maybe_compare"),
        patch(
            "transcribe.ui.analysis_product_views.emotion_label_totals",
            return_value=[],
        ),
        patch(
            "transcribe.ui.analysis_product_views.epistemic_category_bars",
            return_value=[],
        ),
    ):
        st.session_state = {}
        render_mood_product(
            health,
            ["emotion", "epistemic_markers"],
            project_id="nb1",
            on_jump=jumps.append,
        )

    assert jumps == ["e1", "ep1"]
    assert chart.call_count == 2
    assert chart.call_args_list[0].kwargs["y"] == "intensity"
    assert chart.call_args_list[1].kwargs["y"] == ["hedges", "boosters"]
    assert chart.call_args_list[1].kwargs["chart_type"] == "bar"
    from transcribe.ui.analysis_product_views import render_mood_product

    payload = {
        "units": [{"order": 1, "unit_id": "page-a", "compound": 0.2}],
        "global_stats": {},
    }
    health = _health({"sentiment": _ok_module("sentiment", payload)})

    with (
        patch("transcribe.ui.analysis_product_views.st") as st,
        patch(
            "transcribe.ui.analysis_product_views.render_clickable_page_series",
            return_value="page-a",
        ) as chart,
        patch("transcribe.ui.analysis_product_views.render_advanced_payload"),
        patch("transcribe.ui.analysis_product_views._maybe_compare"),
    ):
        st.session_state = {}
        render_mood_product(health, ["sentiment"], project_id="nb1")

    chart.assert_called_once()


def _page_row(page_id: str, ink: float) -> Any:
    from transcribe.page_metrics.models import PageMetricsRow

    return PageMetricsRow(
        page_id=page_id,
        render_id=f"r-{page_id}",
        render_sha256="abc",
        ink_coverage_pct=ink,
        blankness_pct=100.0 - ink,
        ink_hue="black",
        ink_hue_degrees=None,
        paper_tone="cream",
        width=100,
        height=100,
        pixel_count=10000,
        ink_pixel_count=int(ink * 100),
    )


def test_page_metrics_ink_click_calls_on_jump() -> None:
    from transcribe.page_metrics.models import PageMetricsRollup, PublishedPageMetrics
    from transcribe.ui.page_metrics_view import render_overview_page_metrics

    published = PublishedPageMetrics(
        project_id="proj",
        algorithm_version="test",
        cache_identity="cache",
        outcome="success",
        computed_at="2024-01-01T00:00:00Z",
        pages=(_page_row("ink-1", 12.5), _page_row("ink-2", 40.0)),
        rollup=PageMetricsRollup(
            page_count=2,
            mean_ink_coverage_pct=26.25,
            median_ink_coverage_pct=26.25,
            mean_blankness_pct=65.0,
            hue_counts={"black": 2},
        ),
    )
    jumps: list[str] = []
    project = SimpleNamespace(id="proj")

    with (
        patch("transcribe.ui.page_metrics_view.st") as st,
        patch(
            "transcribe.ui.page_metrics_view.ensure_page_metrics",
            return_value=published,
        ),
        patch(
            "transcribe.ui.page_series_charts.render_clickable_page_series",
            return_value="ink-2",
        ) as chart,
    ):
        st.session_state = {}

        def _cols(spec: Any):
            count = len(spec) if isinstance(spec, list) else int(spec)
            mocks = [MagicMock() for _ in range(count)]
            if count == 4:
                mocks[3].button.return_value = False
            return mocks

        st.columns.side_effect = _cols
        render_overview_page_metrics(
            MagicMock(),
            project,  # type: ignore[arg-type]
            on_jump=jumps.append,
        )

    assert jumps == ["ink-2"]
    assert chart.call_args.kwargs["chart_type"] == "bar"
    assert chart.call_args.kwargs["y"] == "ink_coverage_pct"
    # Rows passed to the chart keep real page ids in page order.
    ink_rows = chart.call_args.args[0]
    assert [r["page_id"] for r in ink_rows] == ["ink-1", "ink-2"]
    assert [r["order"] for r in ink_rows] == [1, 2]
