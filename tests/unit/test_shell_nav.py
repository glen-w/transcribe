"""Sidebar mode normalisation and notebook-workflow gating."""

from __future__ import annotations

from transcribe.ui.shell import (
    is_open_notebook_workflow,
    is_workflow_mode,
    normalize_ui_mode,
)


def test_new_notebook_is_first_workflow_mode() -> None:
    assert normalize_ui_mode("New notebook") == "New notebook"
    assert normalize_ui_mode("Create") == "New notebook"
    assert is_workflow_mode("New notebook")
    assert not is_open_notebook_workflow("New notebook")
    assert is_open_notebook_workflow("Import")


def test_legacy_workflow_alias() -> None:
    assert normalize_ui_mode("Workflow") == "Import"
