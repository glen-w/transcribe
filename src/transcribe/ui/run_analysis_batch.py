"""Analyse → Batch launch and live progress (multi-notebook)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import streamlit as st

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
from transcribe.corpus.analysis_batch_run import AnalysisBatchRunStore
from transcribe.corpus.import_run import ImportRunStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import JobConflictError, TranscribeError, ValidationError
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    BatchAnalysisProgress,
    list_analysis_candidates,
    select_by_ids,
    select_from_import_run,
    select_needing_analysis,
)
from transcribe.services.project import ProjectService
from transcribe.ui.components.action_links import render_action_link
from transcribe.ui.components.progress_panel import render_progress_panel
from transcribe.ui.shell import set_ui_mode
from transcribe.ui.targets import (
    ANALYSE_BATCH_IMPORT_RUN_KEY,
    ANALYSE_BATCH_NOTEBOOK_IDS_KEY,
    ANALYSE_BATCH_SOURCE_KEY,
)

_BATCH_SNAPSHOT_KEY = "batch_analysis_progress_snapshot"
_BATCH_WAS_RUNNING_KEY = "_batch_analysis_was_running"
_BATCH_POST_RUN_KEY = "_batch_analysis_post_run_id"
_PRESET_KEY = "run_analysis_preset"
_CUSTOM_KEY = "run_analysis_custom_modules"
_QA_ENABLE_KEY = "run_analysis_qa_enable"
_QA_TEXT_KEY = "run_analysis_qa_text"


def batch_analysis_progress_to_snapshot(progress: BatchAnalysisProgress) -> dict[str, Any]:
    """Map BatchAnalysisProgress into the shared progress panel snapshot."""
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    module_frac = 0.0
    if progress.status == "running" and progress.modules_total:
        module_done = progress.modules_completed + progress.modules_failed
        module_frac = min(1.0, module_done / progress.modules_total)
    pct = ((done + module_frac) / total * 100.0) if total else 0.0
    status = progress.status
    if status == "completed":
        panel_status, phase = "completed", "completed"
        pct = 100.0 if total else pct
    elif status == "partial":
        panel_status, phase = "completed", "partial"
    elif status == "cancelled":
        panel_status, phase = "failed", "cancelled"
    elif status == "failed":
        panel_status, phase = "failed", "failed"
    else:
        panel_status, phase = "running", "running_pipeline"
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": progress.current_item,
        "current_module": progress.current_module_id,
        "detail_current": progress.current_module_id,
        "detail_completed": progress.modules_completed,
        "detail_failed": progress.modules_failed,
        "detail_skipped": progress.modules_skipped,
        "detail_total": progress.modules_total,
        "detail_unit": "modules in this notebook",
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.error
        if status == "failed"
        else (progress.message if status == "failed" else None),
    }


def render_batch_analysis_progress(
    coord: BatchAnalysisCoordinator, runtime: RuntimePaths
) -> bool:
    """Return True when the page should skip the settings form."""
    live = coord.get_progress()
    st.session_state[_BATCH_WAS_RUNNING_KEY] = live.status == "running"
    is_running = live.status == "running" or coord.is_running()
    post_id = st.session_state.get(_BATCH_POST_RUN_KEY)
    show_post = (
        bool(post_id)
        and live.analysis_batch_id == post_id
        and live.status in {"completed", "cancelled", "failed", "partial"}
    )
    if not is_running and not show_post:
        return False

    if is_running:
        poll = timedelta(seconds=2)

        @st.fragment(run_every=poll)
        def batch_status_panel() -> None:
            progress = coord.get_progress()
            render_progress_panel(
                batch_analysis_progress_to_snapshot(progress),
                unit_label="notebooks",
                current_label="Current notebook",
            )
            if (
                st.session_state.get(_BATCH_WAS_RUNNING_KEY)
                and progress.status != "running"
            ):
                st.session_state[_BATCH_WAS_RUNNING_KEY] = False
                st.session_state[_BATCH_POST_RUN_KEY] = progress.analysis_batch_id
                st.rerun()

        batch_status_panel()
        if st.button("Stop after current notebook", key="batch_analysis_stop"):
            coord.request_cancel()
            st.info(
                "Stopping after current notebook; remaining notebooks will not start."
            )
        return True

    render_progress_panel(
        batch_analysis_progress_to_snapshot(live),
        unit_label="notebooks",
        current_label="Current notebook",
    )
    _render_batch_complete_actions(coord, live)
    return True


def _render_batch_complete_actions(
    coord: BatchAnalysisCoordinator, progress: BatchAnalysisProgress
) -> None:
    st.markdown("#### Next")
    run = None
    try:
        run = coord.store.load(progress.analysis_batch_id)
    except TranscribeError:
        run = None
    retry_ids = [
        item.notebook_id
        for item in (run.items if run else [])
        if item.state == "failed"
    ]
    cols = st.columns(3, gap="small")
    with cols[0]:
        if render_action_link(
            "Library",
            key="ax_batch_done_view",
            icon=":material/menu_book:",
            help="Open the notebook list.",
        ):
            set_ui_mode("Library")
    with cols[1]:
        if render_action_link(
            "Retry failed",
            key="ax_batch_done_retry",
            icon=":material/replay:",
            help="Re-run analysis on notebooks that failed.",
            disabled=not retry_ids,
        ):
            try:
                candidates = list_analysis_candidates(coord.corpus)
                selected = select_by_ids(candidates, retry_ids)
                new_run = coord.create_run(
                    selected,
                    module_ids=list(run.module_ids) if run else ["stats"],
                    question_text=run.question_text if run else None,
                    preset_label=run.preset_label if run else None,
                    preset_key=run.preset_key if run else None,
                    preset_content_version=run.preset_content_version if run else None,
                    preset_policy_fingerprint=(
                        run.preset_policy_fingerprint if run else None
                    ),
                    import_run_id=run.import_run_id if run else None,
                )
                coord.start(new_run.analysis_batch_id)
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                st.rerun()
            except (JobConflictError, TranscribeError, ValidationError) as exc:
                st.error(str(exc))
    with cols[2]:
        if render_action_link(
            "Change settings",
            key="ax_batch_done_settings",
            icon=":material/settings:",
            help="Return to batch analysis settings.",
        ):
            st.session_state.pop(_BATCH_POST_RUN_KEY, None)
            st.rerun()
    if run is not None:
        for item in run.items:
            bits = [
                item.state,
                f"{item.modules_completed}/{item.modules_total} modules",
            ]
            if item.modules_failed:
                bits.append(f"{item.modules_failed} failed")
            if item.modules_skipped:
                bits.append(f"{item.modules_skipped} skipped")
            if item.error_message:
                bits.append(item.error_message)
            st.write(f"- **{item.title or item.notebook_id}** · " + " · ".join(bits))
            if st.button(
                "Open",
                key=f"ax_batch_open_{item.notebook_id}",
            ):
                from transcribe.ui.navigation import (
                    notebook_has_published_analysis,
                    normalize_ui_mode,
                )
                from transcribe.ui.shell import sync_notebook_selector
                from transcribe.services.batch_notebooks import resolve_notebook_root

                try:
                    item_root = resolve_notebook_root(coord.corpus, item.notebook_id)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
                    continue
                st.session_state["root"] = str(item_root)
                sync_notebook_selector(str(item_root))
                if notebook_has_published_analysis(item_root):
                    st.session_state["ui_mode"] = normalize_ui_mode("Overview")
                else:
                    st.session_state["ui_mode"] = normalize_ui_mode("Reading")
                st.rerun()


def render_batch_analysis_launch(
    runtime: RuntimePaths,
    batch_coord: BatchAnalysisCoordinator,
    *,
    projects: ProjectService | None = None,
    project: Any | None = None,
) -> None:
    """Preset form + notebook selection for Analyse → Batch."""
    from transcribe.analysis.module_catalog import format_module_label
    from transcribe.analysis.llm_runtime import (
        is_unsuitable_text_model_name,
        suitable_text_model_names,
    )
    from transcribe.providers.ollama import OllamaVisionProvider, invalidate_discovery_cache
    from transcribe.ui.module_ui_groups import group_modules_for_ui

    if _PRESET_KEY not in st.session_state:
        st.session_state[_PRESET_KEY] = PRESET_LABELS["balanced"]

    preset_label = st.selectbox(
        "Preset",
        options=[PRESET_LABELS[p] for p in VALID_PRESETS],
        key=_PRESET_KEY,
        help=PRESET_HELP,
    )
    preset = label_to_preset(str(preset_label))
    custom_modules: list[str] = []
    if preset == "custom":
        suitable = suitable_module_ids()
        selected = st.multiselect(
            "Select modules",
            options=suitable,
            format_func=format_module_label,
            key="batch_analysis_custom_modules",
        )
        st.session_state[_CUSTOM_KEY] = list(selected)
        custom_modules = selected
    else:
        custom_modules = list(st.session_state.get(_CUSTOM_KEY) or [])

    resolved = resolve_analysis_preset(preset, custom_modules=custom_modules)
    qa_enabled = st.checkbox(
        "Include Ask notebook question",
        value=bool(st.session_state.get(_QA_ENABLE_KEY, False)),
        key="batch_analysis_qa_enable",
        help="Adds llm_custom_qa with the same question on every notebook.",
    )
    question_text: str | None = None
    if qa_enabled:
        question_text = st.text_area(
            "Question",
            value=st.session_state.get(_QA_TEXT_KEY, ""),
            key="batch_analysis_qa_text",
            placeholder="What themes recur across these pages?",
        )

    plan = compute_effective_modules(
        resolved, custom_qa_execution=bool(qa_enabled and (question_text or "").strip())
    )
    parts = [f"**{format_preset_label(preset)}** · {len(plan.module_ids)} modules"]
    if resolved.preset != "custom":
        parts.append(f"v{resolved.content_version}")
    st.caption(" · ".join(parts) + " · applied to each selected notebook")

    groups = group_modules_for_ui(plan.module_ids)
    with st.expander("Modules in this plan", expanded=False):
        for group_name, mids in groups:
            st.markdown(f"**{group_name}**")
            st.write(", ".join(format_module_label(m) for m in mids))

    needs_llm = plan.llm_count > 0
    text_model = ""
    if project is not None:
        text_model = project.settings.text_model_name or ""
    if needs_llm:
        st.info(
            "LLM modules need a text Ollama model configured on each notebook "
            "(Settings / This notebook Analyse). Missing models report unavailable_model."
        )
        if project is not None and projects is not None:
            with st.expander("LLM setup (open notebook)", expanded=not bool(text_model)):
                provider = OllamaVisionProvider(project.settings.base_url)
                refresh_models = st.button(
                    "Refresh models", key="batch_analysis_refresh_models"
                )
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
                    chosen = st.selectbox(
                        "Text model", options=names, index=idx, key="batch_ax_text_model"
                    )
                else:
                    chosen = st.text_input(
                        "Text model name", value="", key="batch_ax_text_model_manual"
                    )
                if st.button("Save text model", key="batch_analysis_save_text_model"):
                    settings = project.settings
                    settings.text_model_name = chosen
                    projects.save_settings(project, settings)
                    st.success(f"Text model set to `{chosen}`")
                    st.rerun()

    corpus = CorpusPaths.from_runtime(runtime)
    candidates = list_analysis_candidates(corpus)
    source_options = ["pending", "import_run", "pick"]
    queued_source = st.session_state.pop(ANALYSE_BATCH_SOURCE_KEY, None)
    if queued_source in source_options and "ax_batch_source" not in st.session_state:
        st.session_state["ax_batch_source"] = queued_source
    source = st.radio(
        "Notebooks",
        options=source_options,
        format_func=lambda s: {
            "pending": "Notebooks needing analysis",
            "import_run": "From an import run",
            "pick": "Pick notebooks",
        }[s],
        key="ax_batch_source",
        horizontal=True,
    )
    selected = []
    import_run_id: str | None = None
    if source == "pending":
        selected = select_needing_analysis(candidates)
        st.caption(
            f"{len(selected)} notebook(s) needing analysis "
            f"({sum(c.pages_with_text for c in selected)} page(s) with text)."
        )
    elif source == "import_run":
        runs = ImportRunStore(corpus).list_runs()
        queued_run = st.session_state.pop(ANALYSE_BATCH_IMPORT_RUN_KEY, None)
        labels = {r.import_run_id: f"{r.import_run_id} · {r.status}" for r in runs}
        run_ids = [r.import_run_id for r in runs]
        if queued_run in run_ids:
            st.session_state["ax_batch_import_run"] = queued_run
        if not run_ids:
            st.info("No import runs yet. Batch-import folders under Import → Batch.")
        else:
            chosen_run = st.selectbox(
                "Import run",
                options=run_ids,
                format_func=lambda rid: labels.get(rid, rid),
                key="ax_batch_import_run",
            )
            import_run_id = str(chosen_run) if chosen_run else None
            if import_run_id:
                try:
                    selected = select_from_import_run(
                        corpus,
                        import_run_id,
                        candidates,
                        purpose="analyse",
                    )
                    st.caption(
                        f"{len(selected)} committed notebook(s) · "
                        f"{sum(c.pages_with_text for c in selected)} with text."
                    )
                except (TranscribeError, ValidationError) as exc:
                    st.error(str(exc))
    else:
        queued_ids = st.session_state.pop(ANALYSE_BATCH_NOTEBOOK_IDS_KEY, None)
        options = [c.notebook_id for c in candidates]
        labels = {
            c.notebook_id: (
                f"{c.title} ({c.pages_with_text} with text · {c.analysis_aggregate})"
            )
            for c in candidates
        }
        default = [nid for nid in (queued_ids or []) if nid in options]
        if default and "ax_batch_pick" not in st.session_state:
            st.session_state["ax_batch_pick"] = default
        picked = st.multiselect(
            "Notebooks",
            options=options,
            format_func=lambda nid: labels.get(nid, nid),
            key="ax_batch_pick",
        )
        if picked:
            try:
                selected = select_by_ids(candidates, list(picked))
            except TranscribeError as exc:
                st.error(str(exc))

    recent = AnalysisBatchRunStore(corpus).list_runs()[:8]
    if recent:
        with st.expander("Recent batch analysis runs", expanded=False):
            for run in recent:
                ok = sum(1 for i in run.items if i.state == "completed")
                st.caption(
                    f"`{run.analysis_batch_id}` · {run.status} · "
                    f"{ok}/{len(run.items)} notebooks"
                )
                if run.status in {"pending", "running"} or any(
                    i.state in {"pending", "running"} for i in run.items
                ):
                    if st.button(
                        "Resume", key=f"batch_analysis_resume_{run.analysis_batch_id}"
                    ):
                        try:
                            batch_coord.start(run.analysis_batch_id)
                            st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                            st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                            st.rerun()
                        except (JobConflictError, TranscribeError) as exc:
                            st.error(str(exc))

    launch_ids = batch_module_order(list(expand_with_hard_parents(plan.module_ids)))
    if st.button(
        "Start batch analysis",
        type="primary",
        key="ax_batch_start",
        disabled=not launch_ids,
    ):
        if not selected:
            st.error("Select at least one notebook.")
        else:
            try:
                q = (question_text or "").strip() or None
                new_run = batch_coord.create_run(
                    selected,
                    module_ids=launch_ids,
                    question_text=q,
                    preset_label=format_preset_label(preset),
                    preset_key=resolved.preset,
                    preset_content_version=resolved.content_version,
                    preset_policy_fingerprint=resolved.policy_fingerprint,
                    import_run_id=import_run_id,
                    seed_project=projects,
                )
                batch_coord.start(new_run.analysis_batch_id)
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                st.rerun()
            except (JobConflictError, TranscribeError, ValidationError) as exc:
                st.error(str(exc))
