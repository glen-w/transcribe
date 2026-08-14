"""Streamlit helpers for page ink / blankness metrics."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from transcribe.domain.models import Project
from transcribe.page_metrics.models import PageMetricsRow, PublishedPageMetrics
from transcribe.page_metrics.service import PageMetricsService
from transcribe.ports import SystemClock
from transcribe.services.project import ProjectService

_HUE_SWATCH: dict[str, str] = {
    "black": "#222222",
    "blue": "#2f5fbf",
    "red": "#c43c3c",
    "brown": "#8b5a2b",
    "green": "#2f8f4e",
    "other": "#7a7a7a",
    "mixed": "#9a7a9a",
    "none": "#d0d0d0",
}


def ensure_page_metrics(
    projects: ProjectService,
    project: Project,
    *,
    force: bool = False,
) -> PublishedPageMetrics | None:
    """Lazy-compute published metrics; never raise into the UI shell."""
    try:
        svc = PageMetricsService(projects, clock=SystemClock())
        return svc.ensure_fresh(project, force=force)
    except Exception:  # noqa: BLE001 — optional surface
        return None


def render_page_metrics_strip(row: PageMetricsRow | None) -> None:
    """Compact coverage / blankness / hue line under the page image."""
    if row is None:
        st.caption("Page used / ink: not available for this render.")
        return
    swatch = _HUE_SWATCH.get(row.ink_hue, "#888888")
    hue_label = row.ink_hue.replace("_", " ")
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:0.85rem;align-items:center;'
        f'font-size:0.875rem;opacity:0.9;margin:0.35rem 0 0.6rem 0;">'
        f"<span><strong>Page used:</strong> {row.ink_coverage_pct:.1f}%</span>"
        f"<span><strong>Blank:</strong> {row.blankness_pct:.1f}%</span>"
        f'<span style="display:inline-flex;align-items:center;gap:0.35rem;">'
        f"<strong>Ink:</strong> {hue_label}"
        f'<span style="display:inline-block;width:0.75rem;height:0.75rem;'
        f"border-radius:2px;background:{swatch};"
        f'border:1px solid rgba(0,0,0,0.25);" title="ink hue"></span>'
        f"</span>"
        f'<span style="opacity:0.75;">Paper: {row.paper_tone}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_overview_page_metrics(
    projects: ProjectService,
    project: Project,
    *,
    on_jump: Callable[[str], None] | None = None,
) -> None:
    """Notebook rollup block for Analyse → Overview."""
    st.markdown("#### Page ink & blankness")
    st.caption(
        "Visual metrics from active page renders (Pillow). "
        "Independent of text Analyse modules — refreshes when page images change."
    )
    published = ensure_page_metrics(projects, project)
    cols = st.columns([1, 1, 1, 1.2])
    if cols[3].button("Refresh page metrics", key="page_metrics_refresh"):
        published = ensure_page_metrics(projects, project, force=True)
        st.rerun()

    if published is None:
        st.info("Page metrics unavailable.")
        return
    if published.outcome == "insufficient_data" or not published.pages:
        st.info("No measurable page renders yet.")
        return

    rollup = published.rollup
    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Mean page used",
        (
            f"{rollup.mean_ink_coverage_pct:.1f}%"
            if rollup.mean_ink_coverage_pct is not None
            else "—"
        ),
    )
    m2.metric(
        "Median page used",
        (
            f"{rollup.median_ink_coverage_pct:.1f}%"
            if rollup.median_ink_coverage_pct is not None
            else "—"
        ),
    )
    m3.metric(
        "Mean blank",
        (f"{rollup.mean_blankness_pct:.1f}%" if rollup.mean_blankness_pct is not None else "—"),
    )

    from transcribe.ui.page_series_charts import maybe_jump, render_clickable_page_series

    ink_rows = [
        {
            "order": i + 1,
            "page_id": p.page_id,
            "ink_coverage_pct": p.ink_coverage_pct,
        }
        for i, p in enumerate(published.pages)
        if p.page_id and p.ink_coverage_pct is not None
    ]
    st.caption("Ink coverage by page order — click a bar to open that page")
    maybe_jump(
        render_clickable_page_series(
            ink_rows,
            y="ink_coverage_pct",
            key=f"overview_ink_{project.id}",
            chart_type="bar",
        ),
        on_jump,
    )

    if rollup.hue_counts:
        labels = list(rollup.hue_counts.keys())
        counts = [rollup.hue_counts[k] for k in labels]
        st.caption("Dominant ink hue (pages)")
        st.bar_chart({"hue": labels, "pages": counts}, x="hue", y="pages")
