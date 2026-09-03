"""Library cover-grid paging helpers and view ids."""

from __future__ import annotations

from transcribe.ui.archive_views import (
    ARCHIVE_COVERS_COLS_KEY,
    LIBRARY_VIEW_ACTIVITY,
    LIBRARY_VIEW_COVERS,
    LIBRARY_VIEW_LABELS,
    LIBRARY_VIEW_SESSION_KEY,
    _DEFAULT_ARCHIVE_COVERS_COLS,
    _MAX_ARCHIVE_COVERS_COLS,
    _MIN_ARCHIVE_COVERS_COLS,
    _archive_covers_cols,
    _archive_notebook_page_size,
    _archive_notebook_show_count,
)


def test_library_default_view_is_covers() -> None:
    assert LIBRARY_VIEW_COVERS == "covers"
    assert LIBRARY_VIEW_ACTIVITY == "activity"
    assert LIBRARY_VIEW_SESSION_KEY == "library_view"
    assert LIBRARY_VIEW_LABELS[LIBRARY_VIEW_COVERS] == "Covers"
    assert LIBRARY_VIEW_LABELS[LIBRARY_VIEW_ACTIVITY] == "Activity"
    assert tuple(LIBRARY_VIEW_LABELS)[0] == LIBRARY_VIEW_COVERS


def test_archive_notebook_page_size_zero_means_all() -> None:
    assert _archive_notebook_page_size(configured_initial=0, total=42) == 42


def test_archive_notebook_page_size_positive_uses_configured() -> None:
    assert _archive_notebook_page_size(configured_initial=12, total=42) == 12


def test_archive_notebook_show_count_defaults_to_page_size() -> None:
    assert (
        _archive_notebook_show_count(
            configured_initial=12,
            total=42,
            session_show_n=None,
        )
        == 12
    )
    assert (
        _archive_notebook_show_count(
            configured_initial=0,
            total=42,
            session_show_n=None,
        )
        == 42
    )


def test_archive_notebook_show_count_honors_session_and_caps_total() -> None:
    assert (
        _archive_notebook_show_count(
            configured_initial=12,
            total=42,
            session_show_n=24,
        )
        == 24
    )
    assert (
        _archive_notebook_show_count(
            configured_initial=12,
            total=42,
            session_show_n=99,
        )
        == 42
    )


def test_archive_covers_zoom_constants() -> None:
    assert _MIN_ARCHIVE_COVERS_COLS < _DEFAULT_ARCHIVE_COVERS_COLS < _MAX_ARCHIVE_COVERS_COLS
    assert ARCHIVE_COVERS_COLS_KEY == "archive_covers_cols"


def test_archive_covers_cols_defaults_and_clamps(monkeypatch) -> None:
    from transcribe.ui import archive_views as av

    state: dict = {}
    monkeypatch.setattr(av.st, "session_state", state)

    assert _archive_covers_cols() == _DEFAULT_ARCHIVE_COVERS_COLS

    state[ARCHIVE_COVERS_COLS_KEY] = _MAX_ARCHIVE_COVERS_COLS + 2
    assert _archive_covers_cols() == _MAX_ARCHIVE_COVERS_COLS

    state[ARCHIVE_COVERS_COLS_KEY] = _MIN_ARCHIVE_COVERS_COLS - 1
    assert _archive_covers_cols() == _MIN_ARCHIVE_COVERS_COLS

    state[ARCHIVE_COVERS_COLS_KEY] = "bad"
    assert _archive_covers_cols() == _DEFAULT_ARCHIVE_COVERS_COLS
