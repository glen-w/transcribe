"""Sidebar mode normalisation and notebook-workflow gating."""

from __future__ import annotations

from pathlib import Path

from transcribe.ui.navigation import (
    is_open_notebook_workflow,
    is_view_mode,
    is_workflow_mode,
    normalize_ui_mode,
)
from transcribe.ui.shell import (
    is_open_notebook_workflow as shell_is_open_notebook_workflow,
    is_workflow_mode as shell_is_workflow_mode,
    normalize_ui_mode as shell_normalize_ui_mode,
)


def test_new_notebook_is_first_workflow_mode() -> None:
    assert normalize_ui_mode("New notebook") == "New notebook"
    assert normalize_ui_mode("Create") == "New notebook"
    assert is_workflow_mode("New notebook")
    assert not is_open_notebook_workflow("New notebook")
    assert not is_open_notebook_workflow("Import")
    assert not is_open_notebook_workflow("Transcribe")
    assert is_open_notebook_workflow("Review")
    assert not is_open_notebook_workflow("Reading")
    assert not is_open_notebook_workflow("Analyse")


def test_reading_is_view_mode() -> None:
    assert normalize_ui_mode("Reading") == "Reading"
    assert is_view_mode("Reading")
    assert not is_workflow_mode("Reading")


def test_library_alias_and_home_not_archive() -> None:
    assert normalize_ui_mode("View") == "Library"
    assert normalize_ui_mode("Library") == "Library"
    assert normalize_ui_mode("Home") == "Home"


def test_legacy_workflow_alias() -> None:
    assert normalize_ui_mode("Workflow") == "Import"


def test_inbox_aliases_to_import() -> None:
    assert normalize_ui_mode("Inbox") == "Import"


def test_shell_reexports_navigation_helpers() -> None:
    assert shell_normalize_ui_mode("Published results") == "Overview"
    assert shell_is_workflow_mode("Analyse")
    assert shell_is_open_notebook_workflow("Export")


def test_picker_does_not_rewrite_ui_mode() -> None:
    shell = Path("src/transcribe/ui/shell.py").read_text(encoding="utf-8")
    assert "picker changes never rewrite" in shell
    assert "disabled = (not enabled) and current != mode" in shell
    start = shell.index("if _canonical_root(selected) != _canonical_root(previous):")
    chunk = shell[start : start + 400]
    assert "set_ui_mode" not in chunk
    assert '["ui_mode"]' not in chunk
    assert "def _canonical_root" in shell


def test_first_visit_home_is_app_not_normalize() -> None:
    app = Path("src/transcribe/ui/app.py").read_text(encoding="utf-8")
    assert 'first_visit = "ui_mode" not in st.session_state' in app
    assert 'mode = "Home"' in app
    assert normalize_ui_mode("nope") == "Archive"
