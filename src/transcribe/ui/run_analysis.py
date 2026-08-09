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
from transcribe.ui.module_ui_groups import group_modules_for_ui
from transcribe.ui.shell import render_page_shell

_PRESET_KEY = "run_analysis_preset"
_CUSTOM_KEY = "run_analysis_custom_modules"
_CUSTOM_WIDGET_KEY = "run_analysis_custom_modules_widget"
_QA_ENABLE_KEY = "run_analysis_qa_enable"
_QA_TEXT_KEY = "run_analysis_qa_text"
_CUSTOM_QA_MODULE = "llm_custom_qa"
_REVIEW_KEEP_OPEN_KEY = "run_analysis_review_modules_keep_open"
_PENDING_REVIEW_REMOVAL_KEY = "run_analysis_pending_review_removal"
_KEY_PREFIX = "run_analysis"


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


def render_run_analysis_form(
    *,
    projects: ProjectService,
    project: Any,
) -> None:
    """Configure and launch a notebook analysis run from a TX-style preset."""
    render_page_shell(
        "Run Analysis",
        "Choose an analysis preset (or custom modules), optional Ask-notebook "
        "question, then run.",
    )

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
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        with st.spinner(f"Running {len(launch_ids)} modules…"):
            q = (question_text or "").strip() or None
            results: dict[str, dict[str, Any]] = {}
            for mid in launch_ids:
                try:
                    if mid == "llm_custom_qa" and q:
                        results[mid] = runner.run_module(mid, question_text=q)
                    else:
                        results[mid] = runner.run_module(mid)
                except Exception as exc:  # noqa: BLE001
                    results[mid] = {
                        "module_id": mid,
                        "outcome": "failed",
                        "capability": "failed",
                        "payload": {"error": {"message": str(exc)}},
                    }
        st.session_state["run_analysis_last_results"] = {
            mid: {
                "outcome": env.get("outcome"),
                "capability": env.get("capability"),
            }
            for mid, env in results.items()
        }
        st.rerun()

    last = st.session_state.get("run_analysis_last_results")
    if isinstance(last, dict) and last:
        st.subheader("Last run")
        ok = sum(1 for v in last.values() if v.get("outcome") == "success")
        st.caption(f"{ok}/{len(last)} succeeded")
        for mid, row in last.items():
            st.write(
                f"**{format_module_label(mid)}:** outcome=`{row.get('outcome')}` "
                f"capability=`{row.get('capability')}`"
            )
