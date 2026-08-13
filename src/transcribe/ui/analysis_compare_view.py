"""Streamlit helpers: period selector + this-notebook vs average charts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.domain.dates import ApproximateDate
from transcribe.services.analysis_compare import (
    COMPARABLE_SPECS,
    ComparePeriod,
    compare_rows,
    extract_module_metrics,
    load_module_baseline,
)


def _years_from_projects(projects_dir: Path | None) -> list[int]:
    if projects_dir is None or not Path(projects_dir).exists():
        return []
    years: set[int] = set()
    from transcribe.persistence.atomic import read_json
    from transcribe.services.archive import discover_project_roots

    for root in discover_project_roots(Path(projects_dir)):
        try:
            data = read_json(root / "project.json")
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        for key in ("date_start", "date_end"):
            try:
                d = ApproximateDate.from_dict(data.get(key))
            except (ValueError, TypeError):
                d = None
            if d is not None:
                years.add(d.year)
    return sorted(years, reverse=True)


def render_compare_period_controls(
    *,
    key_prefix: str,
    projects_dir: Path | None,
) -> ComparePeriod:
    """Archive-style period picker for Analyse comparison baselines."""
    years = _years_from_projects(projects_dir)
    options = ["Entire corpus"]
    if years:
        options.append("Year")
    options.append("Date range")
    choice = st.selectbox(
        "Compare with",
        options,
        key=f"{key_prefix}_compare_period",
        help=(
            "Bars compare this notebook to the average of other notebooks with "
            "published results. Year / date range use each notebook’s diary "
            "date span (same idea as Archive period filters)."
        ),
    )
    if choice == "Year" and years:
        year = st.selectbox("Year", years, key=f"{key_prefix}_compare_year")
        return ComparePeriod(kind="year", year=int(year), include_undated=False)
    if choice == "Date range":
        today = date.today()
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input(
                "From",
                value=date(today.year - 1, 1, 1),
                key=f"{key_prefix}_compare_from",
            )
        with c2:
            end = st.date_input(
                "To",
                value=today,
                key=f"{key_prefix}_compare_to",
            )
        return ComparePeriod(
            kind="range",
            range_start=ApproximateDate(year=start.year, month=start.month, day=start.day),
            range_end=ApproximateDate(year=end.year, month=end.month, day=end.day),
            include_undated=False,
        )
    return ComparePeriod(kind="all", include_undated=True)


def render_module_compare_charts(
    module_id: str,
    payload: dict[str, Any],
    *,
    projects_dir: Path | None,
    period: ComparePeriod,
    exclude_project_id: str | None,
    chart_key: str,
) -> None:
    """TX-style categorical bars: this notebook vs corpus/period average."""
    if projects_dir is None:
        return
    if module_id not in COMPARABLE_SPECS:
        return
    current = extract_module_metrics(module_id, payload)
    if not current:
        return
    baseline = load_module_baseline(
        Path(projects_dir),
        module_id,
        period=period,
        exclude_project_id=exclude_project_id,
    )
    rows = compare_rows(current, baseline)
    if not rows:
        st.caption(
            "No peer notebooks with published results in this period yet — "
            "showing this notebook only."
        )
        # Still show a single-series chart so the metric is visual.
        labels = [r for r in COMPARABLE_SPECS[module_id] if r[0] in current]
        if labels:
            st.bar_chart(
                {
                    "metric": [lab for _k, lab, _p in labels],
                    "This notebook": [current[k] for k, _lab, _p in labels],
                },
                x="metric",
                y="This notebook",
            )
        return

    st.caption(f"Compared with {baseline.baseline_label} · peers exclude this notebook.")
    # One grouped chart: categories = metric labels; two series.
    st.bar_chart(
        {
            "metric": [r["label"] for r in rows],
            "This notebook": [r["this"] for r in rows],
            baseline.baseline_label: [r["average"] for r in rows],
        },
        x="metric",
        y=["This notebook", baseline.baseline_label],
    )
    # Compact delta strip
    deltas = []
    for r in rows:
        sign = "+" if r["delta"] >= 0 else ""
        deltas.append(f"{r['label']} {sign}{r['delta']:.3g}")
    if deltas:
        st.caption("Δ vs average · " + " · ".join(deltas[:6]))
    _ = chart_key  # reserved for future Altair keys / session uniqueness
