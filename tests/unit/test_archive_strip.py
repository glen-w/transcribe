"""Archive notebook strip paging helpers."""

from __future__ import annotations

from transcribe.ui.archive_views import (
    _archive_notebook_page_size,
    _archive_notebook_show_count,
)


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
