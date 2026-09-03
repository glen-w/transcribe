"""Always-on-top analysis progress chip (top-right).

Shows while a this-notebook or batch Analyse worker is active, including when
the user has navigated away from Workflow → Analyse. Clicking View returns
them to the live progress panel on that page.
"""

from __future__ import annotations

import html
from typing import Any, Callable, Literal, Mapping, MutableMapping

import streamlit as st

from transcribe.ui.components.progress_panel import SNAPSHOT_KEY
from transcribe.ui.targets import ANALYSE_TARGET_KEY, TARGET_BATCH, TARGET_THIS

_PENDING_LAUNCH_KEY = "run_analysis_pending_launch"
_IN_PROGRESS_KEY = "analysis_run_in_progress"
_BATCH_WAS_RUNNING_KEY = "_batch_analysis_was_running"
_BATCH_SNAPSHOT_KEY = "batch_analysis_progress_snapshot"
_UI_MODE_KEY = "ui_mode"

AnalysisTarget = Literal["This notebook", "Batch"]

_PHASE_LABELS: dict[str, str] = {
    "validating": "Checking inputs…",
    "running_pipeline": "Running…",
    "finalizing": "Finalizing…",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "partial": "Completed with gaps",
}


def is_analysis_operation_active(
    session_state: Mapping[str, Any] | MutableMapping[str, Any] | None = None,
    *,
    batch_running: bool | None = None,
) -> bool:
    """True while a this-notebook or batch Analyse launch is in flight."""
    state = session_state if session_state is not None else st.session_state
    if state.get(_IN_PROGRESS_KEY):
        return True
    if batch_running is True:
        return True
    if batch_running is False:
        return False
    return bool(state.get(_BATCH_WAS_RUNNING_KEY))


def resolve_active_analysis_target(
    session_state: Mapping[str, Any] | MutableMapping[str, Any] | None = None,
    *,
    batch_running: bool | None = None,
) -> AnalysisTarget | None:
    """Target mode for the active operation, or None when idle."""
    state = session_state if session_state is not None else st.session_state
    if state.get(_IN_PROGRESS_KEY):
        pending = state.get(_PENDING_LAUNCH_KEY)
        if isinstance(pending, dict):
            target = pending.get("target_type")
            if target in (TARGET_THIS, TARGET_BATCH):
                return target  # type: ignore[return-value]
        return TARGET_THIS
    if batch_running is True or (
        batch_running is None and state.get(_BATCH_WAS_RUNNING_KEY)
    ):
        return TARGET_BATCH
    return None


def sync_analyse_target_to_active_operation(
    session_state: MutableMapping[str, Any] | None = None,
    *,
    batch_running: bool | None = None,
) -> AnalysisTarget | None:
    """Force Analyse Target to match the ongoing operation (if any)."""
    state = session_state if session_state is not None else st.session_state
    target = resolve_active_analysis_target(state, batch_running=batch_running)
    if target is not None:
        state[ANALYSE_TARGET_KEY] = target
    return target


def _snapshot_summary(snapshot: Mapping[str, Any] | None) -> tuple[str, float, str]:
    """Return (title, pct 0-100, detail line) for the chip."""
    if not isinstance(snapshot, Mapping):
        return "Analysis running…", 0.0, ""
    phase = str(snapshot.get("phase") or "running_pipeline")
    status = str(snapshot.get("status") or "running")
    title = _PHASE_LABELS.get(phase, phase.replace("_", " ").title())
    if status == "completed":
        title = "Completed"
    elif status == "failed":
        title = "Failed"
    elif status == "cancelled":
        title = "Cancelled"
    try:
        pct = float(snapshot.get("pct") or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    pct = max(0.0, min(100.0, pct))
    detail_parts: list[str] = []
    item = str(snapshot.get("current_item") or "").strip()
    module = str(snapshot.get("current_module") or "").strip()
    if item:
        detail_parts.append(item)
    if module:
        detail_parts.append(module)
    completed = snapshot.get("completed", 0) or 0
    skipped = snapshot.get("skipped", 0) or 0
    failed = snapshot.get("failed", 0) or 0
    total = snapshot.get("total", 0) or 0
    done = int(completed) + int(skipped) + int(failed)
    if int(total) > 0:
        detail_parts.append(f"{done}/{int(total)}")
    return title, pct, " · ".join(detail_parts)


def _render_chip_html(*, title: str, pct: float, detail: str, target: str) -> str:
    safe_title = html.escape(title)
    safe_detail = html.escape(detail) if detail else ""
    safe_target = html.escape(target)
    width = f"{pct:.1f}"
    detail_html = (
        f'<div class="tx-global-run-progress__detail">{safe_detail}</div>'
        if safe_detail
        else ""
    )
    return (
        '<div class="tx-global-run-progress" role="status" '
        'aria-live="polite">'
        '<div class="tx-global-run-progress__row">'
        f'<span class="tx-global-run-progress__title">{safe_title}</span>'
        f'<span class="tx-global-run-progress__meta">{safe_target}</span>'
        "</div>"
        f"{detail_html}"
        '<div class="tx-global-run-progress__track" aria-hidden="true">'
        f'<div class="tx-global-run-progress__fill" style="width:{width}%"></div>'
        "</div>"
        f'<div class="tx-global-run-progress__pct">{width}%</div>'
        "</div>"
    )


def _project_root_for_active_run(
    session_state: Mapping[str, Any] | MutableMapping[str, Any],
) -> str | None:
    pending = session_state.get(_PENDING_LAUNCH_KEY)
    if isinstance(pending, dict):
        root = pending.get("project_root")
        if isinstance(root, str) and root.strip():
            return root.strip()
    root = session_state.get("root")
    if isinstance(root, str) and root.strip():
        return root.strip()
    return None


def _batch_is_running(batch_coord: Any | None) -> bool:
    if batch_coord is None:
        return False
    try:
        progress = batch_coord.get_progress()
        return bool(batch_coord.is_running() or progress.status == "running")
    except Exception:  # noqa: BLE001
        return False


def _sync_snapshots_from_coordinators(
    *,
    batch_coord: Any | None,
    get_analysis_coord: Callable[[str], Any] | None,
) -> tuple[bool, AnalysisTarget | None]:
    """Refresh session snapshots from live coordinators; return (active, target)."""
    from transcribe.ui.run_analysis import progress_to_snapshot
    from transcribe.ui.progress_snapshots import batch_analysis_progress_to_snapshot

    batch_running = _batch_is_running(batch_coord)
    if batch_coord is not None:
        try:
            batch_progress = batch_coord.get_progress()
        except Exception:  # noqa: BLE001
            batch_progress = None
        if batch_progress is not None:
            if batch_running:
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state[_BATCH_SNAPSHOT_KEY] = (
                    batch_analysis_progress_to_snapshot(batch_progress)
                )
            elif st.session_state.get(_BATCH_WAS_RUNNING_KEY):
                # Batch finished while off Analyse — drop the floating-chip latch.
                st.session_state[_BATCH_WAS_RUNNING_KEY] = False
                st.session_state[_BATCH_SNAPSHOT_KEY] = (
                    batch_analysis_progress_to_snapshot(batch_progress)
                )

    root = _project_root_for_active_run(st.session_state)
    if st.session_state.get(_IN_PROGRESS_KEY) and root and get_analysis_coord is not None:
        try:
            coord = get_analysis_coord(root)
            progress = coord.get_progress()
            st.session_state[SNAPSHOT_KEY] = progress_to_snapshot(progress)
        except Exception:  # noqa: BLE001 — chip must not break page routing
            pass

    active = is_analysis_operation_active(
        st.session_state, batch_running=batch_running if batch_coord is not None else None
    )
    target = resolve_active_analysis_target(
        st.session_state,
        batch_running=batch_running if batch_coord is not None else None,
    )
    return active, target


def _active_snapshot(target: AnalysisTarget | None) -> Mapping[str, Any] | None:
    if target == TARGET_BATCH:
        snap = st.session_state.get(_BATCH_SNAPSHOT_KEY)
        return snap if isinstance(snap, Mapping) else None
    snap = st.session_state.get(SNAPSHOT_KEY)
    return snap if isinstance(snap, Mapping) else None


@st.fragment(run_every=0.5)
def _global_analysis_progress_fragment(
    batch_coord: Any | None,
    get_analysis_coord: Callable[[str], Any] | None,
) -> None:
    """Poll snapshot while a run is active (works off the Analyse page)."""
    active, target = _sync_snapshots_from_coordinators(
        batch_coord=batch_coord,
        get_analysis_coord=get_analysis_coord,
    )
    if not active:
        return
    # Page owns the full panel; skip the floating chip there.
    if st.session_state.get(_UI_MODE_KEY) == "Analyse":
        return

    display_target = target or TARGET_THIS
    title, pct, detail = _snapshot_summary(_active_snapshot(display_target))

    st.markdown(
        '<div class="tx-global-run-progress-flag" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns([5, 1.2], gap="small")
    with cols[0]:
        st.markdown(
            _render_chip_html(
                title=title, pct=pct, detail=detail, target=display_target
            ),
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button(
            "View",
            key="tx_global_analysis_view",
            help="Open Analyse to see live progress and controls.",
            width="stretch",
        ):
            st.session_state[_UI_MODE_KEY] = "Analyse"
            st.session_state[ANALYSE_TARGET_KEY] = display_target
            st.rerun()


def render_global_analysis_progress(
    *,
    batch_coord: Any | None = None,
    get_analysis_coord: Callable[[str], Any] | None = None,
) -> None:
    """Shell entry: mount the floating chip when an analysis operation is active."""
    batch_running = _batch_is_running(batch_coord) if batch_coord is not None else None
    if not is_analysis_operation_active(st.session_state, batch_running=batch_running):
        return
    if st.session_state.get(_UI_MODE_KEY) == "Analyse":
        return
    _global_analysis_progress_fragment(batch_coord, get_analysis_coord)
