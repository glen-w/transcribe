"""Unit tests for the global analysis progress chip helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.ui.components import global_analysis_progress as gap
from transcribe.ui.targets import TARGET_BATCH, TARGET_THIS


@pytest.mark.unit
def test_is_analysis_operation_active_single_and_batch() -> None:
    assert gap.is_analysis_operation_active({}) is False
    assert gap.is_analysis_operation_active({"analysis_run_in_progress": True}) is True
    assert (
        gap.is_analysis_operation_active(
            {"_batch_analysis_was_running": True}
        )
        is True
    )
    assert (
        gap.is_analysis_operation_active(
            {"_batch_analysis_was_running": False}
        )
        is False
    )
    assert (
        gap.is_analysis_operation_active({}, batch_running=True) is True
    )
    assert (
        gap.is_analysis_operation_active(
            {"_batch_analysis_was_running": True}, batch_running=False
        )
        is False
    )


@pytest.mark.unit
def test_resolve_and_sync_active_target() -> None:
    state: dict = {
        "analysis_run_in_progress": True,
        "run_analysis_pending_launch": {"target_type": TARGET_THIS},
        "analyse_target": TARGET_BATCH,
    }
    assert gap.resolve_active_analysis_target(state) == TARGET_THIS
    assert gap.sync_analyse_target_to_active_operation(state) == TARGET_THIS
    assert state["analyse_target"] == TARGET_THIS

    batch_state: dict = {
        "_batch_analysis_was_running": True,
        "analyse_target": TARGET_THIS,
    }
    assert gap.resolve_active_analysis_target(batch_state) == TARGET_BATCH
    gap.sync_analyse_target_to_active_operation(batch_state)
    assert batch_state["analyse_target"] == TARGET_BATCH


@pytest.mark.unit
def test_snapshot_summary_prefers_item_and_counts() -> None:
    title, pct, detail = gap._snapshot_summary(
        {
            "phase": "running_pipeline",
            "status": "running",
            "pct": 40.0,
            "current_item": "notebook-a",
            "current_module": "stats",
            "completed": 2,
            "skipped": 0,
            "failed": 0,
            "total": 5,
        }
    )
    assert title == "Running…"
    assert pct == 40.0
    assert "notebook-a" in detail
    assert "stats" in detail
    assert "2/5" in detail


@pytest.mark.unit
def test_app_shell_mounts_global_progress() -> None:
    from transcribe.ui import app as app_mod
    from transcribe.ui import shell as shell_mod

    app_source = Path(app_mod.__file__).read_text(encoding="utf-8")
    shell_source = Path(shell_mod.__file__).read_text(encoding="utf-8")
    assert "render_global_analysis_progress" in app_source
    assert "tx-global-run-progress" in shell_source
    assert "z-index: 1100" in shell_source


@pytest.mark.unit
def test_analyse_workspace_resumes_this_notebook_before_batch() -> None:
    """In-progress this-notebook runs must win over Target=Batch."""
    from transcribe.ui import app as app_mod

    source = Path(app_mod.__file__).read_text(encoding="utf-8")
    sync_idx = source.index("sync_analyse_target_to_active_operation")
    this_idx = source.index("Ongoing this-notebook run takes priority")
    batch_idx = source.index("render_batch_analysis_progress(batch_coord, runtime)")
    assert sync_idx < this_idx < batch_idx
    assert "disabled=operation_active" in source
    assert '"target_type": TARGET_THIS' in Path(
        "src/transcribe/ui/run_analysis.py"
    ).read_text(encoding="utf-8")
    assert '"project_root": str(projects.paths.root)' in Path(
        "src/transcribe/ui/run_analysis.py"
    ).read_text(encoding="utf-8")
