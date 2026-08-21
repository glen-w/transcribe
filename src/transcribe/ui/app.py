"""Streamlit UI for Transcribe.

JobCoordinator, BatchOcrCoordinator, and AnalysisCoordinator are owned via
st.cache_resource so reruns do not drop live OCR / analysis jobs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

from transcribe.analysis.coordinator import (
    AnalysisCoordinator,
    build_analysis_coordinator,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import TranscribeError
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import build_runtime_paths
from transcribe.services.archive import ArchiveService, bump_archive_generation
from transcribe.services.project import (
    ProjectService,
    allocate_notebook_root,
    open_project_paths,
)
from transcribe.ui import icons as ic
from transcribe.ui.archive_views import render_archive, render_notebooks, render_search
from transcribe.ui.components.context_bar import render_context_bar
from transcribe.ui.home import render_home
from transcribe.ui.layout import apply_page_width
from transcribe.ui.navigation import (
    is_open_notebook_workflow,
    is_view_mode,
    apply_destination_to_session,
    normalize_ui_mode,
    page_spec_for,
)
from transcribe.ui.settings_interface import render_settings_page
from transcribe.ui.page_viewer import render_page_viewer
from transcribe.ui.run_analysis import render_run_analysis_form
from transcribe.ui.run_import import render_run_import
from transcribe.ui.run_transcribe import invalidate_batch_ocr_caches, render_run_transcribe
from transcribe.ui.components.global_analysis_progress import (
    render_global_analysis_progress,
)
from transcribe.ui.shell import (
    configure_streamlit_page,
    inject_global_styles,
    render_brand,
    render_mode_nav,
    render_page_shell,
    set_ui_mode,
    sync_notebook_selector,
)
from transcribe.ui.targets import PENDING_IMPORT_TARGET_KEY, TARGET_BATCH


@st.cache_resource
def get_batch_analysis_coordinator(data_dir: str, projects_dir: str):
    from transcribe.corpus.paths import CorpusPaths
    from transcribe.runtime_paths import RuntimePaths
    from transcribe.services.batch_analysis import build_batch_analysis_coordinator

    live = build_runtime_paths()
    runtime = RuntimePaths(
        repo_root=live.repo_root,
        data_dir=Path(data_dir),
        projects_dir=Path(projects_dir),
        inbox_dir=live.inbox_dir,
        export_dir=live.export_dir,
    )
    corpus = CorpusPaths.from_runtime(runtime)
    return build_batch_analysis_coordinator(
        corpus, clock=SystemClock(), ids=UuidGenerator()
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


def _render_workflow(runtime, root: str, *, section: str = "Import") -> None:
    section = normalize_ui_mode(section)
    try:
        paths, projects, _ingest = _services(root)
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
        from transcribe.ui.review_workbench import render_review_page

        page_ids = st.session_state.get("view_page_ids") or viewer_page_ids(project)
        view_entries = st.session_state.get("view_entries")
        render_review_page(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=page_ids,
            view_entries=view_entries,
        )
        return

    if section == "Analyse":
        _render_analyse_this_notebook(runtime, paths, projects, project)
        return

    if section == "Export":
        _render_export_panel(runtime, paths, projects, project, root)
        return

    if section == "Review":
        _render_review_workbench(runtime, paths, projects, project)
        return


def _render_analyse_this_notebook(runtime, paths, projects, project) -> None:
    _ = runtime
    _ = paths
    analysis_coord = get_analysis_coordinator(str(paths.root))
    render_run_analysis_form(projects=projects, project=project, coord=analysis_coord)


def render_analyse_workspace(
    runtime,
    *,
    root: str | None,
    projects,
    project,
) -> None:
    """Analyse with This notebook | Batch target switcher."""
    from transcribe.ui.components.global_analysis_progress import (
        is_analysis_operation_active,
        sync_analyse_target_to_active_operation,
    )
    from transcribe.ui.run_analysis import analysis_run_in_progress
    from transcribe.ui.run_analysis_batch import (
        render_batch_analysis_launch,
        render_batch_analysis_progress,
    )
    from transcribe.ui.targets import (
        ANALYSE_TARGET_KEY,
        PENDING_ANALYSE_TARGET_KEY,
        TARGET_BATCH,
        TARGET_OPTIONS,
        TARGET_THIS,
        apply_pending_target,
        normalize_target,
    )

    batch_coord = get_batch_analysis_coordinator(
        str(runtime.data_dir), str(runtime.projects_dir)
    )
    batch_running = batch_coord.is_running() or (
        batch_coord.get_progress().status == "running"
    )
    operation_active = is_analysis_operation_active(
        st.session_state, batch_running=batch_running
    )
    # Returning mid-run must reopen the same target + progress, not the config form.
    if operation_active:
        st.session_state.pop(PENDING_ANALYSE_TARGET_KEY, None)
        active_target = sync_analyse_target_to_active_operation(
            st.session_state, batch_running=batch_running
        )
    else:
        apply_pending_target(
            st.session_state,
            pending_key=PENDING_ANALYSE_TARGET_KEY,
            target_key=ANALYSE_TARGET_KEY,
        )
        active_target = None

    normalize_target(st.session_state, ANALYSE_TARGET_KEY)
    target = st.segmented_control(
        "Target",
        options=list(TARGET_OPTIONS),
        key=ANALYSE_TARGET_KEY,
        disabled=operation_active,
        help=(
            "This notebook: Analyse the selected notebook. "
            "Batch: same Analyse plan across many notebooks "
            "(needing analysis, an import run, or a manual pick)."
            if not operation_active
            else "Target is locked while an analysis run is in progress."
        ),
    )
    if target is None:
        target = st.session_state.get(ANALYSE_TARGET_KEY) or TARGET_THIS
    if operation_active and active_target is not None:
        target = active_target

    # Ongoing this-notebook run takes priority over Target=Batch so return
    # visits always restore the live progress panel (and Cancel).
    active_root = root
    pending = st.session_state.get("run_analysis_pending_launch")
    if (
        operation_active
        and active_target == TARGET_THIS
        and isinstance(pending, dict)
        and isinstance(pending.get("project_root"), str)
        and pending["project_root"].strip()
    ):
        active_root = pending["project_root"].strip()

    this_running = False
    if active_root:
        try:
            analysis_coord = get_analysis_coordinator(str(Path(active_root)))
            this_running = analysis_run_in_progress(analysis_coord)
        except TranscribeError:
            this_running = bool(st.session_state.get("analysis_run_in_progress"))

    if this_running or (operation_active and active_target == TARGET_THIS and active_root):
        try:
            paths = open_project_paths(Path(active_root))
            run_projects = ProjectService(
                paths, clock=SystemClock(), ids=UuidGenerator()
            )
            run_project = run_projects.load(reconcile=True)
        except TranscribeError as exc:
            st.error(str(exc))
            return
        _render_analyse_this_notebook(runtime, paths, run_projects, run_project)
        return

    if render_batch_analysis_progress(batch_coord, runtime):
        return

    if target == TARGET_BATCH:
        render_batch_analysis_launch(
            runtime,
            batch_coord,
            projects=projects,
            project=project,
        )
        return

    if project is None or projects is None or not root:
        st.info("Select a notebook in the View block, or create one under Workflow → New notebook.")
        return
    paths = open_project_paths(Path(root))
    _render_analyse_this_notebook(runtime, paths, projects, project)


def _render_review_workbench(runtime, paths, projects, project) -> None:
    from transcribe.ui.action_menus.nav import viewer_page_ids
    from transcribe.ui.review_queue import (
        ReviewFilter,
        available_review_filters,
        filter_review_page_ids,
        format_review_filter_label,
    )

    if not project.pages:
        st.info("No pages yet.")
        return

    st.caption(
        "Unapproved suggested dates still appear in Archive timeline. "
        "Time-of-day stamps are ignored until Future metadata lands."
    )

    base_ids = viewer_page_ids(project)
    filter_options_with_counts = available_review_filters(
        project,
        base_page_ids=base_ids,
        load_page_result=projects.load_page_result,
    )
    filter_options = [key for key, _ in filter_options_with_counts]
    filter_counts = dict(filter_options_with_counts)
    current_filter = st.session_state.get("review_needs_filter")
    if current_filter not in filter_options and filter_options:
        st.session_state["review_needs_filter"] = filter_options[0]
    filter_key: ReviewFilter = st.selectbox(
        "Queue",
        filter_options,
        format_func=lambda key: format_review_filter_label(key, filter_counts[key]),
        key="review_needs_filter",
    )
    page_ids = filter_review_page_ids(
        project,
        filter_key=filter_key,
        base_page_ids=base_ids,
        load_page_result=projects.load_page_result,
    )

    if not page_ids:
        if filter_key == "all":
            st.info("No pages yet.")
        else:
            st.success("Nothing needs attention for this filter.")
        return

    default_id = st.session_state.get("view_page_id") or page_ids[0]
    if default_id not in page_ids:
        default_id = page_ids[0]
    view_entries = [{"page_id": pid, "project_root": str(paths.root)} for pid in page_ids]
    st.session_state["view_page_id"] = default_id
    st.session_state["view_page_ids"] = page_ids
    st.session_state["view_entries"] = view_entries
    st.caption(f"Showing {len(page_ids)} of {len(base_ids)} pages")
    from transcribe.ui.review_workbench import render_review_page

    render_review_page(
        paths=paths,
        projects=projects,
        project=project,
        page_id=default_id,
        page_ids=page_ids,
        view_entries=view_entries,
    )


def _render_reading_mode(paths, projects, project) -> None:
    from transcribe.ui.action_menus.nav import chronological_page_ids

    if not project.pages:
        st.info("No pages yet.")
        return

    page_ids = chronological_page_ids(project)
    root_key = str(paths.root)
    by_root = dict(st.session_state.get("reading_page_by_root") or {})
    remembered = by_root.get(root_key)
    default_id = st.session_state.get("view_page_id") or remembered or page_ids[0]
    if default_id not in page_ids:
        default_id = page_ids[0]

    dated = [p for p in project.pages if p.date is not None]
    if dated:
        jump_labels = {
            p.page_id: (
                f"{p.date.format_display()} · "
                f"p.{next(i for i, x in enumerate(project.pages, 1) if x.page_id == p.page_id)}"
            )
            for p in sorted(dated, key=lambda page: (page.date.sort_key(), page.page_id))
        }
        choices = ["— Jump by date —"] + list(jump_labels.keys())
        selected = st.selectbox(
            "Jump by date",
            choices,
            format_func=lambda pid: ("— Jump by date —" if pid == choices[0] else jump_labels[pid]),
            key="reading_jump_by_date",
        )
        if selected != choices[0] and selected in page_ids:
            default_id = selected

    view_entries = [{"page_id": pid, "project_root": root_key} for pid in page_ids]
    st.session_state["view_page_id"] = default_id
    st.session_state["view_page_ids"] = page_ids
    st.session_state["view_entries"] = view_entries
    from transcribe.ui.page_viewer import remember_reading_page

    remember_reading_page(root_key, default_id)
    render_page_viewer(
        paths=paths,
        projects=projects,
        project=project,
        page_id=default_id,
        page_ids=page_ids,
        view_entries=view_entries,
        highlight_query="",
        show_back=False,
        presentation="read",
    )


def _render_export_panel(runtime, paths, projects, project, root: str) -> None:
    from transcribe.ui.export_panel import render_export_panel

    archive = get_archive(str(runtime.projects_dir), str(runtime.data_dir))
    render_export_panel(runtime, paths, projects, project, root, archive=archive)


def _render_view_reading(paths, projects, project) -> None:
    spec = page_spec_for("Reading")
    assert spec is not None
    render_page_shell(spec.title, spec.description)
    if st.session_state.get("show_page_viewer") and st.session_state.get("view_page_id"):
        from transcribe.ui.action_menus.nav import viewer_page_ids

        return_mode = st.session_state.get("page_return_mode") or "Library"
        page_ids = st.session_state.get("view_page_ids") or viewer_page_ids(project)
        render_page_viewer(
            paths=paths,
            projects=projects,
            project=project,
            page_id=st.session_state["view_page_id"],
            page_ids=page_ids,
            view_entries=st.session_state.get("view_entries"),
            highlight_query=st.session_state.get("view_highlight", ""),
            back_label=f"Back to {return_mode}",
            presentation="read",
        )
        return
    _render_reading_mode(paths, projects, project)


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
    if st.button("Create notebook", type="primary", key="new_notebook_create", icon=ic.CREATE):
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
            invalidate_batch_ocr_caches()
            from transcribe.ui.run_analysis_batch import invalidate_batch_analyse_caches

            invalidate_batch_analyse_caches()
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

    first_visit = "ui_mode" not in st.session_state
    raw_mode = st.session_state.get("ui_mode")
    if raw_mode == "Inbox":
        st.session_state[PENDING_IMPORT_TARGET_KEY] = TARGET_BATCH
    if first_visit:
        mode = "Home"
        st.session_state["ui_mode"] = mode
    else:
        mode = apply_destination_to_session(st.session_state, raw_mode)

    with st.sidebar:
        render_brand()
        mode = render_mode_nav(mode, notebook_options=notebook_options)

    root = st.session_state.get("root") or ""
    apply_page_width(mode)
    title_by_root = {r: t for r, t in notebook_options}
    render_context_bar(
        mode=mode,
        root=root or None,
        title=title_by_root.get(root),
        show_path=False,
    )

    # Floating chip while analysis runs off the Analyse page.
    batch_coord = get_batch_analysis_coordinator(
        str(runtime.data_dir), str(runtime.projects_dir)
    )
    render_global_analysis_progress(
        batch_coord=batch_coord,
        get_analysis_coord=get_analysis_coordinator,
    )

    spec = page_spec_for(mode)
    if spec is None:
        spec = page_spec_for("Archive")
        assert spec is not None

    if mode == "Home":
        render_page_shell(spec.title, spec.description)
        render_home(runtime, archive)
        return
    if mode == "Library":
        render_page_shell(spec.title, spec.description)
        render_notebooks(runtime, archive)
        return
    if mode == "Search":
        render_page_shell(spec.title, spec.description)
        render_search(runtime, archive)
        return
    if mode == "Archive":
        render_page_shell(spec.title, spec.description)
        render_archive(runtime, archive)
        return
    if mode == "Settings":
        render_page_shell(spec.title, spec.description)
        render_settings_page()
        return
    if mode == "Diagnostics":
        from transcribe.ui.diagnostics import render_diagnostics

        render_page_shell(spec.title, spec.description)
        render_diagnostics(runtime, root=root or None)
        return
    if mode == "New notebook":
        render_page_shell(spec.title, spec.description)
        _render_new_notebook(runtime, archive)
        return

    if mode in {"Import", "Transcribe", "Analyse"}:
        render_page_shell(spec.title, spec.description)
        projects = ingest = project = None
        if root:
            try:
                _paths, projects, ingest = _services(root)
                project = projects.load(reconcile=True)
            except TranscribeError as exc:
                st.caption(str(exc))
                projects = ingest = project = None
        if mode == "Import":
            render_run_import(
                runtime,
                root=root or None,
                projects=projects,
                ingest=ingest,
                project=project,
            )
        elif mode == "Transcribe":
            render_run_transcribe(
                runtime,
                root=root or None,
                projects=projects,
                project=project,
            )
        else:
            render_analyse_workspace(
                runtime,
                root=root or None,
                projects=projects,
                project=project,
            )
        return

    if is_view_mode(mode) or is_open_notebook_workflow(mode):
        if not root:
            if mode == "Places":
                render_page_shell(spec.title, spec.description)
                from transcribe.ui.notebook_views import render_places_without_notebook

                render_places_without_notebook(runtime)
                return
            render_page_shell(spec.title, spec.description)
            st.info("Select a notebook in View, or create one under Workflow → New notebook.")
            return
        try:
            paths, projects, _ingest = _services(root)
            project = projects.load(reconcile=True)
        except TranscribeError as exc:
            render_page_shell(spec.title, spec.description)
            st.info("Select a notebook in View, or create one under Workflow → New notebook.")
            st.caption(str(exc))
            return
        if mode == "Reading":
            _render_view_reading(paths, projects, project)
            return
        if mode == "Review" or mode == "Export":
            _render_workflow(runtime, root, section=mode)
            return
        from transcribe.ui.notebook_views import (
            render_view_ask,
            render_view_detect,
            render_view_mood,
            render_view_overview,
            render_view_places,
            render_view_summaries,
            render_view_themes,
        )

        kwargs = {
            "runtime": runtime,
            "paths": paths,
            "projects": projects,
            "project": project,
            "get_analysis_coordinator": get_analysis_coordinator,
        }
        if mode == "Overview":
            render_view_overview(**kwargs)
        elif mode == "Themes":
            render_view_themes(**kwargs)
        elif mode == "Mood":
            render_view_mood(**kwargs)
        elif mode == "Places":
            render_view_places(**kwargs)
        elif mode == "Summaries":
            render_view_summaries(**kwargs)
        elif mode == "Ask":
            render_view_ask(**kwargs)
        elif mode == "Detect":
            render_view_detect(
                projects=projects, project=project, project_root=str(paths.root)
            )
        return


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
