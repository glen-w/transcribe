"""Unit tests for clickable page-series chart selection helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from transcribe.ui.analysis_display_helpers import (
    epistemic_page_series_rows,
    topic_shift_series_rows,
    unit_series_rows,
)
from transcribe.ui.page_series_selection import page_id_from_unit_id, selected_page_id


def test_selected_page_id_from_altair_event() -> None:
    event = SimpleNamespace(
        selection={"page_select": [{"page_id": "p-3", "order": 3, "compound": 0.2}]}
    )
    assert selected_page_id(event) == "p-3"


def test_selected_page_id_empty_or_missing() -> None:
    assert selected_page_id(None) is None
    assert selected_page_id(SimpleNamespace(selection={})) is None
    assert selected_page_id(SimpleNamespace(selection={"page_select": {}})) is None
    assert selected_page_id({"selection": {"page_select": []}}) is None


def test_page_id_from_unit_id() -> None:
    assert page_id_from_unit_id("abc") == "abc"
    assert page_id_from_unit_id("abc/span:10-40") == "abc"
    assert page_id_from_unit_id("") is None
    assert page_id_from_unit_id(None) is None


def test_unit_series_rows_keeps_page_id() -> None:
    rows = unit_series_rows(
        [
            {"order": 1, "unit_id": "p1", "compound": 0.1},
            {"order": 2, "compound": 0.2},  # no id → skipped
            {"order": 3, "unit_id": "p3/span:0-8", "compound": -0.4},
            {"order": 4, "page_id": "explicit", "unit_id": "ignored", "compound": 0.0},
        ],
        "compound",
    )
    assert rows == [
        {"order": 1, "page_id": "p1", "compound": 0.1},
        {"order": 3, "page_id": "p3", "compound": -0.4},
        {"order": 4, "page_id": "explicit", "compound": 0.0},
    ]


def test_topic_shift_and_epistemic_rows() -> None:
    shifts = topic_shift_series_rows(
        [
            {
                "from_unit_id": "a/span:1-2",
                "from_order": 1,
                "similarity": 0.75,
            },
            {"from_order": 2, "similarity": 0.1},  # no unit → skipped
        ]
    )
    assert shifts == [{"order": 1, "page_id": "a", "similarity": 0.75}]

    ep = epistemic_page_series_rows(
        [
            {
                "order": 1,
                "unit_id": "p1",
                "category_counts": {
                    "epistemic_hedge": 2,
                    "approximator": 1,
                    "certainty_booster": 4,
                },
            }
        ]
    )
    assert ep == [{"order": 1, "page_id": "p1", "hedges": 3, "boosters": 4}]


def test_shared_jump_helper_targets_reading_not_review() -> None:
    jumps = Path("src/transcribe/ui/view_jumps.py").read_text(encoding="utf-8")
    views = Path("src/transcribe/ui/notebook_views.py").read_text(encoding="utf-8")
    detect = Path("src/transcribe/ui/run_detection.py").read_text(encoding="utf-8")
    assert 'st.session_state["ui_mode"] = "Reading"' in jumps
    assert 'st.session_state["ui_mode"] = "Review"' not in jumps
    assert "def jump_to_reading" in jumps
    assert "def jump_person_occurrence" in jumps
    assert "jump_to_reading" in views
    assert "jump_person_occurrence" in views
    assert "rerun=False" in jumps
    assert 'return_mode="Review"' not in views
    assert 'return_mode="Detect"' in detect
    assert 'st.session_state["ui_mode"] = "Detect"' in detect
