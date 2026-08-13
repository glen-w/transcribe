"""Unit tests for corpus/period analysis comparison baselines."""

from __future__ import annotations

import json
from pathlib import Path

from transcribe.domain.dates import ApproximateDate
from transcribe.services.analysis_compare import (
    ComparePeriod,
    compare_rows,
    extract_foundations_display,
    extract_module_metrics,
    load_module_baseline,
    notebook_overlaps_period,
    payload_get,
)


def test_payload_get_nested():
    assert payload_get({"document": {"ttr": 0.4}}, "document.ttr") == 0.4
    assert payload_get({"document": {}}, "document.ttr") is None
    assert payload_get({}, "document.ttr") is None


def test_extract_lexical_and_foundations_display():
    payload = {
        "document": {
            "ttr": 0.42,
            "mtld": 55.5,
            "hapax_rate": 0.31,
            "token_count": 120,
        }
    }
    metrics = extract_module_metrics("lexical_diversity", payload)
    assert metrics["ttr"] == 0.42
    assert metrics["mtld"] == 55.5
    bits = extract_foundations_display(payload, "lexical_diversity")
    labels = [b[0] for b in bits]
    assert "Tokens" in labels
    assert "TTR" in labels


def test_extract_stats_and_understandability():
    stats = extract_module_metrics(
        "stats",
        {"unit_count": 3, "total_token_count": 90, "total_char_count": 400},
    )
    assert stats == {
        "unit_count": 3.0,
        "total_token_count": 90.0,
        "total_char_count": 400.0,
    }
    und = extract_module_metrics(
        "understandability",
        {
            "document": {
                "flesch_reading_ease": 65.2,
                "avg_sentence_length": 12.5,
                "gunning_fog_index": 8.1,
                "lexical_density": 0.55,
            }
        },
    )
    assert und["flesch_reading_ease"] == 65.2
    # Old wrong top-level keys must not be required
    assert extract_foundations_display(
        {"document": {"flesch_reading_ease": 70.0}}, "understandability"
    )


def test_notebook_overlaps_period_year_and_range():
    start = ApproximateDate(year=2020, month=3, day=1)
    end = ApproximateDate(year=2020, month=6, day=1)
    assert notebook_overlaps_period(
        start, end, ComparePeriod(kind="year", year=2020, include_undated=False)
    )
    assert not notebook_overlaps_period(
        start, end, ComparePeriod(kind="year", year=2019, include_undated=False)
    )
    assert notebook_overlaps_period(
        start,
        end,
        ComparePeriod(
            kind="range",
            range_start=ApproximateDate(year=2020, month=1, day=1),
            range_end=ApproximateDate(year=2020, month=12, day=31),
            include_undated=False,
        ),
    )
    assert notebook_overlaps_period(
        None, None, ComparePeriod(kind="all", include_undated=True)
    )
    assert not notebook_overlaps_period(
        None, None, ComparePeriod(kind="year", year=2020, include_undated=False)
    )


def _write_project(
    root: Path,
    *,
    project_id: str,
    title: str,
    date_start: dict | None,
    date_end: dict | None,
    module_id: str,
    payload: dict,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.json").write_text(
        json.dumps(
            {
                "format": "transcribe.project",
                "schema_version": 1,
                "id": project_id,
                "title": title,
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2020-01-01T00:00:00Z",
                "timezone": "UTC",
                "pages": [],
                "sources": [],
                "date_start": date_start,
                "date_end": date_end,
            }
        ),
        encoding="utf-8",
    )
    pub_dir = root / "analysis" / module_id
    pub_dir.mkdir(parents=True, exist_ok=True)
    (pub_dir / "published.json").write_text(
        json.dumps(
            {
                "format": "transcribe.analysis-result",
                "schema_version": 1,
                "project_id": project_id,
                "module_id": module_id,
                "module_version": "1.0.0",
                "cache_identity": "x",
                "content_fingerprint": "y",
                "attempt_state": "succeeded",
                "outcome": "success",
                "capability": "ok",
                "provenance": {},
                "warnings": [],
                "parents": [],
                "config_fingerprint": "z",
                "payload": payload,
                "published": True,
            }
        ),
        encoding="utf-8",
    )


def test_load_module_baseline_corpus_and_year(tmp_path: Path):
    projects = tmp_path / "projects"
    _write_project(
        projects / "a",
        project_id="proj-a",
        title="A",
        date_start={"y": 2020, "m": 1, "d": 1},
        date_end={"y": 2020, "m": 6, "d": 1},
        module_id="lexical_diversity",
        payload={"document": {"ttr": 0.40, "mtld": 40.0, "hapax_rate": 0.2}},
    )
    _write_project(
        projects / "b",
        project_id="proj-b",
        title="B",
        date_start={"y": 2021, "m": 1, "d": 1},
        date_end={"y": 2021, "m": 6, "d": 1},
        module_id="lexical_diversity",
        payload={"document": {"ttr": 0.60, "mtld": 60.0, "hapax_rate": 0.4}},
    )
    _write_project(
        projects / "current",
        project_id="proj-current",
        title="Current",
        date_start={"y": 2020, "m": 3, "d": 1},
        date_end={"y": 2020, "m": 4, "d": 1},
        module_id="lexical_diversity",
        payload={"document": {"ttr": 0.50, "mtld": 50.0, "hapax_rate": 0.3}},
    )

    all_base = load_module_baseline(
        projects,
        "lexical_diversity",
        period=ComparePeriod(kind="all"),
        exclude_project_id="proj-current",
    )
    assert all_base.metrics["ttr"].n_notebooks == 2
    assert abs(all_base.metrics["ttr"].average - 0.5) < 1e-9

    year_base = load_module_baseline(
        projects,
        "lexical_diversity",
        period=ComparePeriod(kind="year", year=2020, include_undated=False),
        exclude_project_id="proj-current",
    )
    assert year_base.metrics["ttr"].n_notebooks == 1
    assert year_base.metrics["ttr"].average == 0.40
    assert "2020" in year_base.baseline_label

    current = extract_module_metrics(
        "lexical_diversity",
        {"document": {"ttr": 0.50, "mtld": 50.0, "hapax_rate": 0.3}},
    )
    rows = compare_rows(current, year_base)
    assert rows
    ttr_row = next(r for r in rows if r["key"] == "ttr")
    assert abs(ttr_row["delta"] - 0.10) < 1e-9
