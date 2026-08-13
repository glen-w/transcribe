"""Streamlit UI for Transcribe.

JobCoordinator and AnalysisCoordinator are owned via st.cache_resource so
reruns do not drop live OCR / analysis jobs.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import streamlit as st

from transcribe.analysis.coordinator import AnalysisCoordinator, build_analysis_coordinator
from transcribe.analysis.llm_runtime import (
    is_unsuitable_text_model_name,
    suitable_text_model_names,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import JobConflictError, TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    invalidate_discovery_cache,
    is_local_machine_host,
    normalize_base_url,
)
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import ArchiveService, bump_archive_generation
from transcribe.services.export import ExportService
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.multipass import MultiPassCoordinator, MultiPassProgress
from transcribe.services.project import (
    ProjectService,
    allocate_notebook_root,
    open_project_paths,
)
from transcribe.ui.archive_views import render_archive, render_notebooks, render_search
from transcribe.ui.settings_interface import render_settings_page
from transcribe.ui.page_viewer import render_page_viewer
from transcribe.ui.run_analysis import render_run_analysis_form
from transcribe.ui.shell import (
    configure_streamlit_page,
    inject_global_styles,
    is_open_notebook_workflow,
    is_workflow_mode,
    normalize_ui_mode,
    render_brand,
    render_mode_nav,
    render_page_shell,
    set_ui_mode,
    sync_notebook_selector,
)


@st.cache_resource
def get_coordinator(project_root: str) -> JobCoordinator:
    _paths, _projects, coord, _ingest = build_coordinator(
        project_root,
        clock=SystemClock(),
        ids=UuidGenerator(),
        archive_runtime=build_runtime_paths(),
    )
    return coord


@st.cache_resource
def get_multipass_coordinator(project_root: str) -> MultiPassCoordinator:
    coord = get_coordinator(project_root)
    return MultiPassCoordinator(
        jobs=coord,
        projects=coord.projects,
        clock=coord.clock,
        ids=coord.ids,
    )


@st.cache_resource
def get_analysis_coordinator(project_root: str) -> AnalysisCoordinator:
    _paths, _projects, coord = build_analysis_coordinator(
        project_root,
        clock=SystemClock(),
        ids=UuidGenerator(),
    )
    return coord


@st.cache_resource
def get_archive(projects_dir: str, data_dir: str) -> ArchiveService:
    """Keep ArchiveService across Streamlit reruns so TTL / generation state sticks."""
    from transcribe.runtime_paths import RuntimePaths

    live = build_runtime_paths()
    runtime = RuntimePaths(
        repo_root=live.repo_root,
        data_dir=Path(data_dir),
        projects_dir=Path(projects_dir),
        inbox_dir=live.inbox_dir,
        export_dir=live.export_dir,
    )
    return ArchiveService(runtime)


def _services(project_root: str):
    paths = open_project_paths(Path(project_root))
    clock = SystemClock()
    ids = UuidGenerator()
    projects = ProjectService(paths, clock=clock, ids=ids)
    from transcribe.config.facade import get_config
    from transcribe.ingest import IngestService

    dpi = int(get_config().effective.ingest.render_dpi)
    declutter = bool(get_config().effective.ingest.visual_declutter_enabled)
    ingest = IngestService(
        paths,
        clock=clock,
        ids=ids,
        default_dpi=dpi,
        visual_declutter_enabled=declutter,
    )
    return paths, projects, ingest


def _render_job_progress(progress: JobProgress) -> None:
    st.write(
        f"Job: **{progress.status}** — completed {progress.completed}/"
        f"{progress.total} (failed {progress.failed}, skipped {progress.skipped})"
    )
    if progress.current_page_ids:
        st.caption("Current page(s): " + ", ".join(p[:8] for p in progress.current_page_ids))
    if progress.message:
        st.caption(progress.message)
    if progress.circuit_open:
        st.warning(
            "This model hit repeated Ollama timeouts; remaining pages for this "
            "model were skipped."
        )
    done = progress.completed + progress.failed
    if progress.total > 0 and progress.status in {
        "running",
        "completed",
        "cancelled",
        "failed",
    }:
        st.progress(min(1.0, done / progress.total))
    if progress.status == "running":
        st.info(
            "OCR is running in the background. Progress also prints in the "
            "Streamlit terminal as `[transcribe] …` lines. The first page can "
            "take several minutes while Ollama loads the vision model."
        )


def _render_multipass_progress(
    multi: MultiPassProgress, job: JobProgress
) -> None:
    st.write(
        f"Compare: **{multi.status}** — {multi.phase or 'starting'}"
        + (
            f" · model {multi.model_index}/{multi.model_total}"
            if multi.model_total
            else ""
        )
    )
    if multi.message:
        st.caption(multi.message)
    if multi.phase == "vision" and job.status in {
        "running",
        "completed",
        "cancelled",
        "failed",
    }:
        _render_job_progress(job)
    elif multi.phase == "rank_composite":
        st.caption(
            f"Ranked {multi.pages_ranked} · composite {multi.pages_composite}"
        )
    if multi.status == "running":
        st.info(
            "Compare is running in the background. Stop after current page "
            "cancels remaining pages of this model and remaining models."
        )


def _failed_page_ids(projects: ProjectService, project) -> list[str]:
    failed: list[str] = []
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        if result is not None and result.status == "failed":
            failed.append(page.page_id)
    return failed


def _render_transcribe_complete_actions(
    *,
    projects: ProjectService,
    project,
    coord: JobCoordinator,
    progress: JobProgress,
) -> None:
    from transcribe.ui.components.action_links import render_action_link

    st.markdown("#### Next")
    failed_ids = _failed_page_ids(projects, project)
    cols = st.columns(4, gap="small")
    with cols[0]:
        if render_action_link(
            "View",
            key="tx_done_view",
            icon=":material/menu_book:",
            help="Open this notebook on the View page.",
        ):
            set_ui_mode("View")
    with cols[1]:
        if render_action_link(
            "Review",
            key="tx_done_review",
            icon=":material/rate_review:",
            help="Browse and edit transcribed pages.",
        ):
            set_ui_mode("Review")
    with cols[2]:
        if render_action_link(
            "Analyse",
            key="tx_done_analyse",
            icon=":material/analytics:",
            help="Open Analyse for this notebook.",
        ):
            set_ui_mode("Analyse")
    with cols[3]:
        if render_action_link(
            "Retry failed",
            key="tx_done_retry",
            icon=":material/replay:",
            help="Re-run OCR on pages whose last attempt failed.",
            disabled=not failed_ids,
        ):
            try:
                coord.start(page_ids=failed_ids, force=False)
                st.session_state["_job_was_running"] = True
                st.session_state["_transcribe_post_kind"] = "job"
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))
    if failed_ids:
        st.caption(f"{len(failed_ids)} failed page(s) can be retried.")
    elif progress.failed:
        st.caption("Failed count was reported, but no failed pages remain on disk.")
    if render_action_link(
        "Change settings",
        key="tx_done_settings",
        icon=":material/settings:",
        help="Return to model and OCR settings for another run.",
    ):
        st.session_state.pop("_transcribe_post_job_id", None)
        st.session_state.pop("_transcribe_post_kind", None)
        st.rerun()


def _render_workflow(runtime, root: str, *, section: str = "Import") -> None:
    section = normalize_ui_mode(section)
    try:
        paths, projects, ingest = _services(root)
        project = projects.load(reconcile=True)
    except TranscribeError as exc:
        st.info("Select or create a notebook to begin.")
        st.caption(str(exc))
        return

    if (
        section == "Review"
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
    ):
        from transcribe.ui.action_menus.nav import viewer_page_ids

        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=st.session_state.get("view_page_ids")
            or viewer_page_ids(project),
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label="Back to Review",
        )
        return

    if section == "Analyse":
        st.caption(f"Project: `{paths.root}`")
        from transcribe.ui.run_analysis import analysis_run_in_progress
        from transcribe.ui.run_detection import render_detection_workspace

        focus_detect = bool(st.session_state.pop("analyse_focus_detect", False))
        analysis_coord = get_analysis_coordinator(str(paths.root))
        analyse_tabs = st.tabs(["Run Analysis", "Published results", "Detect"])
        with analyse_tabs[0]:
            running = render_run_analysis_form(
                projects=projects, project=project, coord=analysis_coord
            )
        with analyse_tabs[1]:
            if running or analysis_run_in_progress(analysis_coord):
                st.info("Published results available when the current run finishes.")
            else:
                _render_analysis_result_tabs(runtime, paths, projects, project)
        with analyse_tabs[2]:
            render_detection_workspace(
                projects=projects, project_root=str(paths.root)
            )
        if focus_detect:
            st.info("Opened Detect from notebook actions.")
        return

    st.caption(f"Project: `{paths.root}`")

    if section == "Export":
        _render_export_panel(runtime, paths, projects, project, root)
        return

    if section == "Import":
        flash = st.session_state.pop("import_flash", None)
        if flash:
            st.success(flash)
        for err in st.session_state.pop("import_errors", []) or []:
            st.error(err)

        uploaded = st.file_uploader(
            "JPEG / PNG / PDF",
            type=["jpg", "jpeg", "png", "pdf"],
            accept_multiple_files=True,
        )
        from transcribe.config.facade import get_config

        dpi = int(get_config().effective.ingest.render_dpi)
        declutter = bool(get_config().effective.ingest.visual_declutter_enabled)
        st.caption(
            f"PDF render DPI: **{dpi}** · Visual declutter: "
            f"**{'on' if declutter else 'off'}** "
            "(Settings → Configuration)"
        )
        if st.button("Import files") and uploaded:
            total = len(uploaded)
            bar = st.progress(0.0, text=f"Importing 0/{total}")
            status = st.empty()
            ok = 0
            errors: list[str] = []
            for i, f in enumerate(uploaded):
                status.caption(f"Importing `{f.name}`…")
                try:
                    project = ingest.import_bytes(
                        f.name, f.getvalue(), render_dpi=dpi
                    )
                    bump_archive_generation(runtime)
                    ok += 1
                except TranscribeError as exc:
                    errors.append(f"{f.name}: {exc}")
                done = i + 1
                bar.progress(
                    min(1.0, done / total),
                    text=f"Importing {done}/{total}",
                )
            if ok:
                st.session_state["import_flash"] = (
                    f"Imported {ok} file{'s' if ok != 1 else ''}"
                    + (f" ({len(errors)} failed)" if errors else "")
                )
            if errors:
                st.session_state["import_errors"] = errors
            st.rerun()
        st.write(f"Pages in notebook: **{len(project.pages)}**")
        title_key = f"import_notebook_title__{project.id}"
        if title_key not in st.session_state:
            st.session_state[title_key] = project.title or ""
        title_in = st.text_input(
            "Notebook name",
            key=title_key,
            help="Display title for this notebook. The notebook folder path is unchanged.",
        )
        if st.button("Save notebook name"):
            cleaned = title_in.strip()
            if not cleaned:
                st.error("Notebook name cannot be empty.")
            else:
                project = projects.update_notebook_metadata(title=cleaned)
                bump_archive_generation(runtime)
                st.success("Notebook name saved")
        tags_in = st.text_input(
            "Notebook tags (comma-separated)", value=", ".join(project.tags)
        )
        if st.button("Save notebook tags"):
            project = projects.update_notebook_metadata(
                tags=[t for t in tags_in.split(",")]
            )
            bump_archive_generation(runtime)
            st.success("Tags saved")
        return

    if section == "Review":
        if not project.pages:
            st.info("No pages yet.")
        else:
            from transcribe.ui.action_menus.nav import viewer_page_ids

            page_ids = viewer_page_ids(project)
            default_id = st.session_state.get("view_page_id") or page_ids[0]
            if default_id not in page_ids:
                default_id = page_ids[0]
            # Rebuild nav for the open notebook so stale Archive/Search entries
            # (e.g. a deleted notebook) cannot override Review.
            view_entries = [
                {"page_id": pid, "project_root": str(paths.root)} for pid in page_ids
            ]
            st.session_state["view_page_id"] = default_id
            st.session_state["view_page_ids"] = page_ids
            st.session_state["view_entries"] = view_entries
            render_page_viewer(
                paths=paths,
                projects=projects,
                project=project,
                page_id=default_id,
                page_ids=page_ids,
                view_entries=view_entries,
                highlight_query="",
                show_back=False,
            )
        return

    # Transcribe: configure Ollama and run OCR
    coord = get_coordinator(str(paths.root))
    multi = get_multipass_coordinator(str(paths.root))
    live = coord.get_progress()
    multi_live = multi.get_progress()
    is_running = live.status == "running" or multi_live.status == "running"
    was_running = st.session_state.get("_job_was_running", False)
    st.session_state["_job_was_running"] = is_running
    post_job_id = st.session_state.get("_transcribe_post_job_id")
    post_kind = st.session_state.get("_transcribe_post_kind", "job")
    show_post = False
    if post_kind == "multipass":
        show_post = (
            bool(post_job_id)
            and multi_live.pass_id == post_job_id
            and multi_live.status in {"completed", "cancelled", "failed"}
        )
    else:
        show_post = (
            bool(post_job_id)
            and live.job_id == post_job_id
            and live.status in {"completed", "cancelled", "failed"}
        )

    if is_running:
        poll = timedelta(seconds=2) if is_running or was_running else None

        @st.fragment(run_every=poll)
        def job_status_panel() -> None:
            progress = coord.get_progress()
            mp = multi.get_progress()
            if mp.status == "running":
                _render_multipass_progress(mp, progress)
            else:
                _render_job_progress(progress)
            still_running = (
                progress.status == "running" or mp.status == "running"
            )
            if st.session_state.get("_job_was_running") and not still_running:
                st.session_state["_job_was_running"] = False
                if mp.status in {"completed", "cancelled", "failed"} and mp.pass_id:
                    st.session_state["_transcribe_post_job_id"] = mp.pass_id
                    st.session_state["_transcribe_post_kind"] = "multipass"
                else:
                    st.session_state["_transcribe_post_job_id"] = progress.job_id
                    st.session_state["_transcribe_post_kind"] = "job"
                bump_archive_generation(runtime)
                st.rerun()

        job_status_panel()
        if st.button("Stop after current page", key="transcribe_stop_running"):
            multi.request_cancel()
            coord.request_cancel()
            st.info("Stopping after current page…")
        return

    if show_post:
        if post_kind == "multipass":
            _render_multipass_progress(multi_live, live)
        else:
            _render_job_progress(live)
        _render_transcribe_complete_actions(
            projects=projects,
            project=project,
            coord=coord,
            progress=live,
        )
        return

    base_url = st.text_input("Ollama base URL", value=project.settings.base_url)
    try:
        normalized = normalize_base_url(base_url)
        remote = not is_local_machine_host(normalized)
    except Exception as exc:
        st.error(str(exc))
        normalized = project.settings.base_url
        remote = False

    # Phase 6 #9 — privacy ack stays visible / confirm-gated (never buried alone).
    allow_remote = False
    if remote:
        st.warning(
            "This Ollama host is not loopback. Page images will leave this machine."
        )
        allow_remote = st.checkbox("I understand and want to use this remote host")

    provider = OllamaVisionProvider(normalized)
    _, c2 = st.columns([1, 1])
    refresh = c2.button("Refresh Models")
    if refresh:
        invalidate_discovery_cache(normalized)
    discovery = provider.list_vision_models(refresh=refresh)
    if discovery.error:
        st.caption(f"Discovery: {discovery.error}")
    names = [m.name for m in discovery.models]
    all_discovery = provider.list_models(refresh=False)
    unknown = [m.name for m in all_discovery.models if not m.capability_known]
    from transcribe.services.ocr_preference_stats import (
        preference_hint_for_model,
        rollup_preference_stats,
    )

    pref_stats = rollup_preference_stats()

    def _model_label(name: str) -> str:
        hint = preference_hint_for_model(name, stats=pref_stats)
        return f"{name} — {hint}" if hint else name

    model = st.selectbox(
        "Vision model",
        options=names or [project.settings.model_name or ""],
        index=0 if names else 0,
        format_func=_model_label,
    )
    from transcribe.ui.components.model_info import (
        render_model_information,
        warn_if_first_compare_model_is_general_vlm,
    )

    render_model_information(
        discovery.models,
        selected=model,
        role="vision",
        key="tx_vision_model_info",
    )
    text_model_options = suitable_text_model_names(all_discovery.models)
    if (
        project.settings.text_model_name
        and is_unsuitable_text_model_name(project.settings.text_model_name)
    ):
        st.warning(
            f"Saved text model `{project.settings.text_model_name}` is "
            "vision/embedding — choose a text model below."
        )
    if not text_model_options:
        st.caption("No suitable text models discovered from Ollama.")
        text_model_options = [""]
    text_model = st.selectbox(
        "Text analysis model",
        options=text_model_options,
        index=(
            text_model_options.index(project.settings.text_model_name)
            if project.settings.text_model_name in text_model_options
            else 0
        ),
        help="Required for LLM analysis modules. Vision/embedding models are filtered out.",
    )
    render_model_information(
        all_discovery.models,
        selected=text_model,
        role="text",
        key="tx_text_model_info",
    )

    # Primary path: optional one-line cleanup toggle (#9).
    cleanup_enabled = st.checkbox(
        "Clean OCR with text model",
        value=bool(project.settings.cleanup_enabled),
        help=(
            "Optional second-pass text model after vision OCR. "
            "Adds one Ollama call per page; failures keep raw OCR."
        ),
    )

    # Advanced: power controls collapsed off the primary path.
    with st.expander("Advanced", expanded=False):
        if unknown:
            st.caption("Models with unknown capabilities")
            st.write(", ".join(unknown))
        from transcribe.prompt_engine.definition import PromptFamily
        from transcribe.prompt_engine.hub import list_catalogue

        ocr_entries = list_catalogue(family=PromptFamily.OCR)
        ocr_ids = [e.definition.prompt_id for e in ocr_entries] or [
            "faithful_markdown",
            "faithful_text",
        ]
        default_prompt = project.settings.prompt_id or "faithful_markdown"
        prompt_index = ocr_ids.index(default_prompt) if default_prompt in ocr_ids else 0
        prompt_id = st.selectbox("Prompt", ocr_ids, index=prompt_index)
        custom = st.text_area(
            "Custom prompt override (optional)",
            value=project.settings.custom_prompt or "",
        )
        preprocess = st.selectbox("Preprocess", ["none", "gentle_contrast"])
        workers = st.selectbox("Workers", [1, 2], index=0)
        force = st.checkbox("Force re-run (ignore matching fingerprints)")
        cleanup_mode_labels = {
            "strip_leak": "Strip prompt leakage only",
            "sanitize_light": "Strip leakage + light sanitize",
            "rewrite": "Broader rewrite / normalize",
        }
        cleanup_mode = st.selectbox(
            "Cleanup mode",
            options=list(cleanup_mode_labels.keys()),
            format_func=lambda m: cleanup_mode_labels[m],
            index=(
                list(cleanup_mode_labels.keys()).index(project.settings.cleanup_mode)
                if project.settings.cleanup_mode in cleanup_mode_labels
                else 0
            ),
            disabled=not cleanup_enabled,
        )
        cleanup_model_options = text_model_options
        cleanup_model = st.selectbox(
            "Cleanup model",
            options=cleanup_model_options,
            index=(
                cleanup_model_options.index(project.settings.cleanup_model_name)
                if project.settings.cleanup_model_name in cleanup_model_options
                else (
                    cleanup_model_options.index(project.settings.text_model_name)
                    if project.settings.text_model_name in cleanup_model_options
                    else 0
                )
            ),
            disabled=not cleanup_enabled,
            help=(
                "Text model for cleanup (vision/embedding filtered out). "
                "Falls back to the text analysis model if unset."
            ),
        )
        if cleanup_enabled and cleanup_model:
            render_model_information(
                all_discovery.models,
                selected=cleanup_model,
                role="text",
                key="tx_cleanup_model_info",
            )
        from transcribe.domain.models import DEFAULT_PREFER_MODE, PREFER_MODES

        prefer_labels = {
            "prefer_is_promote": "Prefer = promote",
            "prefer_only": "Prefer only (no activate)",
            "prefer_promote_with_edit_gate": "Prefer + promote with edit gate",
        }
        prefer_mode = st.selectbox(
            "Prefer mode",
            options=list(prefer_labels.keys()),
            format_func=lambda m: prefer_labels[m],
            index=(
                list(prefer_labels.keys()).index(project.settings.prefer_mode)
                if project.settings.prefer_mode in prefer_labels
                else 0
            ),
        )
        auto_activate_composite = st.checkbox(
            "Auto-activate composite after multipass",
            value=bool(project.settings.auto_activate_composite),
        )
        st.caption(
            "Unverified model identity may increase cost or surprise quality — "
            "prefer discovered vision-capable tags when listed."
        )

    if st.button("Save settings"):
        settings = project.settings
        settings.base_url = normalized
        settings.model_name = model
        settings.text_model_name = text_model
        settings.prompt_id = prompt_id
        settings.custom_prompt = custom.strip() or None
        settings.preprocess_profile = preprocess
        settings.max_workers = int(workers)
        settings.allow_non_loopback = allow_remote
        settings.generation_options.temperature = 0.0
        settings.cleanup_enabled = bool(cleanup_enabled)
        settings.cleanup_mode = cleanup_mode
        if cleanup_enabled:
            settings.cleanup_model_name = cleanup_model
        settings.prefer_mode = prefer_mode
        settings.auto_activate_composite = bool(auto_activate_composite)
        project = projects.save_settings(project, settings)
        coord.provider = OllamaVisionProvider(normalized)
        st.success("Settings saved")

    if st.button("Start transcription"):
        if remote and not allow_remote:
            st.error("Enable the remote-host acknowledgement first.")
        else:
            try:
                settings = project.settings
                settings.base_url = normalized
                settings.model_name = model
                settings.text_model_name = text_model
                settings.prompt_id = prompt_id
                settings.custom_prompt = custom.strip() or None
                settings.preprocess_profile = preprocess
                settings.max_workers = int(workers)
                settings.allow_non_loopback = allow_remote
                settings.cleanup_enabled = bool(cleanup_enabled)
                settings.cleanup_mode = cleanup_mode
                if cleanup_enabled:
                    settings.cleanup_model_name = cleanup_model
                settings.prefer_mode = prefer_mode
                settings.auto_activate_composite = bool(auto_activate_composite)
                project = projects.save_settings(project, settings)
                coord.provider = OllamaVisionProvider(normalized)
                coord.start(force=force)
                st.session_state["_job_was_running"] = True
                st.session_state["_transcribe_post_kind"] = "job"
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Compare models")
    st.caption(
        "Run two or more vision models on this notebook, then rank and "
        "optionally produce a composite candidate with the text model. "
        "Vision phases skip post-OCR cleanup unless you opt in below."
    )
    multi_models = st.multiselect(
        "Vision models for multipass",
        options=names,
        default=[],
        format_func=_model_label,
        help="Select at least two models. Order matters: first model runs fully.",
    )
    if multi_models:
        render_model_information(
            discovery.models,
            selected=multi_models,
            role="vision",
            key="tx_compare_model_info",
        )
        warn_if_first_compare_model_is_general_vlm(multi_models)
    compare_cleanup = st.checkbox(
        "Clean OCR during compare",
        value=False,
        help=(
            "Off by default so compare is a raw-model comparison. "
            "Cleanup still uses the cleanup/text model when enabled."
        ),
    )
    no_auto_comp = st.checkbox(
        "Do not auto-activate composite",
        value=not bool(project.settings.auto_activate_composite),
    )
    if st.button("Start multipass compare"):
        if remote and not allow_remote:
            st.error("Enable the remote-host acknowledgement first.")
        elif len(multi_models) < 2:
            st.error("Select at least two vision models.")
        else:
            try:
                settings = project.settings
                settings.base_url = normalized
                settings.text_model_name = text_model
                settings.allow_non_loopback = allow_remote
                if compare_cleanup:
                    settings.cleanup_model_name = cleanup_model or text_model
                elif text_model and not settings.cleanup_model_name:
                    settings.cleanup_model_name = text_model
                project = projects.save_settings(project, settings)
                coord.provider = OllamaVisionProvider(normalized)
                multi.start(
                    model_names=list(multi_models),
                    force=force,
                    auto_activate_composite=not no_auto_comp,
                    cleanup_enabled=bool(compare_cleanup),
                )
                st.session_state["_job_was_running"] = True
                st.session_state["_transcribe_post_kind"] = "multipass"
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))


def _render_export_panel(runtime, paths, projects, project, root: str) -> None:
    from transcribe.ui.export_panel import render_export_panel

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    render_export_panel(runtime, paths, projects, project, root, archive=archive)


def _render_analysis_result_tabs(runtime, paths, projects, project) -> None:
    from transcribe.analysis.health import derive_analysis_health, scope_analysis_health
    from transcribe.analysis.modules import (
        THROUGH_OVERVIEW,
        THROUGH_THEMES,
        get_registered_modules,
    )
    from transcribe.analysis.runner import AnalysisRunner, module_freshness
    from transcribe.analysis.storage import AnalysisStorage
    from transcribe.ports import SystemClock, UuidGenerator
    from transcribe.ui.analysis_health_view import render_status_strip
    from transcribe.ui.analysis_product_views import (
        render_ask_product,
        render_moments_product,
        render_mood_product,
        render_overview_product,
        render_summaries_product,
        render_themes_product,
    )

    runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
    storage = AnalysisStorage(paths)
    content_revision = projects.content_revision(project)

    overview_ids = list(get_registered_modules(through=THROUGH_OVERVIEW).keys())
    theme_ids = [
        "keyphrases",
        "topic_modeling",
        "semantic_similarity",
        "topic_shift",
        "bertopic",
    ]
    mood_ids = [
        "sentiment",
        "emotion",
        "contextual_emotion",
        "fine_grained_emotion",
        "affect_tension",
        "epistemic_markers",
    ]
    synth_ids = [
        "topic_modeling",
        "highlights",
        "summary",
        "insights",
        "llm_summary",
        "llm_action_items",
        "narrative_summary",
    ]
    batch_ids = list(
        dict.fromkeys(overview_ids + theme_ids + mood_ids + ["moments"] + synth_ids)
    )
    analysis_coord = get_analysis_coordinator(str(paths.root))
    active_run_status = "running" if analysis_coord.is_running() else None
    if active_run_status is None:
        # Surface interrupted reopen state on the shared strip when present.
        try:
            runs_dir = storage.runs_dir()
            if runs_dir.is_dir():
                for path in sorted(runs_dir.glob("*.json"), reverse=True):
                    rec = storage.read_run_record(path.stem)
                    if rec and rec.get("status") == "interrupted":
                        active_run_status = "interrupted"
                        break
        except Exception:  # noqa: BLE001 — strip is best-effort
            pass
    batch_health = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=batch_ids,
        content_revision=content_revision,
        active_run_status=active_run_status,
    )
    overview_health = scope_analysis_health(batch_health, overview_ids)
    themes_health = scope_analysis_health(batch_health, theme_ids)
    mood_health = scope_analysis_health(batch_health, mood_ids)
    moments_health = scope_analysis_health(batch_health, ["moments"])
    summaries_health = scope_analysis_health(batch_health, synth_ids)

    # Phase 6 #8 — sole default freshness/health answer across batch tabs.
    render_status_strip(batch_health)

    (
        tab_overview,
        tab_themes,
        tab_mood,
        tab_moments,
        tab_places,
        tab_summaries,
        tab_ask,
    ) = st.tabs(
        [
            "Overview",
            "Themes",
            "Mood & tone",
            "Moments",
            "People & places",
            "Summaries",
            "Ask notebook",
        ]
    )

    with tab_overview:

        def _page_metrics() -> None:
            from transcribe.ui.page_metrics_view import render_overview_page_metrics

            render_overview_page_metrics(projects, project)

        render_overview_product(
            overview_health, overview_ids, render_page_metrics=_page_metrics
        )

    with tab_themes:
        themes = get_registered_modules(through=THROUGH_THEMES)
        assert set(theme_ids).issubset(set(themes))
        render_themes_product(themes_health, theme_ids)

    with tab_mood:
        render_mood_product(mood_health, mood_ids)

    with tab_moments:
        def _jump_to_page(page_id: str) -> None:
            st.session_state["review_page_id"] = page_id
            st.session_state["nav_section"] = "Review"
            st.rerun()

        render_moments_product(moments_health, on_jump=_jump_to_page)

    with tab_places:
        from transcribe.ui.places_map import render_notebook_places_tab

        ner_mh = batch_health.modules.get("ner")
        render_notebook_places_tab(
            project_root=paths.root,
            runtime=runtime,
            ner_health=ner_mh,
        )

    with tab_summaries:
        render_summaries_product(summaries_health, synth_ids)

    with tab_ask:
        st.caption("Ask notebook is ad-hoc and does not update batch analysis health.")
        render_ask_product(runner=runner)
        question = st.session_state.get("ask_notebook_question") or ""
        rm = module_freshness(
            runner,
            storage,
            ["llm_custom_qa"],
            question_text=question.strip() or None,
        )[0]
        if rm.get("envelope"):
            st.divider()
            if rm.get("status") == "stale":
                st.caption(
                    "Last Ask answer is out of date — ask again to refresh."
                )
            else:
                st.caption("Last Ask answer")
                payload = (rm["envelope"] or {}).get("payload") or {}
                if payload.get("answer"):
                    st.markdown(payload["answer"])
                with st.expander("Advanced · last Ask"):
                    st.json(payload)



_PAGE_SHELL: dict[str, tuple[str, str]] = {
    "Archive": (
        "Archive",
        "Browse notebooks by timeline, tags, and recent activity.",
    ),
    "View": (
        "View",
        "Open a notebook volume and jump into its pages.",
    ),
    "Search": (
        "Search",
        "Find text across transcribed notebook pages.",
    ),
    "Places": (
        "Places",
        "Map places mentioned across all notebooks (from published NER).",
    ),
    "Inbox": (
        "Inbox",
        "Bulk-import a folder of scans and review what committed, skipped, or failed.",
    ),
    "New notebook": (
        "New notebook",
        "Create a notebook, then import pages and run OCR.",
    ),
    "Import": (
        "Import",
        "Add JPEG, PNG, or PDF pages to this notebook.",
    ),
    "Transcribe": (
        "Transcribe",
        "Configure Ollama and run OCR on notebook pages.",
    ),
    "Review": (
        "Review",
        "Browse and edit transcribed pages.",
    ),
    "Analyse": (
        "Analyse",
        "Run notebook analysis from Quick / Balanced / Thorough presets.",
    ),
    "Export": (
        "Export",
        "Export notebook JSON, Markdown, plain text, HTML, EPUB, and PDF.",
    ),
    "Settings": (
        "Settings",
        "Workspace knobs: analysis presets, models, profiles, and interface menus.",
    ),
}


def _notebook_dropdown_options(archive: ArchiveService) -> list[tuple[str, str]]:
    """``(root_path, title)`` pairs for the sidebar notebook selectbox."""
    notebooks = archive.list_notebooks(order="newest")
    out: list[tuple[str, str]] = []
    for nb in notebooks:
        try:
            root = str(nb.root.expanduser().resolve())
        except OSError:
            root = str(nb.root)
        out.append((root, nb.title or nb.root.name))
    return out


def _render_new_notebook(runtime, archive: ArchiveService) -> None:
    st.caption(
        "Creates a new notebook folder under the workspace notebooks directory, "
        "then opens Import."
    )
    if "new_notebook_title" not in st.session_state:
        st.session_state["new_notebook_title"] = "Untitled notebook"
    title_in = st.text_input(
        "Notebook name",
        key="new_notebook_title",
        help="Display title. A folder name is derived automatically.",
    )
    if st.button("Create notebook", type="primary", key="new_notebook_create"):
        cleaned = (title_in or "").strip() or "Untitled notebook"
        try:
            root = allocate_notebook_root(runtime.projects_dir, cleaned)
            paths = open_project_paths(root)
            ProjectService(
                paths,
                clock=SystemClock(),
                ids=UuidGenerator(),
                corpus_paths=CorpusPaths.from_runtime(runtime),
            ).create(title=cleaned)
            bump_archive_generation(runtime)
            archive.ensure_index()
            st.cache_resource.clear()
            st.session_state["root"] = str(paths.root)
            sync_notebook_selector(str(paths.root))
            st.session_state.pop("new_notebook_title", None)
            st.toast(f"Created “{cleaned}”")
            set_ui_mode("Import")
        except TranscribeError as exc:
            st.error(str(exc))


def main() -> None:
    configure_streamlit_page()
    inject_global_styles()

    runtime = build_runtime_paths()
    runtime.ensure_layout()

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    archive.ensure_index()
    notebook_options = _notebook_dropdown_options(archive)

    mode = normalize_ui_mode(st.session_state.get("ui_mode"))
    st.session_state["ui_mode"] = mode

    with st.sidebar:
        render_brand()
        mode = render_mode_nav(mode, notebook_options=notebook_options)

    root = st.session_state.get("root") or ""

    # Page viewer overlay when navigated from Archive/Search/View.
    if (
        not is_workflow_mode(mode)
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
        and root
    ):
        try:
            render_page_viewer(
                page_id=st.session_state["view_page_id"],
                page_ids=st.session_state.get("view_page_ids"),
                view_entries=st.session_state.get("view_entries"),
                highlight_query=st.session_state.get("view_highlight", ""),
                show_back=False,
            )
            return
        except TranscribeError as exc:
            st.error(str(exc))
            st.session_state["show_page_viewer"] = False

    title, desc = _PAGE_SHELL[mode]
    # Analyse owns its own page shell inside Run Analysis.
    if mode != "Analyse":
        render_page_shell(title, desc)

    if mode == "Archive":
        render_archive(runtime, archive)
    elif mode == "View":
        render_notebooks(runtime, archive)
    elif mode == "Search":
        render_search(runtime, archive)
    elif mode == "Places":
        from transcribe.ui.places_map import render_corpus_places_page

        render_corpus_places_page(runtime)
    elif mode == "Inbox":
        from transcribe.ui.import_inbox import render_import_inbox

        render_import_inbox(runtime)
    elif mode == "Settings":
        render_settings_page()
    elif mode == "New notebook":
        _render_new_notebook(runtime, archive)
    elif is_open_notebook_workflow(mode):
        if not root:
            st.info("Select a notebook above, or create one under Workflow → New notebook.")
            return
        _render_workflow(runtime, root, section=mode)


def path_read(path: Path) -> bytes:
    return Path(path).read_bytes()


def cli_main() -> None:
    """Console entry: ``transcribe-ui`` → Streamlit on port 8510 by default."""
    app_path = str(Path(__file__).resolve())
    port = os.getenv("TRANSCRIBE_PORT", "8510")
    address = os.getenv("TRANSCRIBE_HOST", "127.0.0.1")
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        f"--server.port={port}",
        f"--server.address={address}",
        "--browser.gatherUsageStats=false",
    ]
    from streamlit.web import cli as stcli

    raise SystemExit(stcli.main())


if __name__ == "__main__":
    main()
