"""Streamlit progress panel — TX-style snapshot renderer for Analyse runs.

The panel reads one snapshot dict and renders status, current module, bar,
latest event, and a short log tail. No state is inferred from logs.
"""

from __future__ import annotations

import datetime
from typing import Any, MutableMapping, Optional, TypedDict

import streamlit as st

SNAPSHOT_KEY = "run_analysis_progress_snapshot"
PANEL_LOG_LINES = 8


class ProgressSnapshot(TypedDict, total=False):
    status: str  # running | completed | failed
    phase: str
    current_module: str
    current_item: str
    completed: int
    skipped: int
    failed: int
    total: int
    pct: float
    latest_event: str
    recent_logs: list[str]
    error: str | None
    detail_completed: int
    detail_failed: int
    detail_skipped: int
    detail_total: int
    detail_unit: str
    detail_current: str


def make_initial_snapshot(total: int) -> ProgressSnapshot:
    return ProgressSnapshot(
        status="running",
        phase="running_pipeline",
        current_module="",
        completed=0,
        skipped=0,
        failed=0,
        total=total,
        pct=0.0,
        latest_event="Starting…",
        recent_logs=[],
        error=None,
    )


def render_progress_panel(
    snapshot: ProgressSnapshot,
    *,
    unit_label: str = "modules",
    current_label: str = "Current module",
) -> None:
    phase = snapshot.get("phase", "running")
    status = snapshot.get("status", "running")
    current_module = snapshot.get("current_module", "")
    current_item = snapshot.get("current_item", "")
    completed = int(snapshot.get("completed", 0) or 0)
    skipped = int(snapshot.get("skipped", 0) or 0)
    failed = int(snapshot.get("failed", 0) or 0)
    total = int(snapshot.get("total", 0) or 0)
    pct = float(snapshot.get("pct", 0.0) or 0.0)
    latest_event = snapshot.get("latest_event", "")
    recent_logs = list(snapshot.get("recent_logs") or [])
    error = snapshot.get("error")

    done = completed + skipped + failed
    phase_labels = {
        "running_pipeline": "Running pipeline…",
        "finalizing": "Finalizing…",
        "completed": "Completed",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "partial": "Completed with gaps",
        "rank_composite": "Ranking and combining…",
        "vision": "Running vision OCR…",
    }
    phase_label = phase_labels.get(str(phase), str(phase).replace("_", " ").title())

    if status == "completed":
        st.success(f"**{phase_label}**")
    elif status == "failed":
        st.error(f"**{phase_label}**")
        if error:
            st.error(error)
    else:
        st.info(f"**{phase_label}**")

    if current_item:
        st.markdown(f"Current: `{current_item}`")

    detail_current = str(snapshot.get("detail_current") or "")
    if detail_current:
        st.markdown(f"Current page: `{detail_current}`")

    if current_module:
        prefix = (
            f"Last {current_label.lower().replace('current ', '')}:"
            if status in ("completed", "failed")
            else f"{current_label}:"
        )
        st.markdown(f"{prefix} `{current_module}`")

    if total > 0:
        bar_label = f"{done} / {total} {unit_label}"
        if skipped:
            bar_label += f"  ·  {skipped} skipped"
        if failed:
            bar_label += f"  ·  {failed} failed"
        st.progress(min(pct / 100.0, 1.0), text=bar_label)
    else:
        st.progress(0.0)

    detail_total = int(snapshot.get("detail_total", 0) or 0)
    if detail_total > 0:
        detail_completed = int(snapshot.get("detail_completed", 0) or 0)
        detail_failed = int(snapshot.get("detail_failed", 0) or 0)
        detail_skipped = int(snapshot.get("detail_skipped", 0) or 0)
        detail_unit = str(snapshot.get("detail_unit") or "pages")
        detail_done = detail_completed + detail_failed
        detail_label = f"{detail_done} / {detail_total} {detail_unit}"
        if detail_skipped:
            detail_label += f"  ·  {detail_skipped} skipped"
        st.progress(min(detail_done / detail_total, 1.0), text=detail_label)

    if latest_event:
        st.caption(latest_event)

    if recent_logs:
        with st.expander("Recent logs", expanded=False):
            st.text("\n".join(recent_logs[-PANEL_LOG_LINES:]))


class StreamlitProgressCallback:
    """Mutate the Analyse snapshot and optionally re-paint into ``render_slot``."""

    def __init__(
        self,
        snapshot_key: str = SNAPSHOT_KEY,
        *,
        render_slot: Any | None = None,
        unit_label: str = "modules",
        current_label: str = "Current module",
    ) -> None:
        self._snapshot_key = snapshot_key
        self._render_slot = render_slot
        self._unit_label = unit_label
        self._current_label = current_label

    def _snap(self) -> Optional[MutableMapping[str, Any]]:
        return st.session_state.get(self._snapshot_key)

    def refresh_panel(self) -> None:
        if self._render_slot is None:
            return
        snap = self._snap()
        if snap is None:
            return
        with self._render_slot.container():
            render_progress_panel(
                snap,  # type: ignore[arg-type]
                unit_label=self._unit_label,
                current_label=self._current_label,
            )

    def _append_log(self, message: str) -> None:
        snap = self._snap()
        if snap is None:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        logs = list(snap.get("recent_logs") or [])
        logs.append(f"[{ts}] {message}")
        snap["recent_logs"] = logs[-100:]

    def module_started(self, module_id: str, *, index: int, total: int) -> None:
        snap = self._snap()
        if snap is None:
            return
        snap["status"] = "running"
        snap["phase"] = "running_pipeline"
        snap["current_module"] = module_id
        snap["total"] = total
        snap["latest_event"] = f"Running {module_id} ({index}/{total})…"
        self._append_log(f"module_started {module_id}")
        self.refresh_panel()

    def module_finished(
        self,
        module_id: str,
        *,
        outcome: str,
        completed: int,
        failed: int,
        skipped: int,
        total: int,
    ) -> None:
        snap = self._snap()
        if snap is None:
            return
        done = completed + failed + skipped
        pct = (done / total * 100.0) if total else 0.0
        snap["completed"] = completed
        snap["failed"] = failed
        snap["skipped"] = skipped
        snap["total"] = total
        snap["pct"] = pct
        snap["current_module"] = module_id
        snap["latest_event"] = f"{module_id}: {outcome} ({done}/{total})"
        self._append_log(f"module_{outcome} {module_id}")
        self.refresh_panel()

    def run_completed(self) -> None:
        snap = self._snap()
        if snap is None:
            return
        snap["status"] = "completed"
        snap["phase"] = "completed"
        snap["pct"] = 100.0 if int(snap.get("total", 0) or 0) else float(snap.get("pct", 0) or 0)
        snap["latest_event"] = "Analysis completed"
        self._append_log("run_completed")
        self.refresh_panel()

    def run_failed(self, message: str) -> None:
        snap = self._snap()
        if snap is None:
            return
        snap["status"] = "failed"
        snap["phase"] = "failed"
        snap["error"] = message
        snap["latest_event"] = message
        self._append_log(f"run_failed {message}")
        self.refresh_panel()
