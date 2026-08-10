"""Run Analysis page — preset-driven module selection (TranscriptX model)."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from transcribe.analysis.llm_runtime import (
    is_unsuitable_text_model_name,
    suitable_text_model_names,
)
from transcribe.analysis.module_catalog import format_module_label
from transcribe.analysis.parents import batch_module_order
from transcribe.analysis.presets import (
    PRESET_HELP,
    PRESET_LABELS,
    VALID_PRESETS,
    compute_effective_modules,
    expand_with_hard_parents,
    format_preset_label,
    label_to_preset,
    resolve_analysis_preset,
    suitable_module_ids,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import OllamaVisionProvider, invalidate_discovery_cache
from transcribe.services.project import ProjectService
from transcribe.ui.components.action_links import render_action_link
from transcribe.ui.components.progress_panel import (
    SNAPSHOT_KEY,
    StreamlitProgressCallback,
    make_initial_snapshot,
    render_progress_panel,
)
from transcribe.ui.module_ui_groups import group_modules_for_ui
from transcribe.ui.shell import render_page_shell, set_ui_mode

_PRESET_KEY = "run_analysis_preset"
_CUSTOM_KEY = "run_analysis_custom_modules"
_CUSTOM_WIDGET_KEY = "run_analysis_custom_modules_widget"
_QA_ENABLE_KEY = "run_analysis_qa_enable"
_QA_TEXT_KEY = "run_analysis_qa_text"
_CUSTOM_QA_MODULE = "llm_custom_qa"
_REVIEW_KEEP_OPEN_KEY = "run_analysis_review_modules_keep_open"
_PENDING_REVIEW_REMOVAL_KEY = "run_analysis_pending_review_removal"
_KEY_PREFIX = "run_analysis"
_PENDING_LAUNCH_KEY = "run_analysis_pending_launch"
_IN_PROGRESS_KEY = "analysis_run_in_progress"
_LAST_RESULTS_KEY = "run_analysis_last_results"


def analysis_run_in_progress() -> bool:
    return bool(st.session_state.get(_IN_PROGRESS_KEY, False))


def apply_pending_review_module_removal(session_state: Any) -> None:
    """Apply a Review-modules removal queued after widgets already ran last tick."""
    pending = session_state.pop(_PENDING_REVIEW_REMOVAL_KEY, None)
    if not isinstance(pending, dict):
        return
    remaining = pending.get("remaining")
    if not isinstance(remaining, list) or not remaining:
        return
    session_state[_PRESET_KEY] = "Custom"
    session_state[_CUSTOM_KEY] = list(remaining)
    # Drop the multiselect widget key so it re-seeds from custom_modules
    # (filtered to picker options) before the widget is created.
    session_state.pop(_CUSTOM_WIDGET_KEY, None)
    if pending.get("clear_qa"):
        session_state[_QA_ENABLE_KEY] = False
        session_state[_QA_TEXT_KEY] = ""


def apply_review_module_removal(
    session_state: Any,
    *,
    module_ids: Sequence[str],
    remove_id: str,
) -> bool:
    """
    Queue dropping ``remove_id`` from the run (Custom + remainder).

    Returns False when the module is absent or would leave the plan empty.
    Removing ``llm_custom_qa`` also clears Ask-notebook intent on apply.
    """
    if remove_id not in module_ids:
        return False
    remaining = [m for m in module_ids if m != remove_id]
    if not remaining:
        return False

    payload: dict[str, Any] = {"remaining": list(remaining)}
    if remove_id == _CUSTOM_QA_MODULE:
        payload["clear_qa"] = True
    session_state[_PENDING_REVIEW_REMOVAL_KEY] = payload
    session_state[_REVIEW_KEEP_OPEN_KEY] = True
    return True


def _render_review_module_row(
    module_id: str,
    *,
    module_ids: Sequence[str],
    can_remove: bool,
) -> None:
    label = format_module_label(module_id)
    if not can_remove:
        st.markdown(f"- {label}")
        return
    label_col, remove_col = st.columns([20, 1], vertical_alignment="center")
    with label_col:
        st.markdown(f"- {label}")
    with remove_col:
        if st.button(
            "✕",
            key=f"{_KEY_PREFIX}_review_rm_{module_id}",
            help=f"Remove from run: {label}",
            type="tertiary",
        ):
            if apply_review_module_removal(
                st.session_state,
                module_ids=module_ids,
                remove_id=module_id,
            ):
                st.rerun()
            else:
                st.toast("Keep at least one module in the run.")


def _render_module_review(module_ids: tuple[str, ...]) -> None:
    expanded = bool(st.session_state.pop(_REVIEW_KEEP_OPEN_KEY, False))
    with st.expander("Review modules", expanded=expanded):
        can_remove = len(module_ids) > 1
        for title, rows in group_modules_for_ui(module_ids):
            st.markdown(f"**{title}**")
            for mid in rows:
                _render_review_module_row(
                    mid,
                    module_ids=module_ids,
                    can_remove=can_remove,
                )


def _render_post_analysis_actions() -> None:
    """Compact next-step strip after a successful/finished Analyse run."""
    last = st.session_state.get(_LAST_RESULTS_KEY)
    if not isinstance(last, dict) or not last:
        return
    st.markdown("#### Next")
    cols = st.columns(3, gap="small")
    with cols[0]:
        if render_action_link(
            "View",
            key="analysis_done_view",
            icon=":material/menu_book:",
            help="Open this notebook on the View page.",
        ):
            set_ui_mode("View")
    with cols[1]:
        if render_action_link(
            "Review",
            key="analysis_done_review",
            icon=":material/rate_review:",
            help="Browse and edit transcribed pages.",
        ):
            set_ui_mode("Review")
    with cols[2]:
        if render_action_link(
            "Published results",
            key="analysis_done_results",
            icon=":material/analytics:",
            help="Stay on Analyse and inspect published result tabs below.",
        ):
            st.session_state["_analysis_scroll_results"] = True
            st.toast("Published results are below.")


def _execute_pending_launch(
    pending: dict[str, Any],
    *,
    projects: ProjectService,
    progress: StreamlitProgressCallback,
) -> None:
    """Run snapshotted modules; sole launch authority after Run click."""
    launch_ids = list(pending.get("modules") or [])
    question_text = pending.get("question_text")
    st.session_state[SNAPSHOT_KEY] = make_initial_snapshot(len(launch_ids))
    progress.refresh_panel()

    runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
    results: dict[str, dict[str, Any]] = {}
    completed = failed = skipped = 0
    total = len(launch_ids)

    try:
        for index, mid in enumerate(launch_ids, start=1):
            progress.module_started(mid, index=index, total=total)
            try:
                if mid == "llm_custom_qa" and question_text:
                    env = runner.run_module(mid, question_text=question_text)
                else:
                    env = runner.run_module(mid)
            except Exception as exc:  # noqa: BLE001
                env = {
                    "module_id": mid,
                    "outcome": "failed",
                    "capability": "failed",
                    "payload": {"error": {"message": str(exc)}},
                }
            results[mid] = env
            outcome = str(env.get("outcome") or "failed")
            if outcome == "failed":
                failed += 1
            else:
                completed += 1
            progress.module_finished(
                mid,
                outcome=outcome,
                completed=completed,
                failed=failed,
                skipped=skipped,
                total=total,
            )
        progress.run_completed()
    except Exception as exc:  # noqa: BLE001
        progress.run_failed(str(exc))
    finally:
        st.session_state[_IN_PROGRESS_KEY] = False
        st.session_state.pop(_PENDING_LAUNCH_KEY, None)
        progress.refresh_panel()

    st.session_state[_LAST_RESULTS_KEY] = {
        mid: {
            "outcome": env.get("outcome"),
            "capability": env.get("capability"),
        }
        for mid, env in results.items()
    }


def _render_config_and_launch(
    *,
    projects: ProjectService,
    project: Any,
) -> None:
    apply_pending_review_module_removal(st.session_state)

    suitable = list(suitable_module_ids())
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

    if preset == "custom":
        if _CUSTOM_WIDGET_KEY not in st.session_state:
            st.session_state[_CUSTOM_WIDGET_KEY] = [
                m for m in stored_custom if m in suitable
            ]
        selected = st.multiselect(
            "Select modules",
            options=suitable,
            format_func=format_module_label,
            key=_CUSTOM_WIDGET_KEY,
        )
        st.session_state[_CUSTOM_KEY] = list(selected)
        custom_modules = selected
    else:
        custom_modules = list(st.session_state.get(_CUSTOM_KEY) or [])

    resolved = resolve_analysis_preset(preset, custom_modules=custom_modules)

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
    if plan.llm_count:
        parts.append(f"{plan.llm_count} use an LLM")
    if plan.heavy_count:
        parts.append(f"{plan.heavy_count} heavy")
    st.caption(" · ".join(parts))
    _render_module_review(plan.module_ids)

    needs_llm = plan.llm_count > 0
    text_model = project.settings.text_model_name or ""
    if needs_llm:
        with st.expander("LLM setup", expanded=not bool(text_model)):
            st.caption(
                "LLM modules need a local **text** Ollama model "
                "(vision/embedding models are rejected)."
            )
            provider = OllamaVisionProvider(project.settings.base_url)
            refresh_models = st.button("Refresh models", key="run_analysis_refresh_models")
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
            if st.button("Save text model", key="run_analysis_save_text_model"):
                settings = project.settings
                settings.text_model_name = chosen
                projects.save_settings(project, settings)
                st.success(f"Text model set to `{chosen}`")
                st.rerun()
            if not (chosen or text_model):
                st.warning("Select a text model before running LLM modules.")

    launch_ids = batch_module_order(list(expand_with_hard_parents(plan.module_ids)))
    run_disabled = not launch_ids or (
        needs_llm and not (project.settings.text_model_name or "").strip()
    )

    if st.button(
        "Run analysis",
        type="primary",
        disabled=run_disabled,
        width="stretch",
        key="run_analysis_launch",
    ):
        q = (question_text or "").strip() or None
        st.session_state[_PENDING_LAUNCH_KEY] = {
            "modules": list(launch_ids),
            "question_text": q,
            "form_cleared": False,
            "started": False,
            "footer_summary": (
                f"Running **{format_preset_label(preset)}** · "
                f"{len(launch_ids)} modules"
            ),
        }
        st.session_state[SNAPSHOT_KEY] = make_initial_snapshot(len(launch_ids))
        st.session_state[_IN_PROGRESS_KEY] = True
        st.rerun()


def render_run_analysis_form(
    *,
    projects: ProjectService,
    project: Any,
) -> bool:
    """Configure and launch a notebook analysis run from a TX-style preset.

    Returns True while a run is in progress (caller should hide published tabs).
    """
    render_page_shell(
        "Run Analysis",
        "Choose an analysis preset (or custom modules), optional Ask-notebook "
        "question, then run.",
    )

    # Post-run strip only when idle so links never point at a mid-run state.
    if not analysis_run_in_progress():
        _render_post_analysis_actions()

    pending = st.session_state.get(_PENDING_LAUNCH_KEY)
    if analysis_run_in_progress() and isinstance(pending, dict):
        summary = pending.get("footer_summary") or "Running analysis…"
        st.markdown(summary)
        progress_slot = st.empty()
        snapshot = st.session_state.get(SNAPSHOT_KEY)
        if snapshot is not None:
            with progress_slot.container():
                render_progress_panel(snapshot)
        else:
            with progress_slot.container():
                st.info("Analysis is running…")

        # Three-phase launch (TX model):
        # 1) click stores pending + rerun
        # 2) paint progress only + form_cleared + rerun (ends script → clears form)
        # 3) paint progress + execute (blocking; form stays gone)
        if not pending.get("form_cleared"):
            pending["form_cleared"] = True
            st.session_state[_PENDING_LAUNCH_KEY] = pending
            st.rerun()
            return True
        if not pending.get("started"):
            pending["started"] = True
            st.session_state[_PENDING_LAUNCH_KEY] = pending
            progress = StreamlitProgressCallback(render_slot=progress_slot)
            _execute_pending_launch(pending, projects=projects, progress=progress)
            st.rerun()
        return True

    if analysis_run_in_progress():
        snapshot = st.session_state.get(SNAPSHOT_KEY)
        if snapshot is not None:
            render_progress_panel(snapshot)
        else:
            st.info("Analysis is running…")
        return True

    last_snapshot = st.session_state.get(SNAPSHOT_KEY)
    if last_snapshot and last_snapshot.get("status") in ("completed", "failed"):
        with st.expander("Last run progress", expanded=False):
            render_progress_panel(last_snapshot)

    _render_config_and_launch(projects=projects, project=project)

    last = st.session_state.get(_LAST_RESULTS_KEY)
    if isinstance(last, dict) and last:
        st.subheader("Last run")
        ok = sum(1 for v in last.values() if v.get("outcome") == "success")
        st.caption(f"{ok}/{len(last)} succeeded")
        for mid, row in last.items():
            st.write(
                f"**{format_module_label(mid)}:** outcome=`{row.get('outcome')}` "
                f"capability=`{row.get('capability')}`"
            )

    return False
