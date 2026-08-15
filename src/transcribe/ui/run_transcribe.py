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
from transcribe.services.batch_notebooks import (
    NotebookCandidate,
    enrich_page_stats,
    list_candidates_light,
)
from transcribe.services.job import JobCoordinator, JobProgress, build_coordinator
from transcribe.services.multipass import MultiPassCoordinator, MultiPassProgress
from transcribe.services.project import ProjectService
from transcribe.ui.components.action_links import render_action_link
from transcribe.ui.components.model_info import (
    render_model_information,
    warn_if_first_compare_model_is_general_vlm,
)
from transcribe.ui.components.progress_panel import render_progress_panel
from transcribe.ui.corpus_listing_cache import (
    corpus_listing_token,
    get_cached_listing,
    invalidate_listing_key_prefix,
    invalidate_listing_keys,
)
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
_OCR_CANDIDATES_KEY = "tx_batch_ocr_candidates"
_OCR_CANDIDATES_TOKEN_KEY = "tx_batch_ocr_candidates_token"
_LIGHT_PICKER_KEY = "tx_batch_light_picker"
_LIGHT_PICKER_TOKEN_KEY = "tx_batch_light_picker_token"
_IMPORT_RUNS_KEY = "tx_batch_import_runs"
_IMPORT_RUNS_TOKEN_KEY = "tx_batch_import_runs_token"
_RECENT_OCR_RUNS_KEY = "tx_batch_ocr_recent"
_RECENT_OCR_RUNS_TOKEN_KEY = "tx_batch_ocr_recent_token"
_IMPORT_ENRICHED_PREFIX = "tx_batch_import_enriched"
_OCR_SELECTED_KEY = "tx_batch_selected_for_launch"
_OCR_IMPORT_RUN_KEY = "tx_batch_import_run_for_launch"


def invalidate_batch_ocr_caches() -> None:
    """Drop session-cached OCR candidate listings and related run lists."""
    invalidate_listing_keys(
        st.session_state,
        _OCR_CANDIDATES_KEY,
        _OCR_CANDIDATES_TOKEN_KEY,
        _LIGHT_PICKER_KEY,
        _LIGHT_PICKER_TOKEN_KEY,
        _IMPORT_RUNS_KEY,
        _IMPORT_RUNS_TOKEN_KEY,
        _RECENT_OCR_RUNS_KEY,
        _RECENT_OCR_RUNS_TOKEN_KEY,
    )
    invalidate_listing_key_prefix(st.session_state, _IMPORT_ENRICHED_PREFIX)


def _invalidate_ocr_and_analyse_listings() -> None:
    """OCR text changes also stale Analyse 'needing analysis' listings."""
    invalidate_batch_ocr_caches()
    from transcribe.ui.run_analysis_batch import invalidate_batch_analyse_caches

    invalidate_batch_analyse_caches()


def _cached_light_picker(corpus: CorpusPaths) -> list[NotebookCandidate]:
    return get_cached_listing(
        st.session_state,
        cache_key=_LIGHT_PICKER_KEY,
        token_key=_LIGHT_PICKER_TOKEN_KEY,
        token=corpus_listing_token(corpus),
        loader=lambda: list_candidates_light(corpus),
    )


def _cached_ocr_candidates(
    corpus: CorpusPaths, *, force: bool = False
) -> list[NotebookCandidate]:
    def _load() -> list[NotebookCandidate]:
        with st.spinner("Scanning notebooks for pending pages…"):
            return list_candidates(corpus)

    return get_cached_listing(
        st.session_state,
        cache_key=_OCR_CANDIDATES_KEY,
        token_key=_OCR_CANDIDATES_TOKEN_KEY,
        token=corpus_listing_token(corpus),
        loader=_load,
        force=force,
    )


def _cached_import_runs(corpus: CorpusPaths) -> list:
    return get_cached_listing(
        st.session_state,
        cache_key=_IMPORT_RUNS_KEY,
        token_key=_IMPORT_RUNS_TOKEN_KEY,
        token=corpus_listing_token(corpus),
        loader=lambda: ImportRunStore(corpus).list_runs(),
    )


def _cached_recent_ocr_runs(corpus: CorpusPaths) -> list:
    return get_cached_listing(
        st.session_state,
        cache_key=_RECENT_OCR_RUNS_KEY,
        token_key=_RECENT_OCR_RUNS_TOKEN_KEY,
        token=corpus_listing_token(corpus),
        loader=lambda: OcrBatchRunStore(corpus).list_runs()[:8],
    )


def _cached_import_enriched(
    corpus: CorpusPaths, import_run_id: str, picker: list[NotebookCandidate]
) -> list[NotebookCandidate]:
    token = corpus_listing_token(corpus)
    cache_key = f"{_IMPORT_ENRICHED_PREFIX}:{import_run_id}"
    token_key = f"{_IMPORT_ENRICHED_PREFIX}:{import_run_id}:token"

    def _load() -> list[NotebookCandidate]:
        selected = select_from_import_run(corpus, import_run_id, picker)
        return enrich_page_stats(selected)

    return get_cached_listing(
        st.session_state,
        cache_key=cache_key,
        token_key=token_key,
        token=token,
        loader=_load,
    )


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
def get_multipass_coordinator(project_root: str) -> MultiPassCoordinator:
    coord = get_coordinator(project_root)
    return MultiPassCoordinator(
        jobs=coord,
        projects=coord.projects,
        clock=coord.clock,
        ids=coord.ids,
    )


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


def _job_progress_to_snapshot(progress: JobProgress) -> dict[str, Any]:
    done = progress.completed + progress.failed
    total = progress.total
    pct = (done / total * 100.0) if total else 0.0
    if progress.status == "completed":
        panel_status, phase = "completed", "completed"
        pct = 100.0 if total else pct
    elif progress.status == "failed":
        panel_status, phase = "failed", "failed"
    elif progress.status == "cancelled":
        panel_status, phase = "failed", "cancelled"
    else:
        panel_status, phase = "running", "running_pipeline"
    current = ", ".join(progress.current_labels) or ", ".join(
        p[:8] for p in progress.current_page_ids
    )
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": current,
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.message if progress.status == "failed" else None,
    }


def _render_job_progress(progress: JobProgress) -> None:
    render_progress_panel(
        _job_progress_to_snapshot(progress),
        unit_label="pages",
        current_label="Current page",
    )
    if progress.circuit_open:
        if "cannot load this vision model" in (progress.message or "").lower():
            st.warning(progress.message)
        else:
            st.warning(
                "This model hit repeated Ollama timeouts; remaining pages for this "
                "model were skipped."
            )
    if progress.status == "running":
        st.info(
            "OCR is running in the background. Progress also prints in the "
            "Streamlit terminal as `[transcribe] …` lines. The first page can "
            "take several minutes while Ollama loads the vision model."
        )


def _render_multipass_progress(multi: MultiPassProgress, job: JobProgress) -> None:
    st.write(
        f"Compare: **{multi.status}** — {multi.phase or 'starting'}"
        + (f" · model {multi.model_index}/{multi.model_total}" if multi.model_total else "")
    )
    if multi.phase == "vision" and job.status in {
        "running",
        "completed",
        "cancelled",
        "failed",
    }:
        _render_job_progress(job)
    elif multi.phase == "rank_composite":
        total = multi.pages_total or 0
        done = multi.pages_ranked
        if total > 0:
            st.progress(
                min(1.0, done / total),
                text=f"Rank/composite {done}/{total} pages",
            )
        if multi.message:
            st.caption(multi.message)
    elif multi.message:
        st.caption(multi.message)
    if multi.status == "running":
        st.info(
            "Compare is running in the background. Stop after current page "
            "cancels remaining pages of this model and remaining models."
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
    from transcribe.ui.action_menus.ids import SectionId
    from transcribe.ui.post_job import render_post_job_strip
    from transcribe.runtime_paths import build_runtime_paths

    runtime = build_runtime_paths()
    render_post_job_strip(
        SectionId.TRANSCRIBE_COMPLETE,
        project=project,
        root=projects.paths.root,
        projects_dir=runtime.projects_dir,
        instance_prefix="tx_done",
    )
    failed_ids = _failed_page_ids(projects, project)
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


def _batch_progress_to_snapshot(progress: BatchOcrProgress) -> dict[str, Any]:
    done = progress.completed + progress.failed + progress.skipped
    total = progress.total
    page_frac = 0.0
    if progress.status == "running" and progress.pages_total:
        page_done = progress.pages_completed + progress.pages_failed
        page_frac = min(1.0, page_done / progress.pages_total)
    pct = ((done + page_frac) / total * 100.0) if total else 0.0
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
    detail_bits: list[str] = []
    if progress.mode == "multipass":
        if progress.phase:
            detail_bits.append(progress.phase)
        if progress.current_model:
            detail_bits.append(progress.current_model)
        elif progress.model_total:
            detail_bits.append(f"model {progress.model_index}/{progress.model_total}")
    if progress.current_page_label:
        detail_bits.append(progress.current_page_label)
    return {
        "status": panel_status,
        "phase": phase,
        "current_item": progress.current_item,
        "detail_current": " · ".join(detail_bits) if detail_bits else "",
        "detail_completed": progress.pages_completed,
        "detail_failed": progress.pages_failed,
        "detail_skipped": progress.pages_skipped,
        "detail_total": progress.pages_total,
        "detail_unit": "pages in this notebook",
        "completed": progress.completed,
        "skipped": progress.skipped,
        "failed": progress.failed,
        "total": total,
        "pct": pct,
        "latest_event": progress.message,
        "recent_logs": [],
        "error": progress.message if status == "failed" else None,
    }


def _render_batch_progress(coord: BatchOcrCoordinator, runtime: RuntimePaths) -> bool:
    """Return True when the page should skip the settings form."""
    live = coord.get_progress()
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
                current_label="Current notebook",
            )
            if st.session_state.get(_BATCH_WAS_RUNNING_KEY) and progress.status != "running":
                st.session_state[_BATCH_WAS_RUNNING_KEY] = False
                st.session_state[_BATCH_POST_RUN_KEY] = progress.ocr_run_id
                bump_archive_generation(runtime)
                _invalidate_ocr_and_analyse_listings()
                st.rerun()

        batch_status_panel()
        if st.button("Stop after current page", key="batch_ocr_stop"):
            coord.request_cancel()
            st.info("Stopping after current page; remaining notebooks will not start.")
        return True

    render_progress_panel(
        _batch_progress_to_snapshot(live),
        unit_label="notebooks",
        current_label="Current notebook",
    )
    _render_batch_complete_actions(coord, live)
    return True


def _render_batch_complete_actions(coord: BatchOcrCoordinator, progress: BatchOcrProgress) -> None:
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
            "Library",
            key="tx_batch_done_view",
            icon=":material/menu_book:",
            help="Open the notebook list.",
        ):
            set_ui_mode("Library")
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
                candidates = list_candidates_light(coord.corpus)
                selected = select_by_ids(candidates, retry_ids)
                new_run = coord.create_run(
                    selected,
                    settings=settings,
                    force=bool(run.force) if run else False,
                    import_run_id=run.import_run_id if run else None,
                )
                invalidate_batch_ocr_caches()
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
    batch_coord = get_batch_ocr_coordinator(str(runtime.data_dir), str(runtime.projects_dir))
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
            "Batch: same OCR plan across many notebooks "
            "(single model or compare models; pending pages, an import run, "
            "or a manual pick)."
        ),
    )
    if target is None:
        target = st.session_state.get(TRANSCRIBE_TARGET_KEY) or TARGET_THIS

    if target == TARGET_THIS and root and projects is not None and project is not None:
        if _render_this_notebook_live(runtime, root=root, projects=projects, project=project):
            return

    seed = (
        project.settings if project is not None else OCRSettings(base_url=default_ollama_base_url())
    )

    if target == TARGET_BATCH:
        @st.fragment
        def batch_source_panel() -> None:
            _render_batch_notebook_source(runtime, project=project)

        batch_source_panel()

        @st.fragment
        def batch_settings_and_launch() -> None:
            form = _render_ocr_settings_form(seed, key_prefix="tx")
            if form is None:
                return
            _render_batch_launch_actions(
                runtime, batch_coord, form=form, seed=seed
            )

        batch_settings_and_launch()
        return

    if project is None or projects is None or not root:
        st.info("Select a notebook in the View block, or create one under Workflow → New notebook.")
        return

    @st.fragment
    def this_settings_and_launch() -> None:
        form = _render_ocr_settings_form(seed, key_prefix="tx")
        if form is None:
            return
        _render_this_notebook_launch(
            runtime, root=root, projects=projects, project=project, form=form
        )

    this_settings_and_launch()


def _render_this_notebook_live(
    runtime: RuntimePaths,
    *,
    root: str,
    projects: ProjectService,
    project: Project,
) -> bool:
    """Return True when a live/post job owns the page (hide shared settings)."""
    coord = get_coordinator(str(root))
    multi = get_multipass_coordinator(str(root))
    live = coord.get_progress()
    multi_live = multi.get_progress()
    is_running = live.status == "running" or multi_live.status == "running"
    was_running = st.session_state.get("_job_was_running", False)
    st.session_state["_job_was_running"] = is_running
    post_job_id = st.session_state.get("_transcribe_post_job_id")
    post_kind = st.session_state.get("_transcribe_post_kind", "job")
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
            still_running = progress.status == "running" or mp.status == "running"
            if st.session_state.get("_job_was_running") and not still_running:
                st.session_state["_job_was_running"] = False
                if mp.status in {"completed", "cancelled", "failed"} and mp.pass_id:
                    st.session_state["_transcribe_post_job_id"] = mp.pass_id
                    st.session_state["_transcribe_post_kind"] = "multipass"
                else:
                    st.session_state["_transcribe_post_job_id"] = progress.job_id
                    st.session_state["_transcribe_post_kind"] = "job"
                bump_archive_generation(runtime)
                _invalidate_ocr_and_analyse_listings()
                st.rerun()

        job_status_panel()
        if st.button("Stop after current page", key="transcribe_stop_running"):
            multi.request_cancel()
            coord.request_cancel()
            st.info("Stopping after current page…")
        return True

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
    multi_default = _multipass_default_selection(form["names"])
    multi_models = st.multiselect(
        "Vision models for multipass",
        options=form["names"],
        default=multi_default,
        format_func=form["model_label"],
        help="Select at least two models. Order matters: first model runs fully.",
        key="tx_this_compare_models",
    )
    render_model_information(
        form["all_models"],
        selected=multi_models,
        role="vision",
        key="tx_compare_model_info",
    )
    if multi_models:
        warn_if_first_compare_model_is_general_vlm(multi_models)
    compare_cleanup = st.checkbox(
        "Clean OCR during compare",
        value=False,
        help=(
            "Off by default so compare is a raw-model comparison. "
            "Cleanup still uses the cleanup/text model when enabled."
        ),
        key="tx_this_compare_cleanup",
    )
    no_auto_comp = st.checkbox(
        "Do not auto-activate composite",
        value=not bool(project.settings.auto_activate_composite),
        key="tx_this_no_auto_comp",
    )
    if st.button("Start multipass compare", key="tx_this_start_multipass"):
        if form["remote"] and not form["allow_remote"]:
            st.error("Enable the remote-host acknowledgement first.")
        elif len(multi_models) < 2:
            st.error("Select at least two vision models.")
        else:
            try:
                project = _apply_form_settings(projects, project, form)
                if compare_cleanup:
                    settings = project.settings
                    settings.cleanup_model_name = form["cleanup_model"] or form["text_model"]
                    project = projects.save_settings(project, settings)
                elif form["text_model"] and not project.settings.cleanup_model_name:
                    settings = project.settings
                    settings.cleanup_model_name = form["text_model"]
                    project = projects.save_settings(project, settings)
                coord.provider = OllamaVisionProvider(form["normalized"])
                multi = get_multipass_coordinator(str(root))
                multi.start(
                    model_names=list(multi_models),
                    force=form["force"],
                    auto_activate_composite=not no_auto_comp,
                    cleanup_enabled=bool(compare_cleanup),
                )
                st.session_state["_job_was_running"] = True
                st.session_state["_transcribe_post_kind"] = "multipass"
                st.session_state.pop("_transcribe_post_job_id", None)
                st.rerun()
            except (JobConflictError, TranscribeError) as exc:
                st.error(str(exc))


def _multipass_default_selection(available: list[str]) -> list[str]:
    """Workspace multipass_default_models filtered to currently listed models."""
    try:
        from transcribe.config.facade import get_config

        configured = list(get_config().effective.ocr.multipass_default_models or ())
    except Exception:
        configured = []
    avail = set(available)
    return [m for m in configured if m in avail]


def _render_batch_notebook_source(
    runtime: RuntimePaths,
    *,
    project: Project | None = None,
) -> None:
    """Notebook source picker; page-result scan only for pending pages."""
    _ = project
    corpus = CorpusPaths.from_runtime(runtime)
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
    selected: list = []
    import_run_id: str | None = None
    if source == "pending":
        refresh = st.button(
            "Refresh list",
            key="tx_batch_pending_refresh",
            help="Re-scan the corpus for notebooks with untranscribed or failed pages.",
        )
        candidates = _cached_ocr_candidates(corpus, force=refresh)
        selected = select_pending(candidates)
        st.caption(
            f"{len(selected)} notebook(s) with untranscribed or failed pages "
            f"({sum(c.pages_pending for c in selected)} page(s))."
        )
    elif source == "import_run":
        picker = _cached_light_picker(corpus)
        runs = _cached_import_runs(corpus)
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
                    selected = _cached_import_enriched(corpus, import_run_id, picker)
                    st.caption(
                        f"{len(selected)} committed notebook(s) · "
                        f"{sum(c.pages_pending for c in selected)} pending page(s)."
                    )
                except (TranscribeError, ValidationError) as exc:
                    st.error(str(exc))
    else:
        picker = _cached_light_picker(corpus)
        queued_ids = st.session_state.pop(TRANSCRIBE_BATCH_NOTEBOOK_IDS_KEY, None)
        options = [c.notebook_id for c in picker]
        labels = {c.notebook_id: c.title for c in picker}
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
                selected = select_by_ids(picker, list(picked))
            except TranscribeError as exc:
                st.error(str(exc))
    st.session_state[_OCR_SELECTED_KEY] = selected
    st.session_state[_OCR_IMPORT_RUN_KEY] = import_run_id


def _render_batch_launch_actions(
    runtime: RuntimePaths,
    batch_coord: BatchOcrCoordinator,
    *,
    form: dict[str, Any],
    seed: OCRSettings,
) -> None:
    """OCR settings consumers: start buttons + compare (fragment-isolated)."""
    corpus = CorpusPaths.from_runtime(runtime)
    selected = list(st.session_state.get(_OCR_SELECTED_KEY) or [])
    import_run_id = st.session_state.get(_OCR_IMPORT_RUN_KEY)

    recent = _cached_recent_ocr_runs(corpus)
    if recent:
        with st.expander("Recent batch OCR runs", expanded=False):
            for run in recent:
                ok = sum(1 for i in run.items if i.state == "completed")
                mode_bit = " · multipass" if run.mode == "multipass" else ""
                st.caption(
                    f"`{run.ocr_run_id}` · {run.status}{mode_bit} · "
                    f"{ok}/{len(run.items)} notebooks"
                )
                if run.status in {"pending", "running"} or any(
                    i.state in {"pending", "running"} for i in run.items
                ):
                    if st.button("Resume", key=f"batch_ocr_resume_{run.ocr_run_id}"):
                        try:
                            invalidate_batch_ocr_caches()
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
                invalidate_batch_ocr_caches()
                batch_coord.start(new_run.ocr_run_id)
                st.session_state[_BATCH_WAS_RUNNING_KEY] = True
                st.session_state.pop(_BATCH_POST_RUN_KEY, None)
                st.rerun()
            except (JobConflictError, TranscribeError, ValidationError) as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Compare models")
    st.caption(
        "Run two or more vision models on each selected notebook (sequentially), "
        "then rank and optionally produce a composite with the text model. "
        "Cost scales with models × notebooks × pages."
    )
    batch_multi_default = _multipass_default_selection(form["names"])
    batch_multi_models = st.multiselect(
        "Vision models for batch multipass",
        options=form["names"],
        default=batch_multi_default,
        format_func=form["model_label"],
        help="Select at least two models. Applied to every notebook in the batch.",
        key="tx_batch_compare_models",
    )
    render_model_information(
        form["all_models"],
        selected=batch_multi_models,
        role="vision",
        key="tx_batch_compare_model_info",
    )
    if batch_multi_models:
        warn_if_first_compare_model_is_general_vlm(batch_multi_models)
    batch_compare_cleanup = st.checkbox(
        "Clean OCR during compare",
        value=False,
        help=(
            "Off by default so compare is a raw-model comparison. "
            "Cleanup still uses the cleanup/text model when enabled."
        ),
        key="tx_batch_compare_cleanup",
    )
    batch_no_auto_comp = st.checkbox(
        "Do not auto-activate composite",
        value=not bool(seed.auto_activate_composite),
        key="tx_batch_no_auto_comp",
    )
    if st.button("Start batch multipass compare", key="tx_batch_start_multipass"):
        if form["remote"] and not form["allow_remote"]:
            st.error("Enable the remote-host acknowledgement first.")
        elif not selected:
            st.error("Select at least one notebook.")
        elif len(batch_multi_models) < 2:
            st.error("Select at least two vision models.")
        else:
            try:
                settings = _form_to_settings(seed, form)
                if batch_compare_cleanup:
                    settings.cleanup_model_name = form["cleanup_model"] or form["text_model"]
                elif form["text_model"] and not settings.cleanup_model_name:
                    settings.cleanup_model_name = form["text_model"]
                if form["text_model"]:
                    settings.text_model_name = form["text_model"]
                settings.auto_activate_composite = not batch_no_auto_comp
                new_run = batch_coord.create_run(
                    selected,
                    settings=settings,
                    force=form["force"],
                    import_run_id=import_run_id,
                    mode="multipass",
                    vision_model_names=list(batch_multi_models),
                    multipass_cleanup_enabled=bool(batch_compare_cleanup),
                )
                invalidate_batch_ocr_caches()
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
        st.warning("This Ollama host is not loopback. Page images will leave this machine.")
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
    render_model_information(
        all_discovery.models,
        selected=[n for n in (model, text_model) if n],
        role="all",
        key=f"{key_prefix}_model_info",
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
        prompt_id = st.selectbox("Prompt", ocr_ids, index=prompt_index, key=f"{key_prefix}_prompt")
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
                else (
                    list(prefer_labels.keys()).index(DEFAULT_PREFER_MODE)
                    if DEFAULT_PREFER_MODE in prefer_labels
                    else 0
                )
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
        "vision_models": discovery.models,
        "all_models": all_discovery.models,
        "model_label": _model_label,
    }
