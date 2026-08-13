"""Transcribe page — This notebook | Batch (TranscriptX Target pattern)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from transcribe.analysis.llm_runtime import (
    is_unsuitable_text_model_name,
    suitable_text_model_names,
)
from transcribe.corpus.import_run import ImportRunStore
from transcribe.corpus.ocr_run import OcrBatchRunStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.models import DEFAULT_PREFER_MODE, OCRSettings, Project
from transcribe.errors import JobConflictError, TranscribeError, ValidationError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    invalidate_discovery_cache,
    is_local_machine_host,
    normalize_base_url,
)
from transcribe.runtime_paths import RuntimePaths, default_ollama_base_url
from transcribe.services.archive import bump_archive_generation
from transcribe.services.batch_ocr import (
    BatchOcrCoordinator,
    BatchOcrProgress,
    build_batch_ocr_coordinator,
    list_candidates,
    select_by_ids,
    select_from_import_run,
    select_pending,
)
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.project import ProjectService
from transcribe.ui.components.action_links import render_action_link
from transcribe.ui.components.progress_panel import render_progress_panel
from transcribe.ui.shell import set_ui_mode
from transcribe.ui.targets import (
    PENDING_TRANSCRIBE_TARGET_KEY,
    TARGET_BATCH,
    TARGET_OPTIONS,
    TARGET_THIS,
    TRANSCRIBE_BATCH_IMPORT_RUN_KEY,
    TRANSCRIBE_BATCH_NOTEBOOK_IDS_KEY,
    TRANSCRIBE_BATCH_SOURCE_KEY,
    TRANSCRIBE_TARGET_KEY,
    apply_pending_target,
    normalize_target,
)

_BATCH_SNAPSHOT_KEY = "batch_ocr_progress_snapshot"
_BATCH_POST_RUN_KEY = "_batch_ocr_post_run_id"
_BATCH_WAS_RUNNING_KEY = "_batch_ocr_was_running"


@st.cache_resource
def get_coordinator(project_root: str) -> JobCoordinator:
    from transcribe.runtime_paths import build_runtime_paths

    _paths, _projects, coord, _ingest = build_coordinator(
        project_root,
        clock=SystemClock(),
        ids=UuidGenerator(),
        archive_runtime=build_runtime_paths(),
    )
    return coord


@st.cache_resource
def get_batch_ocr_coordinator(data_dir: str, projects_dir: str) -> BatchOcrCoordinator:
    from transcribe.runtime_paths import build_runtime_paths

    live = build_runtime_paths()
    corpus = CorpusPaths(data_dir=Path(data_dir), projects_dir=Path(projects_dir))
    return build_batch_ocr_coordinator(
        corpus,
        clock=SystemClock(),
        ids=UuidGenerator(),
        archive_runtime=live,
    )


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


def _failed_page_ids(projects: ProjectService, project: Project) -> list[str]:
    failed: list[str] = []
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        if result is not None and result.status == "failed":
            failed.append(page.page_id)
    return failed


def _render_transcribe_complete_actions(
    *,
    projects: ProjectService,
    project: Project,
    coord: JobCoordinator,
    progress: JobProgress,
) -> None:
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


def _batch_progress_to_snapshot(progress: BatchOcrProgress) -> dict[str, Any]:
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    pct = (done / total * 100.0) if total else 0.0
    status = progress.status
    if status in {"cancelled", "partial", "failed"}:
        panel_status = "failed" if status == "failed" else (
            "completed" if status == "partial" else "failed"
        )
        if status == "partial":
            panel_status = "completed"
        phase = status
    elif status == "completed":
        panel_status = "completed"
        phase = "completed"
    else:
        panel_status = "running"
        phase = "running_pipeline"
    pages = ""
    if progress.pages_total:
        pages = (
            f"pages {progress.pages_completed}/{progress.pages_total} "
            f"(failed {progress.pages_failed}, skipped {progress.pages_skipped})"
        )
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": progress.current_item,
        "current_module": pages,
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": None,
    }


def _render_batch_progress(coord: BatchOcrCoordinator, runtime: RuntimePaths) -> bool:
    """Return True when the page should skip the settings form."""
    live = coord.get_progress()
    was_running = st.session_state.get(_BATCH_WAS_RUNNING_KEY, False)
    st.session_state[_BATCH_WAS_RUNNING_KEY] = live.status == "running"
    is_running = live.status == "running" or coord.is_running()
    post_id = st.session_state.get(_BATCH_POST_RUN_KEY)
    show_post = (
        bool(post_id)
        and live.ocr_run_id == post_id
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
                _batch_progress_to_snapshot(progress),
                unit_label="notebooks",
                current_label="Current pages",
            )
            if (
                st.session_state.get(_BATCH_WAS_RUNNING_KEY)
                and progress.status != "running"
            ):
                st.session_state[_BATCH_WAS_RUNNING_KEY] = False
                st.session_state[_BATCH_POST_RUN_KEY] = progress.ocr_run_id
                bump_archive_generation(runtime)
                st.rerun()

        batch_status_panel()
        if st.button("Stop after current page", key="batch_ocr_stop"):
            coord.request_cancel()
            st.info("Stopping after current page; remaining notebooks will not start.")
        return True

    render_progress_panel(
        _batch_progress_to_snapshot(live),
        unit_label="notebooks",
        current_label="Current pages",
    )
    _render_batch_complete_actions(coord, live)
    return True


def _render_batch_complete_actions(
    coord: BatchOcrCoordinator, progress: BatchOcrProgress
) -> None:
    st.markdown("#### Next")
    run = None
    try:
        run = coord.store.load(progress.ocr_run_id)
    except TranscribeError:
        run = None
    retry_ids = [
        item.notebook_id
        for item in (run.items if run else [])
        if item.state == "failed" or item.pages_failed
    ]
    cols = st.columns(3, gap="small")
    with cols[0]:
        if render_action_link(
            "View",
            key="tx_batch_done_view",
            icon=":material/menu_book:",
            help="Open the notebook list.",
        ):
            set_ui_mode("View")
    with cols[1]:
        if render_action_link(
            "Retry failed",
            key="tx_batch_done_retry",
            icon=":material/replay:",
            help="Re-run OCR on notebooks that failed or have failed pages.",
            disabled=not retry_ids,
        ):
            try:
                settings = OCRSettings.from_dict(run.settings if run else {})
                candidates = list_candidates(coord.corpus)
                selected = select_by_ids(candidates, retry_ids)
                new_run = coord.create_run(
                    selected,
                    settings=settings,
                    force=bool(run.force) if run else False,
                    import_run_id=run.import_run_id if run else None,
                )
                coord.start(new_run.ocr_run_id)
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                st.rerun()
            except (JobConflictError, TranscribeError, ValidationError) as exc:
                st.error(str(exc))
    with cols[2]:
        if render_action_link(
            "Change settings",
            key="tx_batch_done_settings",
            icon=":material/settings:",
            help="Return to batch OCR settings.",
        ):
            st.session_state.pop(_BATCH_POST_RUN_KEY, None)
            st.rerun()
    if run is not None:
        for item in run.items:
            bits = [
                item.state,
                f"{item.pages_completed}/{item.pages_total} pages",
            ]
            if item.pages_failed:
                bits.append(f"{item.pages_failed} failed")
            if item.pages_skipped:
                bits.append(f"{item.pages_skipped} skipped")
            if item.error_message:
                bits.append(item.error_message)
            st.write(f"- **{item.title or item.notebook_id}** · " + " · ".join(bits))


def render_run_transcribe(
    runtime: RuntimePaths,
    *,
    root: str | None,
    projects: ProjectService | None,
    project: Project | None,
) -> None:
    batch_coord = get_batch_ocr_coordinator(
        str(runtime.data_dir), str(runtime.projects_dir)
    )
    if _render_batch_progress(batch_coord, runtime):
        return

    apply_pending_target(
        st.session_state,
        pending_key=PENDING_TRANSCRIBE_TARGET_KEY,
        target_key=TRANSCRIBE_TARGET_KEY,
    )
    normalize_target(st.session_state, TRANSCRIBE_TARGET_KEY)
    target = st.segmented_control(
        "Target",
        options=list(TARGET_OPTIONS),
        key=TRANSCRIBE_TARGET_KEY,
        help=(
            "This notebook: OCR the selected notebook. "
            "Batch: same OCR settings across many notebooks "
            "(pending pages, an import run, or a manual pick)."
        ),
    )
    if target is None:
        target = st.session_state.get(TRANSCRIBE_TARGET_KEY) or TARGET_THIS

    if target == TARGET_THIS and root and projects is not None and project is not None:
        if _render_this_notebook_live(runtime, root=root, projects=projects, project=project):
            return

    seed = (
        project.settings
        if project is not None
        else OCRSettings(base_url=default_ollama_base_url())
    )
    form = _render_ocr_settings_form(seed, key_prefix="tx")
    if form is None:
        return

    if target == TARGET_BATCH:
        _render_batch_launch(runtime, batch_coord, form=form, seed=seed)
        return

    if project is None or projects is None or not root:
        st.info(
            "Select a notebook above, or create one under Workflow → New notebook."
        )
        return
    _render_this_notebook_launch(
        runtime, root=root, projects=projects, project=project, form=form
    )


def _render_this_notebook_live(
    runtime: RuntimePaths,
    *,
    root: str,
    projects: ProjectService,
    project: Project,
) -> bool:
    """Return True when a live/post job owns the page (hide shared settings)."""
    coord = get_coordinator(str(root))
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
        return True

    if show_post:
        _render_job_progress(live)
        _render_transcribe_complete_actions(
            projects=projects,
            project=project,
            coord=coord,
            progress=live,
        )
        return True
    return False


def _render_this_notebook_launch(
    runtime: RuntimePaths,
    *,
    root: str,
    projects: ProjectService,
    project: Project,
    form: dict[str, Any],
) -> None:
    coord = get_coordinator(str(root))
    if st.button("Save settings"):
        project = _apply_form_settings(projects, project, form)
        coord.provider = OllamaVisionProvider(form["normalized"])
        st.success("Settings saved")

    if st.button("Start transcription"):
        if form["remote"] and not form["allow_remote"]:
            st.error("Enable the remote-host acknowledgement first.")
        else:
            try:
                project = _apply_form_settings(projects, project, form)
                coord.provider = OllamaVisionProvider(form["normalized"])
                coord.start(force=form["force"])
                st.session_state["_job_was_running"] = True
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Compare models")
    st.caption(
        "Run two or more vision models on this notebook, then rank and "
        "optionally produce a composite candidate with the text model."
    )
    multi_models = st.multiselect(
        "Vision models for multipass",
        options=form["names"],
        default=[],
        format_func=form["model_label"],
        help="Select at least two models.",
    )
    no_auto_comp = st.checkbox(
        "Do not auto-activate composite",
        value=not bool(project.settings.auto_activate_composite),
    )
    if st.button("Start multipass compare"):
        if form["remote"] and not form["allow_remote"]:
            st.error("Enable the remote-host acknowledgement first.")
        elif len(multi_models) < 2:
            st.error("Select at least two vision models.")
        else:
            try:
                from transcribe.services.multipass import MultiPassCoordinator

                project = _apply_form_settings(projects, project, form)
                coord.provider = OllamaVisionProvider(form["normalized"])
                multi = MultiPassCoordinator(
                    jobs=coord,
                    projects=projects,
                    clock=SystemClock(),
                    ids=UuidGenerator(),
                )
                with st.spinner("Running multipass (this may take a while)…"):
                    progress = multi.run_blocking(
                        model_names=list(multi_models),
                        force=form["force"],
                        auto_activate_composite=not no_auto_comp,
                    )
                if progress.status == "completed":
                    st.success(progress.message or "Multipass complete")
                else:
                    st.error(progress.message or progress.status)
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))


def _render_batch_launch(
    runtime: RuntimePaths,
    batch_coord: BatchOcrCoordinator,
    *,
    form: dict[str, Any],
    seed: OCRSettings,
) -> None:
    corpus = CorpusPaths.from_runtime(runtime)
    candidates = list_candidates(corpus)
    source_options = ["pending", "import_run", "pick"]
    queued_source = st.session_state.pop(TRANSCRIBE_BATCH_SOURCE_KEY, None)
    if queued_source in source_options and "tx_batch_source" not in st.session_state:
        st.session_state["tx_batch_source"] = queued_source
    source = st.radio(
        "Notebooks",
        options=source_options,
        format_func=lambda s: {
            "pending": "Notebooks with pending pages",
            "import_run": "From an import run",
            "pick": "Pick notebooks",
        }[s],
        key="tx_batch_source",
        horizontal=True,
    )
    selected = []
    import_run_id: str | None = None
    if source == "pending":
        selected = select_pending(candidates)
        st.caption(
            f"{len(selected)} notebook(s) with untranscribed or failed pages "
            f"({sum(c.pages_pending for c in selected)} page(s))."
        )
    elif source == "import_run":
        runs = ImportRunStore(corpus).list_runs()
        queued_run = st.session_state.pop(TRANSCRIBE_BATCH_IMPORT_RUN_KEY, None)
        labels = {r.import_run_id: f"{r.import_run_id} · {r.status}" for r in runs}
        run_ids = [r.import_run_id for r in runs]
        if queued_run in run_ids:
            st.session_state["tx_batch_import_run"] = queued_run
        if not run_ids:
            st.info("No import runs yet. Batch-import folders under Import → Batch.")
        else:
            chosen = st.selectbox(
                "Import run",
                options=run_ids,
                format_func=lambda rid: labels.get(rid, rid),
                key="tx_batch_import_run",
            )
            import_run_id = str(chosen) if chosen else None
            if import_run_id:
                try:
                    selected = select_from_import_run(
                        corpus, import_run_id, candidates
                    )
                    st.caption(
                        f"{len(selected)} committed notebook(s) · "
                        f"{sum(c.pages_pending for c in selected)} pending page(s)."
                    )
                except (TranscribeError, ValidationError) as exc:
                    st.error(str(exc))
    else:
        queued_ids = st.session_state.pop(TRANSCRIBE_BATCH_NOTEBOOK_IDS_KEY, None)
        options = [c.notebook_id for c in candidates]
        labels = {
            c.notebook_id: f"{c.title} ({c.pages_pending} pending / {c.pages_total})"
            for c in candidates
        }
        default = [nid for nid in (queued_ids or []) if nid in options]
        if default and "tx_batch_pick" not in st.session_state:
            st.session_state["tx_batch_pick"] = default
        picked = st.multiselect(
            "Notebooks",
            options=options,
            format_func=lambda nid: labels.get(nid, nid),
            key="tx_batch_pick",
        )
        if picked:
            try:
                selected = select_by_ids(candidates, list(picked))
            except TranscribeError as exc:
                st.error(str(exc))

    recent = OcrBatchRunStore(corpus).list_runs()[:8]
    if recent:
        with st.expander("Recent batch OCR runs", expanded=False):
            for run in recent:
                ok = sum(1 for i in run.items if i.state == "completed")
                st.caption(
                    f"`{run.ocr_run_id}` · {run.status} · {ok}/{len(run.items)} notebooks"
                )
                if run.status in {"pending", "running"} or any(
                    i.state in {"pending", "running"} for i in run.items
                ):
                    if st.button("Resume", key=f"batch_ocr_resume_{run.ocr_run_id}"):
                        try:
                            batch_coord.start(run.ocr_run_id)
                            st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                            st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                            st.rerun()
                        except (JobConflictError, TranscribeError) as exc:
                            st.error(str(exc))

    if st.button("Start batch transcription", type="primary", key="tx_batch_start"):
        if form["remote"] and not form["allow_remote"]:
            st.error("Enable the remote-host acknowledgement first.")
        elif not selected:
            st.error("Select at least one notebook.")
        else:
            try:
                settings = _form_to_settings(seed, form)
                new_run = batch_coord.create_run(
                    selected,
                    settings=settings,
                    force=form["force"],
                    import_run_id=import_run_id,
                )
                batch_coord.start(new_run.ocr_run_id)
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                st.rerun()
            except (JobConflictError, TranscribeError, ValidationError) as exc:
                st.error(str(exc))


def _form_to_settings(base: OCRSettings, form: dict[str, Any]) -> OCRSettings:
    settings = OCRSettings.from_dict(base.as_dict())
    settings.base_url = form["normalized"]
    settings.model_name = form["model"]
    settings.text_model_name = form["text_model"]
    settings.prompt_id = form["prompt_id"]
    settings.custom_prompt = form["custom"].strip() or None
    settings.preprocess_profile = form["preprocess"]
    settings.max_workers = int(form["workers"])
    settings.allow_non_loopback = form["allow_remote"]
    settings.cleanup_enabled = bool(form["cleanup_enabled"])
    settings.cleanup_mode = form["cleanup_mode"]
    if form["cleanup_enabled"]:
        settings.cleanup_model_name = form["cleanup_model"]
    settings.prefer_mode = form["prefer_mode"]
    settings.auto_activate_composite = bool(form["auto_activate_composite"])
    return settings


def _apply_form_settings(
    projects: ProjectService, project: Project, form: dict[str, Any]
) -> Project:
    settings = _form_to_settings(project.settings, form)
    return projects.save_settings(project, settings)


def _render_ocr_settings_form(
    project: Project | OCRSettings, *, key_prefix: str
) -> dict[str, Any] | None:
    settings = project.settings if isinstance(project, Project) else project
    base_url = st.text_input(
        "Ollama base URL",
        value=settings.base_url,
        key=f"{key_prefix}_base_url",
    )
    try:
        normalized = normalize_base_url(base_url)
        remote = not is_local_machine_host(normalized)
    except Exception as exc:
        st.error(str(exc))
        return None

    allow_remote = False
    if remote:
        st.warning(
            "This Ollama host is not loopback. Page images will leave this machine."
        )
        allow_remote = st.checkbox(
            "I understand and want to use this remote host",
            key=f"{key_prefix}_allow_remote",
        )

    provider = OllamaVisionProvider(normalized)
    _, c2 = st.columns([1, 1])
    refresh = c2.button("Refresh Models", key=f"{key_prefix}_refresh")
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

    model_options = names or [settings.model_name or ""]
    model_index = 0
    if settings.model_name in model_options:
        model_index = model_options.index(settings.model_name)
    model = st.selectbox(
        "Vision model",
        options=model_options,
        index=model_index,
        format_func=_model_label,
        key=f"{key_prefix}_model",
    )
    text_model_options = suitable_text_model_names(all_discovery.models)
    if settings.text_model_name and is_unsuitable_text_model_name(settings.text_model_name):
        st.warning(
            f"Saved text model `{settings.text_model_name}` is "
            "vision/embedding — choose a text model below."
        )
    if not text_model_options:
        st.caption("No suitable text models discovered from Ollama.")
        text_model_options = [""]
    text_index = 0
    if settings.text_model_name in text_model_options:
        text_index = text_model_options.index(settings.text_model_name)
    text_model = st.selectbox(
        "Text analysis model",
        options=text_model_options,
        index=text_index,
        help="Required for LLM analysis modules. Vision/embedding models are filtered out.",
        key=f"{key_prefix}_text_model",
    )

    cleanup_enabled = st.checkbox(
        "Clean OCR with text model",
        value=bool(settings.cleanup_enabled),
        help=(
            "Optional second-pass text model after vision OCR. "
            "Adds one Ollama call per page; failures keep raw OCR."
        ),
        key=f"{key_prefix}_cleanup",
    )

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
        default_prompt = settings.prompt_id or "faithful_markdown"
        prompt_index = ocr_ids.index(default_prompt) if default_prompt in ocr_ids else 0
        prompt_id = st.selectbox(
            "Prompt", ocr_ids, index=prompt_index, key=f"{key_prefix}_prompt"
        )
        custom = st.text_area(
            "Custom prompt override (optional)",
            value=settings.custom_prompt or "",
            key=f"{key_prefix}_custom",
        )
        preprocess = st.selectbox(
            "Preprocess",
            ["none", "gentle_contrast"],
            index=(
                ["none", "gentle_contrast"].index(settings.preprocess_profile)
                if settings.preprocess_profile in {"none", "gentle_contrast"}
                else 0
            ),
            key=f"{key_prefix}_preprocess",
        )
        workers = st.selectbox(
            "Workers",
            [1, 2],
            index=0 if int(settings.max_workers or 1) != 2 else 1,
            key=f"{key_prefix}_workers",
        )
        force = st.checkbox(
            "Force re-run (ignore matching fingerprints)",
            key=f"{key_prefix}_force",
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
                list(cleanup_mode_labels.keys()).index(settings.cleanup_mode)
                if settings.cleanup_mode in cleanup_mode_labels
                else 0
            ),
            disabled=not cleanup_enabled,
            key=f"{key_prefix}_cleanup_mode",
        )
        cleanup_model_options = text_model_options
        cleanup_index = 0
        if settings.cleanup_model_name in cleanup_model_options:
            cleanup_index = cleanup_model_options.index(settings.cleanup_model_name)
        elif settings.text_model_name in cleanup_model_options:
            cleanup_index = cleanup_model_options.index(settings.text_model_name)
        cleanup_model = st.selectbox(
            "Cleanup model",
            options=cleanup_model_options,
            index=cleanup_index,
            disabled=not cleanup_enabled,
            help=(
                "Text model for cleanup (vision/embedding filtered out). "
                "Falls back to the text analysis model if unset."
            ),
            key=f"{key_prefix}_cleanup_model",
        )
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
                list(prefer_labels.keys()).index(settings.prefer_mode)
                if settings.prefer_mode in prefer_labels
                else list(prefer_labels.keys()).index(DEFAULT_PREFER_MODE)
                if DEFAULT_PREFER_MODE in prefer_labels
                else 0
            ),
            key=f"{key_prefix}_prefer",
        )
        auto_activate_composite = st.checkbox(
            "Auto-activate composite after multipass",
            value=bool(settings.auto_activate_composite),
            key=f"{key_prefix}_auto_comp",
        )
        st.caption(
            "Unverified model identity may increase cost or surprise quality — "
            "prefer discovered vision-capable tags when listed."
        )

    return {
        "normalized": normalized,
        "remote": remote,
        "allow_remote": allow_remote,
        "model": model,
        "text_model": text_model,
        "cleanup_enabled": cleanup_enabled,
        "prompt_id": prompt_id,
        "custom": custom,
        "preprocess": preprocess,
        "workers": workers,
        "force": force,
        "cleanup_mode": cleanup_mode,
        "cleanup_model": cleanup_model,
        "prefer_mode": prefer_mode,
        "auto_activate_composite": auto_activate_composite,
        "names": names,
        "model_label": _model_label,
    }
