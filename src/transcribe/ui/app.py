"""Streamlit UI for Transcribe.

JobCoordinator is owned via st.cache_resource so reruns do not drop live jobs.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import streamlit as st

from transcribe.analysis.llm_runtime import (
    is_unsuitable_text_model_name,
    suitable_text_model_names,
)
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
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.archive_views import render_archive, render_notebooks, render_search
from transcribe.ui.settings_interface import render_settings_page
from transcribe.ui.page_viewer import render_page_viewer
from transcribe.ui.run_analysis import render_run_analysis_form
from transcribe.ui.shell import (
    configure_streamlit_page,
    inject_global_styles,
    is_workflow_mode,
    normalize_ui_mode,
    render_brand,
    render_mode_nav,
    render_nav_section,
    render_page_shell,
    set_ui_mode,
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
        st.rerun()


def _render_workflow(runtime, root: str, *, section: str = "Import") -> None:
    section = normalize_ui_mode(section)
    try:
        paths, projects, ingest = _services(root)
        project = projects.load(reconcile=True)
    except TranscribeError as exc:
        st.info("Create or open a project directory to begin.")
        st.caption(str(exc))
        return

    if (
        section == "Review"
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
    ):
        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=st.session_state.get("view_page_ids")
            or [p.page_id for p in project.pages],
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label="Back to Review",
        )
        return

    if section == "Analyse":
        st.caption(f"Project: `{paths.root}`")
        focus_detect = bool(st.session_state.pop("analyse_focus_detect", False))
        analyse_tabs = st.tabs(["Run Analysis", "Published results", "Detect"])
        with analyse_tabs[0]:
            render_run_analysis_form(projects=projects, project=project)
        with analyse_tabs[1]:
            _render_analysis_result_tabs(paths, projects, project)
        with analyse_tabs[2]:
            from transcribe.ui.run_detection import render_detection_workspace

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
        st.write(f"Pages in project: **{len(project.pages)}**")
        title_key = f"import_notebook_title__{project.id}"
        if title_key not in st.session_state:
            st.session_state[title_key] = project.title or ""
        title_in = st.text_input(
            "Notebook name",
            key=title_key,
            help="Display title for this notebook. The project folder path is unchanged.",
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
            page_ids = [p.page_id for p in project.pages]
            default_id = st.session_state.get("view_page_id") or page_ids[0]
            if default_id not in page_ids:
                default_id = page_ids[0]
            st.session_state["view_page_id"] = default_id
            st.session_state["view_page_ids"] = page_ids
            render_page_viewer(
                paths=paths,
                projects=projects,
                project=project,
                page_id=default_id,
                page_ids=page_ids,
                highlight_query="",
                show_back=False,
            )
        return

    # Transcribe: configure Ollama and run OCR
    coord = get_coordinator(str(paths.root))
    live = coord.get_progress()
    was_running = st.session_state.get("_job_was_running", False)
    st.session_state["_job_was_running"] = live.status == "running"
    is_running = live.status == "running"
    post_job_id = st.session_state.get("_transcribe_post_job_id")
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
            _render_job_progress(progress)
            if (
                st.session_state.get("_job_was_running")
                and progress.status != "running"
            ):
                st.session_state["_job_was_running"] = False
                st.session_state["_transcribe_post_job_id"] = progress.job_id
                bump_archive_generation(runtime)
                st.rerun()

        job_status_panel()
        if st.button("Stop after current page", key="transcribe_stop_running"):
            coord.request_cancel()
            st.info("Stopping after current page…")
        return

    if show_post:
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
    model = st.selectbox(
        "Vision model",
        options=names or [project.settings.model_name or ""],
        index=0 if names else 0,
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
    if unknown:
        with st.expander("Models with unknown capabilities"):
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
        "Custom prompt override (optional)", value=project.settings.custom_prompt or ""
    )
    preprocess = st.selectbox("Preprocess", ["none", "gentle_contrast"])
    workers = st.selectbox("Workers", [1, 2], index=0)
    force = st.checkbox("Force re-run (ignore matching fingerprints)")
    cleanup_enabled = st.checkbox(
        "Clean OCR with text model",
        value=bool(project.settings.cleanup_enabled),
        help=(
            "Optional second-pass text model after vision OCR. "
            "Adds one Ollama call per page; failures keep raw OCR."
        ),
    )
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
                project = projects.save_settings(project, settings)
                coord.provider = OllamaVisionProvider(normalized)
                coord.start(force=force)
                st.session_state["_job_was_running"] = True
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))


def _render_export_panel(runtime, paths, projects, project, root: str) -> None:
    export_dest = st.text_input(
        "Export directory",
        value=str(runtime.export_dir / Path(root).name),
    )
    if st.button("Export"):
        dest = Path(export_dest) if export_dest.strip() else None
        written = ExportService(paths, projects).export_all(project, dest)
        for kind, path in written.items():
            st.write(f"**{kind}:** `{path}`")
        st.download_button(
            "Download notebook JSON",
            data=path_read(written["notebook"]),
            file_name="notebook.transcribe.json",
        )


def _render_analysis_result_tabs(paths, projects, project) -> None:
    (
        tab_overview,
        tab_themes,
        tab_mood,
        tab_moments,
        tab_summaries,
        tab_ask,
    ) = st.tabs(
        [
            "Overview",
            "Themes",
            "Mood & tone",
            "Moments",
            "Summaries",
            "Ask notebook",
        ]
    )

    with tab_overview:
        from transcribe.analysis.modules import (
            THROUGH_OVERVIEW,
            get_registered_modules,
        )
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Overview")
        st.caption(
            "Read-model of validated published analysis results "
            "(stats, lexical diversity, understandability, wordclouds, "
            "ner, sentiment, epistemic markers). Run analysis from the "
            "preset form above."
        )
        runner = AnalysisRunner(
            projects, clock=SystemClock(), ids=UuidGenerator()
        )
        storage = AnalysisStorage(paths)
        modules = get_registered_modules(through=THROUGH_OVERVIEW)
        read_models = {
            rm["module_id"]: rm
            for rm in module_freshness(runner, storage, list(modules.keys()))
        }

        for mid in modules:
            model = read_models.get(mid) or {
                "status": "unavailable",
                "module_id": mid,
                "envelope": None,
                "live_evidence": [],
            }
            status = model["status"]
            env = model.get("envelope")
            if status == "unavailable":
                st.warning(f"**{mid}:** unavailable (no validated published result)")
            elif status == "stale":
                st.warning(
                    f"**{mid}:** stale relative to current notebook text "
                    f"(last outcome `{env.get('outcome') if env else '?'}`)"
                )
            elif env is not None:
                cap = env.get("capability")
                outcome = env.get("outcome")
                if outcome == "failed":
                    st.error(f"**{mid}:** failed")
                elif outcome == "insufficient_data":
                    st.info(f"**{mid}:** insufficient_data")
                elif cap in {"unavailable_extra", "unavailable_model"}:
                    st.warning(f"**{mid}:** {cap}")
                elif cap == "partial":
                    st.success(f"**{mid}:** success (partial)")
                else:
                    st.success(f"**{mid}:** success ({cap})")
                payload = env.get("payload") or {}
                if mid == "wordclouds" and outcome == "success":
                    tokens = payload.get("tokens") or []
                    if isinstance(tokens, list) and tokens:
                        chart_rows = {
                            "token": [t.get("token", "") for t in tokens[:40]],
                            "weight": [float(t.get("weight") or 0) for t in tokens[:40]],
                        }
                        st.bar_chart(chart_rows, x="token", y="weight")
                    else:
                        st.warning(
                            f"**{mid}:** published success but token list missing/empty"
                        )
                if mid == "ner" and outcome == "success":
                    counts = payload.get("entity_counts") or {}
                    if counts:
                        items = list(counts.items())[:20]
                        st.bar_chart(
                            {
                                "entity": [k for k, _ in items],
                                "count": [int(v) for _, v in items],
                            },
                            x="entity",
                            y="count",
                        )
                    else:
                        st.caption("No named entities found.")
                if mid == "sentiment" and outcome == "success":
                    units = payload.get("units") or []
                    if units:
                        st.line_chart(
                            {
                                "order": [u.get("order") for u in units],
                                "compound": [float(u.get("compound") or 0) for u in units],
                            },
                            x="order",
                            y="compound",
                        )
                if mid == "epistemic_markers" and outcome == "success":
                    g = payload.get("global_stats") or {}
                    st.caption(
                        f"hedge_share={g.get('hedge_share')} "
                        f"booster_share={g.get('booster_share')} "
                        f"hits={g.get('total_marker_hits')}"
                    )
                evidence = env.get("evidence") or []
                if evidence and mid in {"ner", "epistemic_markers"}:
                    live = model.get("live_evidence") or []
                    if not live and model.get("status") != "ok":
                        live = []
                    stale_n = len(evidence) - len(live)
                    if stale_n:
                        st.warning(
                            f"**{mid}:** {stale_n} stale evidence citation(s) hidden"
                        )
                with st.expander(f"{mid} payload"):
                    st.json(payload)
            else:
                st.warning(f"**{mid}:** unavailable")

    with tab_themes:
        from transcribe.analysis.modules import (
            THROUGH_THEMES,
            get_registered_modules,
        )
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Themes")
        st.caption(
            "Keyphrases, topics, semantic motifs, and topic shifts along page order. "
            "BERTopic remains an optional extra (`unavailable_extra` when missing). "
            "Run analysis from the preset form above."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        theme_ids = [
            "keyphrases",
            "topic_modeling",
            "semantic_similarity",
            "topic_shift",
            "bertopic",
        ]
        storage = AnalysisStorage(paths)
        themes = get_registered_modules(through=THROUGH_THEMES)
        assert set(theme_ids).issubset(set(themes))
        for rm in module_freshness(runner, storage, theme_ids):
            mid = rm["module_id"]
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run analysis first")
                continue
            if rm.get("status") == "stale":
                st.warning(
                    f"**{mid}:** stale relative to current notebook — refresh analysis"
                )
                continue
            cap = env.get("capability")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if cap == "unavailable_extra":
                st.warning(banner + " (optional extra not available)")
            elif cap in {"insufficient_data", "skipped_not_applicable"}:
                st.info(banner)
            elif cap == "failed":
                st.error(banner)
            else:
                st.markdown(banner)
            payload = env.get("payload") or {}
            if mid == "keyphrases" and payload.get("phrases"):
                st.write(
                    ", ".join(
                        p.get("phrase", "") for p in payload["phrases"][:12] if p.get("phrase")
                    )
                )
            elif mid == "topic_modeling" and payload.get("topics"):
                for topic in payload["topics"][:5]:
                    terms = ", ".join(topic.get("terms") or [])
                    st.write(f"- **{topic.get('label')}**: {terms}")
            elif mid == "semantic_similarity":
                motifs = payload.get("motifs") or []
                st.caption(
                    f"{payload.get('n_units', 0)} units · {len(motifs)} motif pair(s)"
                )
            elif mid == "topic_shift":
                shifts = payload.get("shifts") or []
                st.caption(
                    f"{payload.get('n_units', 0)} units · {len(shifts)} shift boundary(ies)"
                )
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_mood:
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Mood & tone")
        st.caption(
            "Emotion chronology, contextual smoothing, affect tension, and hedging. "
            "Fine-grained emotion stays an optional extra. "
            "Run analysis from the preset form above."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        mood_ids = [
            "sentiment",
            "emotion",
            "contextual_emotion",
            "fine_grained_emotion",
            "affect_tension",
            "epistemic_markers",
        ]
        storage = AnalysisStorage(paths)
        for rm in module_freshness(runner, storage, mood_ids):
            mid = rm["module_id"]
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run analysis first")
                continue
            if rm.get("status") == "stale":
                st.warning(
                    f"**{mid}:** stale relative to current notebook — refresh analysis"
                )
                continue
            cap = env.get("capability")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if cap == "unavailable_extra":
                st.warning(banner + " (optional extra not available)")
            elif cap == "unavailable_dependency":
                st.warning(banner + " (needs emotion + sentiment parents)")
            elif cap in {"insufficient_data", "skipped_not_applicable"}:
                st.info(banner)
            else:
                st.markdown(banner)
            payload = env.get("payload") or {}
            if mid == "emotion" and payload.get("global_stats"):
                st.caption(
                    f"intensity_mean={payload['global_stats'].get('intensity_mean')}"
                )
            elif mid == "affect_tension" and payload.get("global_stats"):
                st.caption(
                    f"tension_mean={payload['global_stats'].get('tension_mean')} · "
                    f"conflicts={payload['global_stats'].get('n_conflicting')}"
                )
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_moments:
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Moments")
        st.caption(
            "Notebook salience fork (no TX momentum). Soft features from emotion, "
            "sentiment, and topic_shift enrich scores when available. "
            "Run analysis from the preset form above."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        storage = AnalysisStorage(paths)
        rm = module_freshness(runner, storage, ["moments"])[0]
        env = rm.get("envelope")
        if not env:
            st.info("**moments:** unavailable — run analysis first")
        elif rm.get("status") == "stale":
            st.warning(
                "**moments:** stale relative to current notebook — refresh analysis"
            )
        else:
            cap = env.get("capability")
            st.markdown(
                f"**moments:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            )
            payload = env.get("payload") or {}
            for row in payload.get("moments") or []:
                st.write(
                    f"- score=`{row.get('score')}` · `{row.get('quote', '')[:120]}`"
                )
            for w in env.get("warnings") or []:
                st.caption(w.get("message") or w.get("code"))
            with st.expander("moments payload"):
                st.json(payload)

    with tab_summaries:
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Summaries")
        st.caption(
            "Deterministic highlights → summary → insights, plus optional LLM "
            "outputs (honesty-labeled). Works offline when Ollama is down. "
            "Run analysis from the preset form above."
        )
        runner = AnalysisRunner(projects, clock=SystemClock(), ids=UuidGenerator())
        storage = AnalysisStorage(paths)
        synth_ids = [
            "topic_modeling",
            "highlights",
            "summary",
            "insights",
            "llm_summary",
            "llm_action_items",
            "narrative_summary",
        ]
        for rm in module_freshness(runner, storage, synth_ids):
            mid = rm["module_id"]
            env = rm.get("envelope")
            if not env:
                st.info(f"**{mid}:** unavailable — run analysis first")
                continue
            if rm.get("status") == "stale":
                st.warning(
                    f"**{mid}:** stale relative to current notebook — refresh analysis"
                )
                continue
            cap = env.get("capability")
            payload = env.get("payload") or {}
            honesty = payload.get("honesty_label")
            banner = f"**{mid}:** capability=`{cap}` outcome=`{env.get('outcome')}`"
            if honesty:
                banner += f" — _{honesty}_"
            if cap == "unavailable_model":
                st.warning(banner + " (LLM offline)")
            else:
                st.markdown(banner)
            live = rm.get("live_evidence") or []
            if live:
                st.caption(f"{len(live)} live evidence citation(s)")
            with st.expander(f"{mid} payload"):
                st.json(payload)

    with tab_ask:
        from transcribe.analysis.runner import AnalysisRunner, module_freshness
        from transcribe.analysis.storage import AnalysisStorage
        from transcribe.ports import SystemClock, UuidGenerator

        st.subheader("Ask notebook")
        st.caption(
            "Grounded QA with unit evidence. Unsupported answers abstain — "
            "no fabricated citations. Ad-hoc Ask does not update batch analysis health."
        )
        question = st.text_input("Question", key="ask_notebook_question")
        if st.button("Ask", disabled=not (question or "").strip()):
            runner = AnalysisRunner(
                projects, clock=SystemClock(), ids=UuidGenerator()
            )
            with st.spinner("Asking notebook…"):
                env = runner.run_module(
                    "llm_custom_qa", question_text=question.strip()
                )
            st.write(
                f"outcome=`{env.get('outcome')}` capability=`{env.get('capability')}`"
            )
            payload = env.get("payload") or {}
            if payload.get("honesty_label"):
                st.caption(f"Honesty: {payload['honesty_label']}")
            if payload.get("answer"):
                st.markdown(payload["answer"])
            evidence = env.get("evidence") or []
            from transcribe.analysis.envelope import filter_live_evidence

            live = filter_live_evidence(
                evidence,
                current_content_fingerprint=env.get("content_fingerprint"),
            )
            if live and env.get("published"):
                st.json(live)
            elif evidence and env.get("published"):
                st.caption("Evidence citations omitted (fingerprint mismatch)")
            for w in env.get("warnings") or []:
                st.warning(w.get("message") or w.get("code"))
            with st.expander("Raw payload"):
                st.json(payload)

        storage = AnalysisStorage(paths)
        ask_runner = AnalysisRunner(
            projects, clock=SystemClock(), ids=UuidGenerator()
        )
        rm = module_freshness(
            ask_runner,
            storage,
            ["llm_custom_qa"],
            question_text=(question or "").strip() or None,
        )[0]
        if rm.get("envelope"):
            st.divider()
            if rm.get("status") == "stale":
                st.caption(
                    "Last published Ask notebook result is stale — re-ask to refresh"
                )
            else:
                st.caption("Last published Ask notebook result")
                live = rm.get("live_evidence") or []
                if live:
                    st.json(live)
            st.json((rm["envelope"] or {}).get("payload") or {})



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
        "Export notebook JSON, Markdown, and plain text.",
    ),
    "Settings": (
        "Settings",
        "Workspace knobs: analysis presets, models, profiles, and interface menus.",
    ),
}


def main() -> None:
    configure_streamlit_page()
    inject_global_styles()

    runtime = build_runtime_paths()
    runtime.ensure_layout()
    default_root = str(runtime.default_project_dir())

    mode = normalize_ui_mode(st.session_state.get("ui_mode"))
    st.session_state["ui_mode"] = mode

    with st.sidebar:
        render_brand()
        mode = render_mode_nav(mode)
        render_nav_section("Project")
        root = st.text_input(
            "Project directory", value=st.session_state.get("root", default_root)
        )
        st.session_state["root"] = root
        if "create_notebook_title" not in st.session_state:
            st.session_state["create_notebook_title"] = (
                Path(root).expanduser().name or "Untitled notebook"
            )
        create_title = st.text_input(
            "Notebook name",
            help="Used when Create makes a new notebook. Rename later from View or Import.",
            key="create_notebook_title",
        )
        st.caption(f"Projects root: `{runtime.projects_dir}`")
        st.caption(f"Inbox: `{runtime.inbox_dir}`")
        st.caption(f"Exports: `{runtime.export_dir}`")

        col_a, col_b = st.columns(2)
        if col_a.button("Create", width="stretch"):
            try:
                cleaned = (create_title or "").strip() or "Untitled notebook"
                paths = open_project_paths(Path(root))
                ProjectService(paths, clock=SystemClock(), ids=UuidGenerator()).create(
                    title=cleaned
                )
                st.success(f"Created “{cleaned}”")
                st.cache_resource.clear()
            except TranscribeError as exc:
                st.error(str(exc))
        if col_b.button("Open", width="stretch"):
            try:
                paths, projects, ingest = _services(root)
                ingest.cleanup_staging()
                projects.load(reconcile=True)
                st.cache_resource.clear()
                set_ui_mode("Import")
            except TranscribeError as exc:
                st.error(str(exc))

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    archive.ensure_index()

    # Page viewer overlay when navigated from Archive/Search/View.
    if (
        not is_workflow_mode(mode)
        and st.session_state.get("show_page_viewer")
        and st.session_state.get("view_page_id")
        and st.session_state.get("root")
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
    elif mode == "Settings":
        render_settings_page()
    elif is_workflow_mode(mode):
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
