"""Run Analysis page — preset-driven module selection (TranscriptX model)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Sequence

import streamlit as st

from transcribe.analysis.coordinator import AnalysisCoordinator, AnalysisProgress
from transcribe.analysis.llm_runtime import (
    is_unsuitable_text_model_name,
    resolve_text_model_name,
    suitable_text_model_names,
)
from transcribe.analysis.module_catalog import format_module_label
from transcribe.analysis.parents import batch_module_order
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    PlanHashMismatchError,
    build_analysis_run_plan,
    verify_plan_hash,
)
from transcribe.analysis.presets import (
    PRESET_HELP,
    PRESET_LABELS,
    VALID_PRESETS,
    compute_effective_modules,
    expand_with_hard_parents,
    format_preset_label,
    label_to_preset,
    resolve_analysis_preset,
    suitable_detector_ids,
    suitable_module_ids,
)
from transcribe.errors import JobConflictError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import OllamaVisionProvider, invalidate_discovery_cache
from transcribe.services.project import ProjectService
from transcribe.ui.components.progress_panel import (
    SNAPSHOT_KEY,
    make_initial_snapshot,
    render_progress_panel,
)
from transcribe.ui import icons as ic
from transcribe.ui.module_ui_groups import format_detector_label, group_plan_for_ui

_PRESET_KEY = "run_analysis_preset"
_CUSTOM_KEY = "run_analysis_custom_modules"
_CUSTOM_WIDGET_KEY = "run_analysis_custom_modules_widget"
_BATCH_CUSTOM_WIDGET_KEY = "batch_analysis_custom_modules"
_CUSTOM_DETECT_KEY = "run_analysis_custom_detectors"
_CUSTOM_DETECT_WIDGET_KEY = "run_analysis_custom_detectors_widget"
_QA_ENABLE_KEY = "run_analysis_qa_enable"
_QA_TEXT_KEY = "run_analysis_qa_text"
_BATCH_QA_ENABLE_KEY = "batch_analysis_qa_enable"
_BATCH_QA_TEXT_KEY = "batch_analysis_qa_text"
_CUSTOM_QA_MODULE = "llm_custom_qa"
_REVIEW_KEEP_OPEN_KEY = "run_analysis_review_modules_keep_open"
_PENDING_REVIEW_REMOVAL_KEY = "run_analysis_pending_review_removal"
_KEY_PREFIX = "run_analysis"
_PENDING_LAUNCH_KEY = "run_analysis_pending_launch"
_IN_PROGRESS_KEY = "analysis_run_in_progress"
_LAST_RESULTS_KEY = "run_analysis_last_results"
_ACTIVE_RUN_ID_KEY = "run_analysis_active_run_id"


def analysis_run_in_progress(coord: AnalysisCoordinator | None = None) -> bool:
    if coord is not None and coord.is_running():
        return True
    return bool(st.session_state.get(_IN_PROGRESS_KEY, False))


def progress_to_snapshot(progress: AnalysisProgress) -> dict[str, Any]:
    """Map AnalysisCoordinator progress into the Streamlit progress panel snapshot."""
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    pct = (done / total * 100.0) if total else 0.0
    status = progress.status
    if status == "cancelled":
        panel_status = "failed"
        phase = "failed"
    elif status in ("completed", "failed"):
        panel_status = status
        phase = status
    else:
        panel_status = "running"
        phase = "running_pipeline"
    return {
        "status": panel_status,
        "phase": phase,
        "current_module": progress.current_module_id,
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message or "",
        "recent_logs": (
            list(st.session_state.get(SNAPSHOT_KEY, {}).get("recent_logs") or [])
            if isinstance(st.session_state.get(SNAPSHOT_KEY), dict)
            else []
        ),
        "error": progress.error,
    }


def apply_pending_review_module_removal(session_state: Any) -> None:
    """Apply a Review-modules removal queued after widgets already ran last tick."""
    pending = session_state.pop(_PENDING_REVIEW_REMOVAL_KEY, None)
    if not isinstance(pending, dict):
        return
    remaining = pending.get("remaining")
    # Empty remaining is valid when detectors remain in the Custom plan.
    if not isinstance(remaining, list):
        return
    session_state[_PRESET_KEY] = "Custom"
    session_state[_CUSTOM_KEY] = list(remaining)
    # Drop multiselect widget keys so they re-seed from custom_modules
    # (filtered to picker options) before the widgets are created.
    session_state.pop(_CUSTOM_WIDGET_KEY, None)
    session_state.pop(_BATCH_CUSTOM_WIDGET_KEY, None)
    if pending.get("clear_qa"):
        session_state[_QA_ENABLE_KEY] = False
        session_state[_QA_TEXT_KEY] = ""
        session_state[_BATCH_QA_ENABLE_KEY] = False
        session_state[_BATCH_QA_TEXT_KEY] = ""


def apply_review_module_removal(
    session_state: Any,
    *,
    module_ids: Sequence[str],
    remove_id: str,
    detector_ids: Sequence[str] = (),
    keep_open_key: str = _REVIEW_KEEP_OPEN_KEY,
) -> bool:
    """
    Queue dropping ``remove_id`` from the run (Custom + remainder).

    Returns False when the module is absent or would leave the plan empty.
    Removing ``llm_custom_qa`` also clears Ask-notebook intent on apply.
    """
    if remove_id not in module_ids:
        return False
    remaining = [m for m in module_ids if m != remove_id]
    if not remaining and not detector_ids:
        return False

    payload: dict[str, Any] = {"remaining": list(remaining)}
    if remove_id == _CUSTOM_QA_MODULE:
        payload["clear_qa"] = True
    session_state[_PENDING_REVIEW_REMOVAL_KEY] = payload
    session_state[keep_open_key] = True
    return True


def render_review_module_row(
    module_id: str,
    *,
    module_ids: Sequence[str],
    can_remove: bool,
    detector_ids: Sequence[str] = (),
    key_prefix: str = _KEY_PREFIX,
    keep_open_key: str = _REVIEW_KEEP_OPEN_KEY,
) -> None:
    """One Review-plan row with optional hover ✕ (TranscriptX pattern)."""
    label = format_module_label(module_id)
    if not can_remove:
        st.markdown(f"- {label}")
        return
    label_col, remove_col = st.columns([20, 1], vertical_alignment="center")
    with label_col:
        st.markdown(f"- {label}")
    with remove_col:
        if st.button(
            "",
            key=f"{key_prefix}_review_rm_{module_id}",
            help=f"Remove from run: {label}",
            type="tertiary",
            icon=ic.CLOSE,
        ):
            if apply_review_module_removal(
                st.session_state,
                module_ids=module_ids,
                remove_id=module_id,
                detector_ids=detector_ids,
                keep_open_key=keep_open_key,
            ):
                st.rerun()
            else:
                st.toast("Keep at least one module or detector in the run.")


def render_module_review(
    module_ids: tuple[str, ...] | Sequence[str],
    detector_ids: Sequence[str] = (),
    *,
    expander_title: str = "Review plan",
    key_prefix: str = _KEY_PREFIX,
    keep_open_key: str = _REVIEW_KEEP_OPEN_KEY,
) -> None:
    """Grouped plan list with hover-to-remove ✕ on modules (shell CSS)."""
    expanded = bool(st.session_state.pop(keep_open_key, False))
    ids = tuple(module_ids)
    dets = tuple(detector_ids)
    with st.expander(expander_title, expanded=expanded):
        can_remove = (len(ids) + len(dets)) > 1
        for title, rows in group_plan_for_ui(ids, dets):
            st.markdown(f"**{title}**")
            for mid in rows:
                if title == "Detection":
                    st.markdown(f"- {format_detector_label(mid)}")
                else:
                    render_review_module_row(
                        mid,
                        module_ids=ids,
                        can_remove=can_remove and bool(ids),
                        detector_ids=dets,
                        key_prefix=key_prefix,
                        keep_open_key=keep_open_key,
                    )


def _render_module_review(
    module_ids: tuple[str, ...],
    detector_ids: tuple[str, ...] = (),
) -> None:
    render_module_review(module_ids, detector_ids)


def _render_post_analysis_actions(*, projects: ProjectService, project: Any) -> None:
    """Configurable next-step strip after a finished this-notebook Analyse run."""
    last = st.session_state.get(_LAST_RESULTS_KEY)
    if not isinstance(last, dict) or not last:
        return
    from transcribe.ui.action_menus.ids import SectionId
    from transcribe.ui.post_job import render_post_job_strip
    from transcribe.runtime_paths import build_runtime_paths

    runtime = build_runtime_paths()
    render_post_job_strip(
        SectionId.ANALYSE_COMPLETE,
        project=project,
        root=projects.paths.root,
        projects_dir=runtime.projects_dir,
        instance_prefix="analyse_done",
    )


def _sync_snapshot_from_coord(coord: AnalysisCoordinator) -> AnalysisProgress:
    progress = coord.get_progress()
    snap = progress_to_snapshot(progress)
    # Append a log line when the latest event changes.
    prev = st.session_state.get(SNAPSHOT_KEY)
    logs = list(prev.get("recent_logs") or []) if isinstance(prev, dict) else []
    event = snap.get("latest_event") or ""
    if event and (not logs or not logs[-1].endswith(event)):
        import datetime

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{ts}] {event}")
        snap["recent_logs"] = logs[-100:]
    else:
        snap["recent_logs"] = logs
    st.session_state[SNAPSHOT_KEY] = snap
    return progress


def _finalize_run(coord: AnalysisCoordinator, progress: AnalysisProgress) -> None:
    results = coord.get_results()
    st.session_state[_LAST_RESULTS_KEY] = {
        mid: {
            "outcome": env.get("outcome"),
            "capability": env.get("capability"),
        }
        for mid, env in results.items()
    }
    st.session_state[_IN_PROGRESS_KEY] = False
    st.session_state.pop(_PENDING_LAUNCH_KEY, None)
    st.session_state.pop(_ACTIVE_RUN_ID_KEY, None)
    try:
        from transcribe.ui.run_analysis_batch import invalidate_batch_analyse_caches

        invalidate_batch_analyse_caches()
    except Exception:  # noqa: BLE001
        pass
    if progress.status == "failed":
        # Keep error visible on the snapshot.
        pass
    elif progress.status == "completed":
        from transcribe.analysis.module_catalog import get_module_info
        from transcribe.ui.navigation import normalize_ui_mode

        has_modules = any(get_module_info(mid) is not None for mid in results)
        dest = "Overview" if has_modules else "Detect"
        st.session_state["ui_mode"] = normalize_ui_mode(dest)


def _start_coordinator_run(
    pending: dict[str, Any],
    *,
    projects: ProjectService,
    coord: AnalysisCoordinator,
) -> None:
    """Start from a frozen AnalysisRunPlan already bound in pending (no re-snapshot)."""
    plan_raw = pending.get("plan")
    launch_ids = list(pending.get("modules") or [])
    detector_ids = list(pending.get("detectors") or [])
    if isinstance(plan_raw, dict):
        detector_ids = list(plan_raw.get("detector_ids") or detector_ids)
    st.session_state[SNAPSHOT_KEY] = make_initial_snapshot(
        len(launch_ids) + len(detector_ids)
    )
    try:
        if not isinstance(plan_raw, dict):
            raise PlanHashMismatchError("pending launch is missing a frozen analysis plan")
        plan = AnalysisRunPlan.from_dict(plan_raw)
        expected = str(pending.get("plan_hash") or plan.plan_hash or "")
        if not expected or plan.plan_hash != expected or not verify_plan_hash(plan):
            raise PlanHashMismatchError("pending plan_hash does not match the frozen analysis plan")
        run_id = coord.start(plan)
        st.session_state[_ACTIVE_RUN_ID_KEY] = run_id
        pending["started"] = True
        pending["run_id"] = run_id
        st.session_state[_PENDING_LAUNCH_KEY] = pending
    except JobConflictError as exc:
        st.session_state[_IN_PROGRESS_KEY] = False
        st.session_state.pop(_PENDING_LAUNCH_KEY, None)
        st.session_state[SNAPSHOT_KEY] = {
            **make_initial_snapshot(len(launch_ids)),
            "status": "failed",
            "phase": "failed",
            "error": str(exc),
            "latest_event": str(exc),
        }
    except PlanHashMismatchError as exc:
        st.session_state[_IN_PROGRESS_KEY] = False
        st.session_state.pop(_PENDING_LAUNCH_KEY, None)
        st.session_state[SNAPSHOT_KEY] = {
            **make_initial_snapshot(len(launch_ids)),
            "status": "failed",
            "phase": "failed",
            "error": str(exc),
            "latest_event": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        st.session_state[_IN_PROGRESS_KEY] = False
        st.session_state.pop(_PENDING_LAUNCH_KEY, None)
        st.session_state[SNAPSHOT_KEY] = {
            **make_initial_snapshot(len(launch_ids)),
            "status": "failed",
            "phase": "failed",
            "error": str(exc),
            "latest_event": str(exc),
        }


def _render_config_and_launch(
    *,
    projects: ProjectService,
    project: Any,
    coord: AnalysisCoordinator,
) -> None:
    apply_pending_review_module_removal(st.session_state)

    suitable = list(suitable_module_ids())
    suitable_dets = list(suitable_detector_ids())
    options = [PRESET_LABELS[p] for p in VALID_PRESETS]
    if _PRESET_KEY not in st.session_state:
        st.session_state[_PRESET_KEY] = "Balanced"
    elif st.session_state.get(_PRESET_KEY) not in options:
        st.session_state[_PRESET_KEY] = "Balanced"

    label = st.segmented_control(
        "Analysis preset",
        options=options,
        key=_PRESET_KEY,
        help=PRESET_HELP,
    )
    if label is None:
        label = st.session_state.get(_PRESET_KEY) or "Balanced"
    preset = label_to_preset(str(label))

    stored_custom = list(st.session_state.get(_CUSTOM_KEY) or [])
    if not stored_custom:
        stored_custom = list(resolve_analysis_preset("balanced").module_ids)
        st.session_state[_CUSTOM_KEY] = stored_custom
    stored_detectors = list(st.session_state.get(_CUSTOM_DETECT_KEY) or [])

    if preset == "custom":
        if _CUSTOM_WIDGET_KEY not in st.session_state:
            st.session_state[_CUSTOM_WIDGET_KEY] = [m for m in stored_custom if m in suitable]
        selected = st.multiselect(
            "Select modules",
            options=suitable,
            format_func=format_module_label,
            key=_CUSTOM_WIDGET_KEY,
        )
        st.session_state[_CUSTOM_KEY] = list(selected)
        custom_modules = selected
        if _CUSTOM_DETECT_WIDGET_KEY not in st.session_state:
            st.session_state[_CUSTOM_DETECT_WIDGET_KEY] = [
                d for d in stored_detectors if d in suitable_dets
            ]
        selected_dets = st.multiselect(
            "Select detectors",
            options=suitable_dets,
            format_func=format_detector_label,
            key=_CUSTOM_DETECT_WIDGET_KEY,
            help="Prompt-backed content detectors (poetry, lists, …).",
        )
        st.session_state[_CUSTOM_DETECT_KEY] = list(selected_dets)
        custom_detectors = selected_dets
    else:
        custom_modules = list(st.session_state.get(_CUSTOM_KEY) or [])
        custom_detectors = list(st.session_state.get(_CUSTOM_DETECT_KEY) or [])

    resolved = resolve_analysis_preset(
        preset,
        custom_modules=custom_modules,
        custom_detectors=custom_detectors,
    )

    qa_enabled = st.checkbox(
        "Include Ask notebook question",
        value=bool(st.session_state.get(_QA_ENABLE_KEY, False)),
        key=_QA_ENABLE_KEY,
        help="Adds the llm_custom_qa module and runs it with your question.",
    )
    question_text: str | None = None
    if qa_enabled:
        question_text = st.text_area(
            "Question",
            value=st.session_state.get(_QA_TEXT_KEY, ""),
            key=_QA_TEXT_KEY,
            placeholder="What themes recur across these pages?",
        )

    plan = compute_effective_modules(
        resolved, custom_qa_execution=bool(qa_enabled and (question_text or "").strip())
    )
    parts = [f"**{format_preset_label(preset)}** · {len(plan.module_ids)} modules"]
    if plan.detector_ids:
        parts.append(f"{len(plan.detector_ids)} detectors")
    if resolved.preset != "custom":
        parts.append(f"v{resolved.content_version}")
    if plan.llm_count:
        parts.append(f"{plan.llm_count} use an LLM")
    if plan.heavy_count:
        parts.append(f"{plan.heavy_count} heavy")
    st.caption(" · ".join(parts))
    _render_module_review(plan.module_ids, plan.detector_ids)

    needs_llm = plan.needs_llm()
    text_model = resolve_text_model_name(project.settings.text_model_name)
    if needs_llm:
        with st.expander("LLM setup", expanded=not bool(text_model)):
            st.caption(
                "LLM modules and detectors need a local **text** Ollama model "
                "(vision/embedding models are rejected). "
                "Workspace default: Settings → Models."
            )
            provider = OllamaVisionProvider(project.settings.base_url)
            refresh_models = st.button("Refresh models", key="run_analysis_refresh_models", icon=ic.REFRESH)
            if refresh_models:
                invalidate_discovery_cache(project.settings.base_url)
            discovery = provider.list_models(refresh=refresh_models)
            names = suitable_text_model_names(discovery.models)
            if text_model and is_unsuitable_text_model_name(text_model):
                st.warning(
                    f"Saved model `{text_model}` is vision/embedding — "
                    "choose a text model below."
                )
            if names:
                idx = names.index(text_model) if text_model in names else 0
                chosen = st.selectbox("Text model", options=names, index=idx)
            else:
                st.caption("No suitable text models discovered from Ollama.")
                chosen = st.text_input("Text model name", value="")
            from transcribe.ui.components.model_info import render_model_information

            render_model_information(
                discovery.models,
                selected=chosen or text_model,
                role="text",
                key="analyse_text_model_info",
            )
            if st.button("Save text model", key="run_analysis_save_text_model", icon=ic.SAVE):
                settings = project.settings
                settings.text_model_name = chosen
                projects.save_settings(project, settings)
                st.success(f"Text model set to `{chosen}`")
                st.rerun()
            if not (chosen or text_model):
                st.warning("Select a text model before running LLM modules or detectors.")

    launch_ids = batch_module_order(list(expand_with_hard_parents(plan.module_ids)))
    launch_detectors = list(plan.detector_ids)
    run_disabled = (
        (not launch_ids and not launch_detectors)
        or (needs_llm and not (text_model or "").strip())
        or coord.is_running()
    )

    if st.button(
        "Run analysis",
        type="primary",
        disabled=run_disabled,
        width="stretch",
        key="run_analysis_launch",
        icon=ic.RUN,
    ):
        q = (question_text or "").strip() or None
        try:
            frozen = build_analysis_run_plan(
                project_service=projects,
                module_ids=launch_ids,
                question_text=q,
                preset_label=format_preset_label(preset),
                preset_key=resolved.preset,
                preset_content_version=resolved.content_version,
                preset_policy_fingerprint=resolved.policy_fingerprint,
                clock=SystemClock(),
                ids=UuidGenerator(),
                project=project,
                detector_ids=launch_detectors,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not freeze analysis plan: {exc}")
            return

        model_bit = (
            f"`{frozen.text_model.model_name}`"
            if frozen.text_model is not None
            else "no text model (LLM steps will show Needs a text model)"
        )
        version_bit = (
            f" · preset v{resolved.content_version}" if resolved.preset != "custom" else " · custom"
        )
        detector_bit = (
            f" · {len(frozen.detector_ids)} detectors" if frozen.detector_ids else ""
        )
        from transcribe.ui.targets import TARGET_THIS

        st.session_state[_PENDING_LAUNCH_KEY] = {
            "modules": list(frozen.module_ids),
            "detectors": list(frozen.detector_ids),
            "question_text": q,
            "preset_label": format_preset_label(preset),
            "preset_key": resolved.preset,
            "preset_content_version": resolved.content_version,
            "plan": frozen.as_dict(),
            "plan_hash": frozen.plan_hash,
            "form_cleared": False,
            "started": False,
            "target_type": TARGET_THIS,
            "project_root": str(projects.paths.root),
            "footer_summary": (
                f"Running **{format_preset_label(preset)}**{version_bit} · "
                f"{len(frozen.module_ids)} modules{detector_bit} · {model_bit}"
            ),
        }
        st.session_state[SNAPSHOT_KEY] = make_initial_snapshot(frozen.step_total())
        st.session_state[_IN_PROGRESS_KEY] = True
        st.rerun()


def render_run_analysis_form(
    *,
    projects: ProjectService,
    project: Any,
    coord: AnalysisCoordinator | None = None,
) -> bool:
    """Configure and launch a notebook analysis run from a TX-style preset.

    Returns True while a run is in progress (caller should hide published tabs).
    """
    if coord is None:
        from transcribe.analysis.coordinator import AnalysisCoordinator

        coord = AnalysisCoordinator(projects, clock=SystemClock(), ids=UuidGenerator())

    running = analysis_run_in_progress(coord)

    # Post-run strip only when idle so links never point at a mid-run state.
    if not running:
        _render_post_analysis_actions(projects=projects, project=project)

    pending = st.session_state.get(_PENDING_LAUNCH_KEY)
    if running and isinstance(pending, dict):
        summary = pending.get("footer_summary") or "Running analysis…"
        st.markdown(summary)

        # Phase 1: clear form widgets via rerun before starting the thread.
        if not pending.get("form_cleared"):
            pending["form_cleared"] = True
            st.session_state[_PENDING_LAUNCH_KEY] = pending
            snapshot = st.session_state.get(SNAPSHOT_KEY)
            if snapshot is not None:
                render_progress_panel(snapshot)
            st.rerun()
            return True

        # Phase 2: freeze plan + start async coordinator (non-blocking).
        if not pending.get("started"):
            _start_coordinator_run(pending, projects=projects, coord=coord)
            progress = _sync_snapshot_from_coord(coord)
            render_progress_panel(st.session_state[SNAPSHOT_KEY])
            if progress.status in ("failed",) and not coord.is_running():
                _finalize_run(coord, progress)
            st.rerun()
            return True

        # Phase 3: fragment poll — avoids full-app grey-out sleep/rerun loops.
        poll = timedelta(milliseconds=400)

        @st.fragment(run_every=poll)
        def analysis_status_panel() -> None:
            progress = _sync_snapshot_from_coord(coord)
            render_progress_panel(st.session_state[SNAPSHOT_KEY])
            if st.button("Cancel analysis", key="run_analysis_cancel", icon=ic.STOP):
                coord.cancel()
                st.rerun()
            if coord.is_running() or progress.status == "running":
                return
            _finalize_run(coord, progress)
            st.rerun()

        analysis_status_panel()
        return True

    # Coordinator still running after session flags cleared (e.g. navigation).
    if coord.is_running():
        st.session_state[_IN_PROGRESS_KEY] = True
        st.markdown("Running analysis…")
        poll = timedelta(milliseconds=400)

        @st.fragment(run_every=poll)
        def orphan_status_panel() -> None:
            progress = _sync_snapshot_from_coord(coord)
            st.markdown(progress.message or "Running analysis…")
            render_progress_panel(st.session_state[SNAPSHOT_KEY])
            if st.button("Cancel analysis", key="run_analysis_cancel_orphan", icon=ic.STOP):
                coord.cancel()
                st.rerun()
            if coord.is_running() or progress.status == "running":
                return
            _finalize_run(coord, progress)
            st.rerun()

        orphan_status_panel()
        return True

    # Idle: show last progress + form (fragment isolates preset/module clicks).
    last_snapshot = st.session_state.get(SNAPSHOT_KEY)
    if last_snapshot and last_snapshot.get("status") in ("completed", "failed"):
        with st.expander("Last run progress", expanded=False):
            render_progress_panel(last_snapshot)

    @st.fragment
    def config_fragment() -> None:
        _render_config_and_launch(projects=projects, project=project, coord=coord)

    config_fragment()

    last = st.session_state.get(_LAST_RESULTS_KEY)
    if isinstance(last, dict) and last:
        from transcribe.ui.analysis_health_view import last_run_product_summary

        st.subheader("Last run")
        preset_label = st.session_state.get(_PRESET_KEY)
        if isinstance(preset_label, str):
            try:
                preset_label = format_preset_label(label_to_preset(preset_label))
            except Exception:  # noqa: BLE001
                pass
        else:
            preset_label = None
        st.caption(last_run_product_summary(last, preset_label=preset_label))
        with st.expander("Advanced · per-step outcomes"):
            for mid, row in last.items():
                st.write(
                    f"**{format_module_label(mid)}:** "
                    f"{row.get('outcome')} / {row.get('capability')}"
                )

    return False
