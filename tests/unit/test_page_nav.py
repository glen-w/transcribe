"""Pure helpers for page-viewer navigation contexts."""

from __future__ import annotations

from transcribe.ui.page_viewer import _normalize_entries


def test_normalize_entries_from_page_ids():
    entries = _normalize_entries(
        page_ids=["a", "b"],
        project_root="/tmp/nb",
        view_entries=None,
    )
    assert entries == [
        {"page_id": "a", "project_root": "/tmp/nb"},
        {"page_id": "b", "project_root": "/tmp/nb"},
    ]


def test_normalize_entries_cross_notebook():
    entries = _normalize_entries(
        page_ids=None,
        project_root=None,
        view_entries=[
            {"page_id": "p1", "project_root": "/a"},
            {"page_id": "p2", "project_root": "/b"},
        ],
    )
    assert entries[0]["project_root"] == "/a"
    assert entries[1]["project_root"] == "/b"
