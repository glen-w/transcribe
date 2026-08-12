"""Unit tests for clickable activity-chart selection helpers."""

from __future__ import annotations

from types import SimpleNamespace

from transcribe.ui.activity_selection import selected_bin_label


def test_selected_bin_label_from_altair_event() -> None:
    event = SimpleNamespace(
        selection={"bin_select": [{"label": "2024-03", "pages": 4}]}
    )
    assert selected_bin_label(event) == "2024-03"


def test_selected_bin_label_empty_or_missing() -> None:
    assert selected_bin_label(None) is None
    assert selected_bin_label(SimpleNamespace(selection={})) is None
    assert selected_bin_label(SimpleNamespace(selection={"bin_select": {}})) is None
    assert selected_bin_label({"selection": {"bin_select": []}}) is None
